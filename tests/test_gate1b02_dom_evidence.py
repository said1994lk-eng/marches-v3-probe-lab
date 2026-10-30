"""Gate 1B-02 offline safety and evidence tests; never contact the portal."""
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from gate1b02_dom_evidence import (
    CARD_ATTR_JS, DETAIL_STRUCTURE_JS, allowed_detail_url,
    classify_card_attributes, decide_detail_proof, interpret_differential,
    inspect_one_public_detail, one_detail_link,
)
from gate1b02_probe import run

BASE="https://www.marchespublics.gov.ma/"
PLURAL=BASE+"index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=12345"
SINGULAR=BASE+"index.php?page=entreprise.EntrepriseDetailConsultation&refConsultation=12345"


class SafeDetailTests(unittest.TestCase):
    def test_plural_route(self):
        self.assertEqual(allowed_detail_url(PLURAL, BASE),PLURAL)

    def test_singular_route(self):
        self.assertEqual(allowed_detail_url(SINGULAR,BASE),SINGULAR)

    def test_relative_route(self):
        self.assertEqual(allowed_detail_url(
            "index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=5",
            BASE),BASE+"index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=5")

    def test_external_route_rejected(self):
        self.assertIsNone(allowed_detail_url(
            "https://evil.example/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=5",
            BASE))

    def test_invalid_route_no_id(self):
        self.assertIsNone(allowed_detail_url(
            BASE+"index.php?page=entreprise.EntrepriseDetailsConsultation",BASE))

    def test_download_controls_rejected(self):
        self.assertIsNone(allowed_detail_url(PLURAL+"&download=1",BASE))

    def test_auth_controls_rejected(self):
        self.assertIsNone(allowed_detail_url(PLURAL+"&authToken=x",BASE))

    def test_bad_scheme_or_credentials_rejected(self):
        self.assertIsNone(allowed_detail_url(
            "http://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=5",BASE))
        self.assertIsNone(allowed_detail_url(
            "https://user:pw@www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=5",BASE))

    def test_fragment_rejected(self):
        self.assertIsNone(allowed_detail_url(PLURAL+"#secret",BASE))

    def test_other_portal_page_rejected(self):
        self.assertIsNone(allowed_detail_url(
            BASE+"index.php?page=entreprise.Authentification&refConsultation=7",BASE))


class EvidencePolicyTests(unittest.TestCase):
    def test_icon_alt_fournitures_is_candidate_not_proof(self):
        d=classify_card_attributes({"cards":[{
            "attribute_candidate_values":["fournitures"],
            "attribute_candidate_sources":["alt"]}]})
        self.assertEqual(d["status"],"ATTRIBUTE_CANDIDATES_ONLY")
        self.assertEqual(d["candidate_fournitures"],1)

    def test_icon_alt_travaux_is_candidate_not_direct_contradiction(self):
        d=classify_card_attributes({"cards":[{
            "attribute_candidate_values":["travaux"],
            "attribute_candidate_sources":["title"]}]})
        self.assertEqual(d["candidate_other"],1)
        self.assertNotIn("CONTRADICT",d["status"])

    def test_no_attributes(self):
        self.assertEqual(classify_card_attributes({"cards":[{}]})["status"],
                         "NO_ATTRIBUTE_CANDIDATES")

    def test_explicit_one_detail_fournitures_proves_one_only(self):
        d=decide_detail_proof(True,{"status":"EXPLICIT","category":"fournitures",
                                     "source":"explicit_label_pair"})
        self.assertEqual(d.status,"DIRECT_SPOT_CHECK_ONLY")
        self.assertEqual(d.records_verified,1)
        self.assertFalse(d.can_claim_all_results)

    def test_one_detail_travaux_is_contradiction_only_one_record(self):
        d=decide_detail_proof(True,{"status":"EXPLICIT","category":"travaux",
                                     "source":"explicit_inline_label"})
        self.assertEqual(d.status,"CONTRADICTED_SPOT_CHECK")
        self.assertFalse(d.can_claim_all_results)

    def test_untrusted_source_not_proof(self):
        d=decide_detail_proof(True,{"status":"EXPLICIT","category":"fournitures",
                                     "source":"image_alt"})
        self.assertEqual(d.status,"UNCONFIRMED")
        self.assertEqual(d.records_verified,0)

    def test_missing_detail_not_proof(self):
        self.assertEqual(decide_detail_proof(True,None).status,"UNCONFIRMED")

    def test_postback_missing_not_direct_proof(self):
        self.assertEqual(decide_detail_proof(False,{"status":"EXPLICIT",
            "category":"fournitures","source":"explicit_label_pair"}).status,"UNCONFIRMED")

    def test_disjoint_top5_does_not_prove_disjoint_full_sets(self):
        d=interpret_differential({"a","b"},{"c","d"},1377,1000)
        self.assertEqual(d,"DIFFERENTIAL_SUPPORT_ONLY")
        self.assertNotIn("CONFIRMED",d)

    def test_top5_overlap_means_review_not_automatic_failure(self):
        self.assertEqual(interpret_differential({"a","b"},{"b","c"},1377,1000),
                         "DIFFERENTIAL_SAMPLE_OVERLAP_REVIEW")

    def test_differential_invalid(self):
        self.assertEqual(interpret_differential(set(),{"a"},1377,1000),
                         "DIFFERENTIAL_UNCONFIRMED")

    def test_js_never_returns_raw_outerhtml(self):
        self.assertNotIn("outerHTML",CARD_ATTR_JS)
        self.assertNotIn("outerHTML",DETAIL_STRUCTURE_JS)
        self.assertNotIn("PRADO_PAGESTATE",CARD_ATTR_JS)


