"""Gate 1A-08 pure policy + fake-page menu/fallback tests, no network."""
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from gate1a08_menu_connect import (
    ADVANCED, HOME, CATEGORY_DOM_JS, blank_report, failure_reason,
    official_public_url, look_for_form, open_home_menu, run,
    run_with_page,
)


class Response:
    def __init__(self,status=200): self.status=status


class Clicker:
    def __init__(self,page,kind):self.page=page;self.kind=kind

    async def click(self,*,timeout):
        self.page.clicks.append(self.kind)
        if self.kind=="consultations":
            self.page.url=ADVANCED
            self.page.form_ready=True
        if self.kind==self.page.fail_at:
            raise TimeoutError("private URL or token should not reach logs")


class FakePage:
    def __init__(self,*,fail_at=None,home_status=200,form_after_menu=True,
                 fail_home=False,fail_direct=False,home_dest=HOME):
        self.url="about:blank"
        self.fail_at=fail_at
        self.home_status=home_status
        self.form_after_menu=form_after_menu
        self.fail_home=fail_home
        self.fail_direct=fail_direct
        self.home_dest=home_dest
        self.goto_calls=[]
        self.clicks=[]
        self.form_ready=False
        self.waited=[]
        self.direct_status=200

    async def goto(self,url,*,wait_until,timeout):
        self.goto_calls.append((url,wait_until,timeout))
        if url==HOME:
            if self.fail_home:
                raise TimeoutError("hidden portal URL")
            self.url=self.home_dest
            return Response(self.home_status)
        if url==ADVANCED:
            if self.fail_direct:
                raise TimeoutError("hidden direct URL")
            self.url=ADVANCED
            self.form_ready=True
            return Response(self.direct_status)
        raise AssertionError("unsafe goto URL")

    async def wait_for_selector(self,selector,*,state,timeout):
        self.waited.append(selector)
        if selector!="#Annoces":raise AssertionError("other menu?")
        if self.fail_at=="menu_not_visible":
            raise TimeoutError()
        if state!="visible":raise AssertionError("selector not visible")

    def locator(self,selector):
        assert selector=="#Annoces"
        return Clicker(self,"menu")

    def get_by_role(self,role,*,name):
        assert role=="link"
        assert name.search("Consultations en cours")
        return Clicker(self,"consultations")

    async def wait_for_function(self,js,*,timeout,polling):
        assert js==CATEGORY_DOM_JS
        if not self.form_ready:
            raise TimeoutError("form not found")

    async def evaluate(self,js):
        if self.form_ready:
            return {"category_control_found":True,"ready_state":"interactive","body_text_length":3000}
        return {"category_control_found":False,"ready_state":"loading","body_text_length":0,"body_html_length":0}


class TestPolicy(unittest.TestCase):
    def test_allowed_home(self):
        self.assertTrue(official_public_url(HOME,navigation=True))

    def test_allowed_advanced(self):
        self.assertTrue(official_public_url(ADVANCED,navigation=True))

    def test_url_scheme_host_port_credentials_rejected(self):
        for x in ["http://www.marchespublics.gov.ma/",
                  "https://not-marchespublics.gov.ma/",
                  "https://name:pass@www.marchespublics.gov.ma/",
                  "https://www.marchespublics.gov.ma:8443/",
                  "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseHome#frag"]:
            self.assertFalse(official_public_url(x,navigation=True),x)

    def test_protected_other_navigation_rejected(self):
        for p in ["entreprise.EntrepriseDetailsConsultation","entreprise.EntrepriseAuthentification"]:
            self.assertFalse(official_public_url("https://www.marchespublics.gov.ma/index.php?page="+p,navigation=True))

    def test_static_resources_allowed_same_host(self):
        self.assertTrue(official_public_url("https://www.marchespublics.gov.ma/styles/main.css"))
        self.assertFalse(official_public_url("https://external.example/styles/main.css"))

    def test_blank_report_does_not_claim_filter_or_storage(self):
        d=blank_report()
        self.assertFalse(d["category_confirmed"])
        self.assertFalse(d["pagination_started"])
        self.assertEqual(d["search_clicks"],0)
        self.assertEqual(d["database_writes"],0)

    def test_cannot_run_live_implicitly(self):
        old=os.environ.pop("ENABLE_LIVE_GATE1A08",None)
        try:
            x=asyncio.run(run())
        finally:
            if old is not None:os.environ["ENABLE_LIVE_GATE1A08"]=old
        self.assertEqual(x["status"],"LIVE_DISABLED")

    def test_bounded_waits(self):
        with self.assertRaises(ValueError):
            asyncio.run(look_for_form(FakePage(),timeout_ms=600000))


