"""Gate 1A-04 stdlib-only tests for URL constraints and evidence judgement."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from category_evidence import (aggregate_samples, recognized_record, safe_detail_url,
                               inspect_public_cards, inspect_public_detail, sampled_detail_links,
                               inspect_few_details, CATEGORY_FIELDS_JS)
from filter_evidence_gate1a04 import evaluate_gate

BASE='https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch'
DETAIL='https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&id=182'

def row(value='fournitures', source='explicit_label_pair'):
    return {'status': 'EXPLICIT', 'category': value, 'source': source, 'field_pairs': 1}

def empty():
    return {'status':'MISSING', 'category':None, 'source':None, 'field_pairs':0}


class URLSafety(unittest.TestCase):
    def test_explicit_official_detail_allowed(self):
        self.assertEqual(safe_detail_url(DETAIL, BASE), DETAIL)
    def test_relative_official_detail_allowed(self):
        self.assertEqual(safe_detail_url('/index.php?page=entreprise.EntrepriseDetailsConsultation&id=182', BASE), DETAIL)
    def test_external_host_rejected(self):
        self.assertIsNone(safe_detail_url('https://evil.example/index.php?page=entreprise.EntrepriseDetailsConsultation', BASE))
    def test_url_info_rejected(self):
        self.assertIsNone(safe_detail_url('https://user:pw@www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation', BASE))
    def test_dce_route_rejected(self):
        self.assertIsNone(safe_detail_url('https://www.marchespublics.gov.ma/index.php?page=entreprise.DownloadDCE', BASE))
    def test_download_parameter_rejected(self):
        self.assertIsNone(safe_detail_url(DETAIL+'&downloadDCE=1', BASE))
    def test_fragment_rejected(self):
        self.assertIsNone(safe_detail_url(DETAIL+'#fragment',BASE))
    def test_invalid_scheme_rejected(self):
        self.assertIsNone(safe_detail_url('javascript:alert(1)',BASE))
    def test_missing_rejected(self):
        self.assertIsNone(safe_detail_url(None, BASE))
    def test_huge_url_rejected(self):
        self.assertIsNone(safe_detail_url(DETAIL+'x'*2000,BASE))


class SampleAggregation(unittest.TestCase):
    def test_no_inference_from_missing(self):
        sample=aggregate_samples([empty()]*5)
        self.assertEqual(sample.missing, 5)
        self.assertEqual(sample.matching, 0)
    def test_card_details_are_positionally_mapped(self):
        sample=aggregate_samples([row(),empty(),row(),empty(),empty()], [row(),row('travaux'),empty()])
        self.assertEqual(sample.matching, 3)
        self.assertEqual(sample.mismatching, 1)
        self.assertEqual(sample.missing, 1)
    def test_bad_source_cannot_be_trusted(self):
        self.assertIsNone(recognized_record(row(source='title_keyword'))[0])
    def test_wrong_value_is_detected(self):
        self.assertEqual(recognized_record(row('services'))[0], 'services')
    def test_ambiguous_not_evidence(self):
        self.assertEqual(recognized_record({'status':'AMBIGUOUS','category':'fournitures','source':'explicit_label_pair'})[1], 'NO_EXPLICIT_FIELD')
    def test_extra_detail_ignored(self):
        sample=aggregate_samples([row()], [row('travaux')])
        self.assertEqual(sample.matching,1)
        self.assertEqual(sample.details_checked,0)
    def test_report_fixed_categories_only(self):
        s=aggregate_samples([row(),empty()]).report()
        self.assertEqual(s['sample_categories'],['fournitures',None])


class GateLogic(unittest.TestCase):
    def check(self, cards=None, **kwargs):
        data={'selected':True,'retained':None,'search_response_seen':True,'result_transition_seen':False,
              'official_total':1338,'sample':aggregate_samples(cards if cards is not None else [row()]*5)}
        data.update(kwargs)
        return evaluate_gate(**data)
    def test_positive_sample_with_hidden_form(self):
        d=self.check()
        self.assertEqual(d.status,'SAMPLED_CONFIRMED')
        self.assertEqual(d.sample_size,5)
    def test_selected_only_unconfirmed(self):
        self.assertEqual(self.check(cards=[empty()]*5).status,'UNCONFIRMED')
    def test_wrong_category_overrides(self):
        self.assertEqual(self.check(cards=[row()]*4+[row('travaux')]).status,'CONTRADICTED')
    def test_unobserved_postback_rejected(self):
        self.assertEqual(self.check(search_response_seen=False).reason,'SEARCH_UPDATE_NOT_OBSERVED')
    def test_transition_can_replace_response(self):
        self.assertEqual(self.check(search_response_seen=False,result_transition_seen=True).status,'SAMPLED_CONFIRMED')
    def test_lost_filter_explicitly_rejected(self):
        self.assertEqual(self.check(retained=False).status,'CONTRADICTED')
    def test_missing_total_rejected(self):
        self.assertEqual(self.check(official_total=None).status,'UNCONFIRMED')
    def test_zero_total_rejected(self):
        self.assertEqual(self.check(official_total=0).status,'UNCONFIRMED')
    def test_bool_total_rejected(self):
        self.assertEqual(self.check(official_total=True).status,'UNCONFIRMED')
    def test_small_total_with_all_matching(self):
        self.assertEqual(self.check(cards=[row()]*3,official_total=3).status,'SAMPLED_CONFIRMED')
    def test_not_enough_cards(self):
        self.assertEqual(self.check(cards=[row()]*2).reason,'INSUFFICIENT_RESULT_CARDS')
    def test_unselected_rejected(self):
        self.assertEqual(self.check(selected=False).reason,'CATEGORY_NOT_SELECTED')
    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):self.check(minimum_sample=0)


class AsyncInterfaces(unittest.TestCase):
    def test_dom_scoped_to_cards(self):
        class P:
            async def evaluate(self,js,args):
                self.js,self.args=js,args
                return [row()]
        p=P()
        data=asyncio.run(inspect_public_cards(p,max_cards=5))
        self.assertEqual(len(data),1)
        self.assertIn(".tender_item",p.js)
        self.assertEqual(p.args['scope'],'cards')
    def test_detail_scoped_to_main_content(self):
        class P:
            async def evaluate(self,js,args):
                self.js=js
                return empty()
        p=P(); asyncio.run(inspect_public_detail(p))
        self.assertIn("#ctl0_CONTENU_PAGE",p.js)
    def test_sample_links_preserve_missing_position(self):
        class P:
            url=BASE
            async def evaluate(self,js,args):return [DETAIL,None,DETAIL]
        self.assertEqual(asyncio.run(sampled_detail_links(P())),[DETAIL,None,DETAIL])
    def test_invalid_card_limit(self):
        with self.assertRaises(ValueError):asyncio.run(inspect_public_cards(None,max_cards=100))
    def test_details_unknown_url_not_opened(self):
        class C:
            async def new_page(self):raise AssertionError('No open')
        data=asyncio.run(inspect_few_details(C(), [None]))
        self.assertEqual(data[0]['reason'],'UNSAFE_URL')
    def test_no_raw_page_text_to_report(self):
        self.assertNotIn('document.body.innerHTML', CATEGORY_FIELDS_JS)
        self.assertIn('explicit_label_pair',CATEGORY_FIELDS_JS)

if __name__=='__main__':unittest.main()