class ProbeTests(unittest.TestCase):
    def test_off_by_default(self):
        old=os.environ.pop("ENABLE_LIVE_GATE1B02",None)
        try:
            report=asyncio.run(run())
        finally:
            if old is not None:
                os.environ["ENABLE_LIVE_GATE1B02"]=old
        self.assertEqual(report["status"],"LIVE_DISABLED")
        self.assertEqual(report["search_clicks"],0)
        self.assertEqual(report["detail_get_attempts"],0)
        self.assertFalse(report["all_results_verified"])
        self.assertFalse(report["differential_proof_claimed"])

    def test_get_one_detail_uses_commit_and_one_page(self):
        class Resp:
            status=200
        class FakeDetail:
            url=PLURAL
            def __init__(self): self.go_calls=0;self.closed=False
            async def goto(self,url,*,wait_until,timeout):
                assert url==PLURAL and wait_until=="commit"
                self.go_calls+=1
                return Resp()
            async def wait_for_function(self,script,*,timeout): pass
            async def evaluate(self,script,arg=None):
                if script==DETAIL_STRUCTURE_JS:
                    return {"container_present":True,
                       "explicit_category_label_present":True,
                       "category_attribute_candidates":0,
                       "label_tag_types":["TH"]}
                return {"status":"EXPLICIT","category":"fournitures",
                        "source":"explicit_label_pair"}
            async def close(self):self.closed=True
        class Ctx:
            def __init__(self):self.p=FakeDetail();self.calls=0
            async def new_page(self):self.calls+=1;return self.p
        c=Ctx()
        result=asyncio.run(inspect_one_public_detail(c,PLURAL))
        self.assertEqual(c.calls,1)
        self.assertEqual(c.p.go_calls,1)
        self.assertTrue(c.p.closed)
        self.assertEqual(result["detail_field"]["official_category"],"fournitures")
        self.assertNotIn("refConsultation",str(result))

    def test_invalid_detail_link_does_not_open_page(self):
        class Ctx:
            async def new_page(self):
                raise AssertionError("should never be called")
        d=asyncio.run(inspect_one_public_detail(Ctx(),None))
        self.assertEqual(d["status"],"DETAIL_LINK_NOT_VERIFIED")

    def test_one_detail_link_must_be_allowlisted(self):
        class Page:
            url=BASE
            async def evaluate(self,script):
                return "https://evil.example/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=2"
        self.assertIsNone(asyncio.run(one_detail_link(Page())))


if __name__=="__main__":
    unittest.main()