class TestMenu(unittest.TestCase):
    def test_successful_home_menu_form(self):
        p=FakePage()
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"FORM_READY_CONFIRMED_ONCE",result)
        self.assertTrue(result["search_form"]["form_ready"])
        self.assertEqual(result["search_form"]["source"],"home_menu")
        self.assertEqual(result["home_navigation"]["http_status"],200)
        self.assertEqual(result["direct_get_attempts"],0)
        self.assertEqual(result["home_get_attempts"],1)
        self.assertEqual(p.clicks,["menu","consultations"])
        self.assertEqual(len(p.goto_calls),1)
        self.assertEqual(p.goto_calls[0][1],"commit")
        self.assertFalse(result["category_confirmed"])

    def test_home_timeout_safe_direct_once(self):
        p=FakePage(fail_home=True)
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"FORM_READY_CONFIRMED_ONCE",result)
        self.assertEqual(result["search_form"]["source"],"direct_fallback")
        self.assertEqual(result["home_navigation"]["goto"],"TIMEOUT")
        self.assertEqual(result["direct_get_attempts"],1)
        self.assertEqual(len(p.goto_calls),2)

    def test_home_menu_not_visible_direct_once(self):
        p=FakePage(fail_at="menu_not_visible")
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"FORM_READY_CONFIRMED_ONCE",result)
        self.assertEqual(result["menu"]["error"],"ANNOCES_MENU_NOT_VISIBLE")
        self.assertEqual(p.clicks,[])
        self.assertEqual(result["direct_get_attempts"],1)

    def test_menu_click_timeout_no_repeat(self):
        p=FakePage(fail_at="menu")
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"FORM_READY_CONFIRMED_ONCE",result)
        self.assertEqual(p.clicks,["menu"])
        self.assertEqual(result["direct_get_attempts"],1)

    def test_consultations_click_timeout_can_observe_form(self):
        p=FakePage(fail_at="consultations")
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"FORM_READY_CONFIRMED_ONCE",result)
        self.assertEqual(result["direct_get_attempts"],0)
        self.assertEqual(p.clicks,["menu","consultations"])

    def test_home_403_stops_without_fallback(self):
        p=FakePage(home_status=403)
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"HOME_HTTP_ERROR")
        self.assertEqual(result["direct_get_attempts"],0)
        self.assertEqual(p.clicks,[])

    def test_home_external_redirect_never_clicks(self):
        p=FakePage(home_dest="https://evil.example/index.php?page=entreprise.EntrepriseHome")
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"UNAPPROVED_HOME_DESTINATION")
        self.assertEqual(result["direct_get_attempts"],0)
        self.assertEqual(p.clicks,[])

    def test_both_attempts_timeout_unconfirmed(self):
        p=FakePage(fail_home=True,fail_direct=True)
        result=asyncio.run(run_with_page(p))
        self.assertEqual(result["status"],"DIRECT_NAVIGATION_NOT_COMMITTED")
        self.assertEqual(result["direct_get_attempts"],1)
        self.assertEqual(result["search_clicks"],0)
        self.assertNotIn("hidden",str(result))

    def test_no_fallback_when_disabled(self):
        p=FakePage(fail_home=True)
        result=asyncio.run(run_with_page(p,allow_fallback=False))
        self.assertEqual(result["status"],"HOME_NAVIGATION_NOT_COMMITTED")
        self.assertEqual(result["direct_get_attempts"],0)

    def test_form_dom_must_exist(self):
        p=FakePage()
        p.url=ADVANCED
        r=asyncio.run(look_for_form(p,timeout_ms=1000))
        self.assertEqual(r,(False,"CATEGORY_CONTROL_NOT_READY"))


if __name__=="__main__":
    unittest.main()
