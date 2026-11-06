import sys
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app
import build_data

class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = app.load_records()

    def test_extract_pdf_and_metadata(self):
        extracted = build_data.parse_pdf()
        self.assertEqual(len(extracted),13)
        self.assertEqual([sum(r['region']==region for r in extracted) for region in app.REGIONS], [1,3,9])
        for actual,coded in zip(extracted, self.records):
            self.assertEqual(actual['full_text'],coded['full_text'])
            self.assertEqual(actual['speaker'],coded['speaker'])
            self.assertTrue(actual['start_page']<=actual['end_page'])

    def test_all_quotes_grounded_in_pdf(self):
        for rec in self.records:
            for point in rec['points']:
                self.assertIn(point['excerpt'],rec['full_text'])
                self.assertIn(point['stance'],('긍정','부정'))

    def test_summary(self):
        summary=app.summarize(self.records)
        self.assertEqual(summary,{
            '정릉동':{'records':1,'positive':0,'negative':1},
            '길음동':{'records':3,'positive':0,'negative':3},
            '장위동':{'records':9,'positive':4,'negative':8},
        })

    def test_three_balanced_records(self):
        balanced=[r['id'] for r in self.records if len(r['stances'])>1]
        self.assertEqual(balanced,[5,6,13])

    def test_boundary_selection_validation(self):
        synthetic=[]
        for region,subdongs in app.REGIONS.items():
            for subdong in subdongs:
                synthetic.append({'type':'Feature','properties':{'adm_nm':f'서울특별시 성북구 {subdong}','adm_cd2':'1129062000'},'geometry':{'type':'Polygon','coordinates':[[[127,37.6],[127.01,37.6],[127.01,37.61],[127,37.6]]]}})
        synthetic.append({'type':'Feature','properties':{'adm_nm':'서울특별시 강동구 길음1동'},'geometry':{'type':'Polygon','coordinates':[[[127,37.6],[127.01,37.6],[127.01,37.61],[127,37.6]]]}})
        out=app.select_seongbuk_features(synthetic)
        self.assertEqual(len(out['features']),9)
        self.assertEqual(out['features'][0]['properties']['name'],'정릉1동')
        self.assertEqual(out['features'][-1]['properties']['name'],'장위3동')

    def test_no_assumed_precise_location(self):
        self.assertFalse(any('exact_subdong' in r or 'latitude' in r for r in self.records))

if __name__=='__main__':
    unittest.main()
