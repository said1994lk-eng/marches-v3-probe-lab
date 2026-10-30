"""Offline tests for safe redirect classification and bounded fallback."""
import asyncio
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from navigation_destination import classify_destination, is_benign_official_redirect
from navigation_recovery import recover_search_form, Route

BASE='https://www.marchespublics.gov.ma'
A=Route('primary',BASE+'/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons')
B=Route('secondary',BASE+'/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons')

class DestinationTests(unittest.TestCase):
    def test_same_host_home_is_classified(self):
        self.assertEqual(classify_destination(BASE+'/index.php?page=entreprise.EntrepriseHome'), 'OFFICIAL_HOME_OR_LANDING')
    def test_root_is_classified(self):
        self.assertEqual(classify_destination(BASE+'/'), 'OFFICIAL_HOME_OR_LANDING')
    def test_advanced_path_different_query(self):
        self.assertEqual(classify_destination(BASE+'/?page=entreprise.EntrepriseAdvancedSearch'), 'OFFICIAL_ADVANCED_SEARCH_ROUTE')
    def test_login_is_not_benign(self):
        self.assertEqual(classify_destination(BASE+'/index.php?page=entreprise.Authentification'), 'OFFICIAL_AUTH_WALL')
        self.assertFalse(is_benign_official_redirect('OFFICIAL_AUTH_WALL'))
    def test_third_party_stops(self):
        self.assertEqual(classify_destination('https://evil.example/index.php?page=entreprise.EntrepriseHome'),'UNTRUSTED_DESTINATION')
    def test_credentials_are_not_benign(self):
        self.assertEqual(classify_destination('https://name:pass@www.marchespublics.gov.ma/'), 'UNTRUSTED_DESTINATION')
    def test_sensitive_query_not_reported(self):
        self.assertEqual(classify_destination(BASE+'/?page=entreprise.Authentification&token=secretvalue'), 'OFFICIAL_AUTH_WALL')
    def test_unknown_page_stops(self):
        self.assertEqual(classify_destination(BASE+'/index.php?page=entreprise.Unknown'), 'UNRECOGNIZED_OFFICIAL_PAGE')

class RedirectPolicyTests(unittest.TestCase):
    def test_official_home_then_secondary_form(self):
        class Response:
            status=200
        class FakePage:
            def __init__(self):self.url='';self.calls=[]
            async def goto(self,url,*,wait_until,timeout):
                self.calls.append(url)
                self.url=BASE+'/' if len(self.calls)==1 else url
                return Response()
            async def evaluate(self,js):
                return {'category_control_found': True}
            async def wait_for_timeout(self,ms):pass
        p=FakePage()
        r=asyncio.run(recover_search_form(p,[A,B]))
        self.assertEqual(len(p.calls),2)
        self.assertTrue(r.form_ready)
        self.assertEqual(r.observations[0]['reason_code'],'OFFICIAL_REDIRECT_TO_OTHER_ROUTE')
        self.assertEqual(r.observations[0]['destination_class'],'OFFICIAL_HOME_OR_LANDING')
    def test_external_redirection_never_tried_again(self):
        class Response:status=200
        class FakePage:
            def __init__(self):self.url='';self.calls=[]
            async def goto(self,url,*,wait_until,timeout):
                self.calls.append(url)
                self.url='https://evil.example/'
                return Response()
            async def evaluate(self,js):raise AssertionError('should not inspect untrusted DOM')
        p=FakePage();r=asyncio.run(recover_search_form(p,[A,B]))
        self.assertFalse(r.form_ready)
        self.assertEqual(len(p.calls),1)
        self.assertEqual(r.observations[0]['destination_class'],'UNTRUSTED_DESTINATION')
    def test_two_public_redirects_do_not_prove_form(self):
        class Response:status=200
        class FakePage:
            url=BASE+'/'
            async def goto(self,url,*,wait_until,timeout):return Response()
        r=asyncio.run(recover_search_form(FakePage(),[A,B]))
        self.assertFalse(r.form_ready)
        self.assertEqual(len(r.observations),2)
        self.assertNotEqual(r.reason_code,'SEARCH_FORM_CONFIRMED')

if __name__=='__main__':unittest.main()