import sys, unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scrape_pure as pure
import rate_ai as ai
from bs4 import BeautifulSoup

class RadarTests(unittest.TestCase):
    def test_page_with_link_and_title_metadata_no_abstract(self):
        detail = '''<html><head>
        <meta name="citation_title" content="New effects of nitrogen in Danish agriculture">
        <meta name="citation_author" content="Jane Jensen">
        <meta name="citation_publication_date" content="2026/10/21">
        <meta name="citation_doi" content="10.1111/example.2026.003">
        </head><body><h1>New effects of nitrogen in Danish agriculture</h1></body></html>'''
        with patch.object(pure, 'TODAY', date(2026,11,3)), patch.object(pure, 'CUTOFF', date(2026,8,3)):
            p=pure.get_publication(BeautifulSoup(detail,'html.parser'),'https://pure.au.dk/portal/en/publications/nitrogen-example/')
        self.assertEqual(p['date'],'2026-10-21')
        self.assertEqual(p['window'],'yes')
        self.assertEqual(p['evidence_type'],'title_metadata')
        self.assertEqual(p['confidence'],'lav')
        self.assertEqual(p['abstract'],'')
        self.assertEqual(p['scores'],[4,4,4,4])
    def test_month_precision_no_fake_day(self):
        dt,precision,_=pure.parse_date('2026/08')
        self.assertEqual(precision,'month')
        self.assertEqual(dt.isoformat(),'2026-08-01')
        with patch.object(pure, 'TODAY', date(2026,11,3)), patch.object(pure,'CUTOFF',date(2026,8,3)):
            self.assertEqual(pure.in_window(dt,precision),'possible')
    def test_ai_response_validation(self):
        good={'id':'abc','scores':[3,4,5,3],'angle':'Mulig vinkel','reason':'Begrundelse','caveat':'Forbehold','topic':'Kvælstof','contact':'Forsker','confidence':'lav'}
        self.assertTrue(ai.validate(good,{'abc'}))
        good['scores']=[6,4,4,4]
        self.assertFalse(ai.validate(good,{'abc'}))
    def test_link_discovery_deduplicates(self):
        html='''<a href="/portal/en/publications/foo/">Foo</a><a href="/portal/en/publications/foo/?lang=en">Foo</a>'''
        links=pure.publication_links(BeautifulSoup(html,'html.parser'))
        self.assertEqual(len(links),1)

if __name__=='__main__': unittest.main()
