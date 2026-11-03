#!/usr/bin/env python3
"""Best-effort public AGRO Pure harvester (weekly, rolling 3 calendar months).

No bypasses, no logins, and no claim of complete coverage if the site is inaccessible.
Ratings created by this Python job are intentionally RULE-BASED and provisional.
The separate weekly ChatGPT Research Radar task performs editorial/AI analysis.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import time
import unicodedata
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

ROOT = pathlib.Path(__file__).resolve().parent
BASE = 'https://pure.au.dk'
LIST_URL = f'{BASE}/portal/da/organisations/department-of-agroecology/publications/'
USER_AGENT = 'AGRO-ResearchRadar-Pilot/0.2 (public-metadata; once-weekly; request access from AU for production use)'
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': USER_AGENT, 'Accept': 'text/html,application/xhtml+xml'})
TODAY = dt.datetime.now(dt.timezone.utc).date()
CUTOFF = TODAY - relativedelta(months=3)

KEYWORDS = {
    'Kvælstof': ['nitrogen', 'nitrate', 'nitrat', 'kvælstof', 'fertiliz', 'gødning', 'ammonia', 'nutrient'],
    'Klima og emissioner': ['nitrous oxide', 'n2o', 'greenhouse', 'emission', 'methane', 'carbon footprint', 'ghg'],
    'Skov og klima': ['afforestation', 'reforestation', 'forestry', 'forest', 'skovrejsning', 'carbon storage'],
    'Energi og landbrug': ['agrivolt', 'photovoltaic', 'solar panel', 'solcelle'],
    'AI og planteavl': ['machine learning', 'artificial intelligence', 'deep learning', 'ai-designed', 'predictive model'],
    'Jord og miljø': ['soil', 'jord', 'microplastic', 'compaction', 'erosion', 'water retention'],
    'Plantebeskyttelse': ['pesticide', 'fungicide', 'blight', 'pathogen', 'weed', 'herbicide'],
    'Grøn omstilling': ['agroecology', 'living lab', 'sustainab', 'transformation', 'biodivers'],
}
NEWS_HINTS = ['new', 'novel', 'first', 'unexpected', 'evidence', 'effects', 'impacts', 'global', 'denmark', 'danish', 'risk', 'reduction', 'increase', 'decrease', 'model']
DANISH_MONTHS = {'jan':1,'feb':2,'mar':3,'apr':4,'maj':5,'jun':6,'jul':7,'aug':8,'sep':9,'okt':10,'nov':11,'dec':12}
ENGLISH_MONTHS = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}

def atomic_json(path, obj):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')
    tmp.replace(path)

def normalized_url(u):
    p=urlparse(u)
    return p._replace(fragment='', query='').geturl().rstrip('/')+'/'

def robots_checker():
    try:
        r=SESSION.get(BASE+'/robots.txt', timeout=15)
        if r.status_code!=200:
            raise RuntimeError(f'Robots.txt ikke tilgængelig (HTTP {r.status_code}), scraping afbrydes')
        rob=RobotFileParser(); rob.parse(r.text.splitlines())
        if not rob.can_fetch(USER_AGENT, LIST_URL):
            raise RuntimeError('AU Pure robots.txt tillader ikke denne publikationsovervågning')
        return rob
    except requests.RequestException as exc:
        raise RuntimeError('Robots.txt kunne ikke kontrolleres: '+str(exc)) from exc

def fetch(url, robots):
    if not robots.can_fetch(USER_AGENT, url):
        raise RuntimeError('robots.txt tillader ikke at hente: '+url)
    try: r=SESSION.get(url,timeout=30)
    except requests.RequestException as exc: raise RuntimeError('Kunne ikke hente '+url+': '+str(exc)) from exc
    if r.status_code!=200:
        raise RuntimeError(f'Pure afviste {url} (HTTP {r.status_code})')
    if len(r.content)<300: raise RuntimeError('For lidt HTML på '+url)
    return BeautifulSoup(r.text,'html.parser')

def publication_links(soup):
    out=[]
    for a in soup.select('a[href]'):
        href=urljoin(BASE,a.get('href',''))
        p=urlparse(href)
        if p.netloc!='pure.au.dk' or not re.search(r'^/portal/(da|en)/publications/[^/]+', p.path):
            continue
        u=normalized_url(href)
        if u not in out:out.append(u)
    return out

def get_meta(soup,key):
    a=soup.find('meta',attrs={'name':key}) or soup.find('meta',attrs={'property':key})
    return (a.get('content') or '').strip() if a else ''

def parse_date(raw):
    """Returns (date, precision, uncertain). No invented days on incomplete dates."""
    raw=raw.strip().lower().replace('/', '-')
    m=re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})',raw)
    if m:
        try:return dt.date(*map(int,m.groups())), 'day', False
        except ValueError:return None,'unknown',True
    m=re.match(r'^(\d{4})-(\d{1,2})$',raw)
    if m:
        try:return dt.date(int(m[1]),int(m[2]),1),'month',True
        except ValueError:return None,'unknown',True
    m=re.match(r'^(\d{4})$',raw)
    if m:return dt.date(int(m[1]),1,1),'year',True
    m=re.search(r'(?:(\d{1,2})\s+)?([a-zæøå]{3,10})\.?\s+(\d{4})',raw)
    if m:
        mm={**ENGLISH_MONTHS,**DANISH_MONTHS}.get(m[2][:3])
        if mm:
            try:return dt.date(int(m[3]),mm,int(m[1] or 1)),'day' if m[1] else 'month',not bool(m[1])
            except ValueError:pass
    return None,'unknown',True

def in_window(d,precision):
    if d is None:return 'unknown'
    if precision=='day':return 'yes' if CUTOFF<=d<=TODAY else 'no'
    if precision=='month':
        last=d+relativedelta(months=1)-dt.timedelta(days=1)
        return 'possible' if last>=CUTOFF and d<=TODAY else 'no'
    if precision=='year':
        last=dt.date(d.year,12,31)
        return 'possible' if last>=CUTOFF and d<=TODAY else 'no'
    return 'unknown'

def extract_abstract(soup):
    for key in ('citation_abstract','dc.description','DC.description','description'):
        value=get_meta(soup,key)
        if value and len(value)>120 and not value.lower().startswith('read more'):
            return value[:5000]
    for heading in soup.select('h2,h3,h4'):
        if heading.get_text(' ',strip=True).lower() in ('abstract','abstrakt','summary','resumé'):
            texts=[]
            for node in heading.next_siblings:
                if getattr(node,'name',None) in ('h2','h3','h4'):break
                if hasattr(node,'get_text'):texts.append(node.get_text(' ',strip=True))
                if len(' '.join(texts))>5000:break
            if len(' '.join(texts))>80:return ' '.join(texts)[:5000]
    return ''

def provisional_scores(title,authors,abstract,topic):
    """Meaningfully varied but purely rule-based; NEVER call these AI scores."""
    t=title.lower(); a=abstract.lower()
    topical=3 if topic!='Andet' else 2
    novelty=3+int(any(k in t for k in NEWS_HINTS))
    novelty=max(1,min(5,novelty))
    societal=3+int(topic in ('Kvælstof','Klima og emissioner','Plantebeskyttelse','Skov og klima','Energi og landbrug'))
    topicality=3+int(any(k in t for k in ('denmark','danish','policy','regulat','emission','forest','pesticide','nitrogen')))
    accessible=3+int(len(title)<120 and any(k in t for k in ('effect','impact','risk','reduce','new','increase','change')))
    if a:
        # Abstract changes only evidence strength, not automatic assumption of positive results.
        novelty+=int(any(k in a for k in ('we found','we show','our results','we demonstrate')))
    scores=[min(5,novelty),min(5,societal),min(5,topicality),min(5,accessible)]
    return scores

def get_publication(soup,url):
    title=get_meta(soup,'citation_title') or (soup.find('h1').get_text(' ',strip=True) if soup.find('h1') else '')
    if not title:return None
    d_raw=get_meta(soup,'citation_online_date') or get_meta(soup,'citation_publication_date') or get_meta(soup,'dc.date')
    if not d_raw:
        text=soup.get_text(' ',strip=True)
        mt=re.search(r'\b(?:[1-3]?\d\s+)?(?:jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)[a-zæøå]*\.?\s+20\d\d',text,re.I)
        if mt:d_raw=mt.group()
    d,precision,_=parse_date(d_raw)
    window=in_window(d,precision)
    journal=get_meta(soup,'citation_journal_title')
    authors=[a.get('content','') for a in soup.find_all('meta',attrs={'name':'citation_author'}) if a.get('content')]
    if not authors:
        a=get_meta(soup,'dc.creator')
        if a:authors=[a]
    abstract=extract_abstract(soup)
    doi=get_meta(soup,'citation_doi')
    if doi.startswith('https://doi.org/'):doi=doi.split('doi.org/')[-1]
    if not doi:
        mt=re.search(r'10\.\d{4,9}/[^\s<>"\']+',soup.get_text(' ',strip=True))
        if mt:doi=mt.group().strip('.,;)')
    ident=doi.lower() if doi else hashlib.sha1(normalized_url(url).encode()).hexdigest()[:20]
    search=(title+' '+abstract[:2500]).lower()
    topic=max(KEYWORDS,key=lambda k:sum(w in search for w in KEYWORDS[k]))
    if not any(w in search for w in KEYWORDS[topic]):topic='Andet'
    scores=provisional_scores(title,authors,abstract,topic)
    articletype='Review' if 'review' in (get_meta(soup,'citation_article_type')+' '+title).lower() else 'Afventer typekontrol'
    evidence_type='abstract' if abstract else 'title_metadata'
    date_label=d.isoformat() if d and precision=='day' else (d.strftime('%Y-%m') if d and precision=='month' else d.strftime('%Y') if d else 'Ukendt')
    contact=authors[0] if authors else 'AGRO-forsker: verificeres i Pure'
    return {
        'id':ident,'title':title,'date':date_label,'date_precision':precision,'publication_date_raw':d_raw,
        'window':window,'journal':journal,'type':articletype,'topic':topic,'authors':', '.join(authors[:6])+(' m.fl.' if len(authors)>6 else ''),
        'url':url,'doi':doi,'scores':scores,'rating':round(sum(scores)/4,2),
        'angle':f'Undersøg nyhedspotentialet i "{title}" og spørg forskeren til resultaternes konkrete betydning.',
        'reason':'Foreløbig nøgleords- og metadatabaseret prioritering; ingen AI-fortolkning eller faglig vurdering udført.',
        'caveat':'Resultater kan ikke fastslås af titlen. Kræver faglig vurdering, kildekontrol og evt. abstract før publicering.',
        'contact':contact,'status':'Ikke vurderet','coverage':'Ukendt',
        'source':'Automatisk indsamlet – regelbaseret kandidat-rating (IKKE AI)',
        'evidence':('Abstract tilgængeligt (automatisk ikke fagligt analyseret)' if abstract else 'Kun titel/forfatter/metadata – lav sikkerhed'),
        'evidence_type':evidence_type,'confidence':'lav' if not abstract else 'middel',
        'abstract_available':bool(abstract),'abstract_digest':hashlib.sha256(abstract.encode('utf-8')).hexdigest()[:20] if abstract else '', 'abstract':abstract, 'discovered_at':TODAY.isoformat(),
    }

def editorial_fingerprint(p):
    fields=[p.get(x,'') for x in ('title','authors','date','journal','type','evidence_type')]+[
      p.get('abstract_digest') or hashlib.sha256(p.get('abstract','').encode()).hexdigest()[:20]]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()[:20]

def run(max_pages,delay):
    robots=robots_checker()
    existing=json.loads((ROOT/'publications.json').read_text(encoding='utf8'))
    rows=existing.get('publications',[])
    byid={p['id'].lower():p for p in rows if p.get('id')}
    byurl={normalized_url(p['url']):p for p in rows if p.get('url')}
    listed=[];pages_scanned=0;stopped='';duplicates=0
    # Scan the WHOLE relevant section: Pure lists results by publication year then TITLE.
    # Never stop after 3 pages or 25 new items like the first demo.
    for page in range(max_pages):
        url=LIST_URL+('?page='+str(page) if page else '')
        soup=fetch(url,robots)
        links=publication_links(soup)
        pages_scanned+=1
        if not links:
            if page==0:raise RuntimeError('Fandt ingen publikationslinks på startsiden')
            stopped='End of pagination: no links';break
        newlinks=[x for x in links if x not in listed]
        if not newlinks:
            stopped='End of pagination: links repeated';break
        listed.extend(newlinks)
        # Once the list has passed all potentially eligible YEARS, stop.
        # Be conservative: examine a full page's year headings, not individual dates.
        years=[int(h.get_text(' ',strip=True)) for h in soup.select('h2,h3,h4') if re.fullmatch(r'20\d\d',h.get_text(' ',strip=True))]
        if years and max(years)<CUTOFF.year:
            stopped='Passed eligible publication years';break
        time.sleep(delay)
    if not stopped:stopped='Page safety cap reached; coverage unverified'
    examined=0;newcount=0;eligible=[];uncertain=[];detail_errors=[]
    for url in listed:
        old=byurl.get(url)
        if old and old.get('date_precision')=='day' and old.get('window')=='no':
            continue
        try:
            # Verify metadata and dates anew each week. The abstract is transient and
            # removed before public data is committed to the repository.
            soup=fetch(url,robots); p=get_publication(soup,url);examined+=1
            if not p:detail_errors.append(url);continue
        except Exception as e:
            detail_errors.append(f'{url}: {str(e)[:100]}')
            continue
        time.sleep(delay)
        # Recalculate window on every run, including previously collected papers.
        d,precision,_=parse_date(str(p.get('date','')))
        p['window']=in_window(d,p.get('date_precision',precision))
        if p['window'] not in ('yes','possible'):
            continue
        if p['window']=='possible':uncertain.append(p)
        canonical=p['id'].lower()
        if canonical in byid:
            orig=byid[canonical]
            if orig is not p:
                # Preserve manual editorial score/status but refresh metadata/evidence.
                source=orig.get('source','')
                editorial='Redaktionel pilotvurdering' in source
                ai_unchanged=('AI-vurdering' in source and orig.get('ai_fingerprint') and
                              orig.get('ai_fingerprint') == editorial_fingerprint(p))
                protected={'status','coverage','notes'}
                if editorial or ai_unchanged:
                    protected |= {'scores','rating','angle','reason','caveat','contact','source','reviewed_at','topic','confidence','evidence'}
                else:
                    # Underlying source changed: old AI score is no longer current.
                    orig.pop('ai_fingerprint',None)
                    orig.pop('ai_model',None)
                for k,v in p.items():
                    if k not in protected:orig[k]=v
            eligible.append(orig)
        elif normalized_url(p['url']) in byurl:
            duplicates+=1
            eligible.append(byurl[normalized_url(p['url'])])
        else:
            rows.append(p);byid[canonical]=p;byurl[normalized_url(p['url'])]=p;eligible.append(p);newcount+=1
    # Keep one row per persistent identifier. Keep only rolling-window papers in the RADAR,
    # while old records remain in history for de-duplication on future runs.
    seen=set();unique=[]
    for p in eligible:
        key=p['id'].lower()
        if key not in seen:unique.append(p);seen.add(key)
    status='complete_candidate' if stopped!='Page safety cap reached; coverage unverified' and not detail_errors else 'partial'
    if status=='complete_candidate':
        # Still cannot PROVE complete coverage without a reconciliation against Pure export.
        status='unverified'
    out={**existing,'publications':rows,'last_attempt':TODAY.isoformat(),'last_success':TODAY.isoformat(),
         'ingestion_status':status,'window_start':CUTOFF.isoformat(),'window_end':TODAY.isoformat(),
         'description':'Kandidatoversigt baseret på offentligt tilgængelige Pure-sider. Fuldstændighed ikke verificeret mod AU-eksport.'}
    atomic_json(ROOT/'publications.json',out)
    sync={'status':status,'last_attempt':TODAY.isoformat(),'last_success':TODAY.isoformat(),
          'window_start':CUTOFF.isoformat(),'window_end':TODAY.isoformat(),'pages_scanned':pages_scanned,
          'publication_links':len(listed),'details_fetched':examined,'in_window':len(unique),
          'uncertain_dates':len(uncertain),'abstracts_missing':sum(not p.get('abstract_available') for p in unique),'new':newcount,'detail_failures':len(detail_errors),'stop_reason':stopped,
          'message':f'{len(unique)} kandidater i tremånedersvinduet, {len(uncertain)} med usikker dato. Fuldstændighed IKKE verificeret; scorer er regelbaserede, medmindre AI-vurdering er bekræftet separat.'}
    atomic_json(ROOT/'sync.json',sync)
    print(json.dumps(sync,ensure_ascii=False,indent=2))
    if status=='partial':sys.exit(2)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--max-pages',type=int,default=100,help='Safety ceiling, not a 3-page sample; incomplete if reached')
    ap.add_argument('--delay',type=float,default=1.0,help='Seconds between requests')
    args=ap.parse_args()
    try:run(max(1,min(args.max_pages,300)),max(.5,args.delay))
    except Exception as e:
        previous={}
        try:previous=json.loads((ROOT/'sync.json').read_text(encoding='utf8'))
        except Exception:pass
        atomic_json(ROOT/'sync.json',{'status':'error','last_attempt':TODAY.isoformat(),
          'last_success':previous.get('last_success'),'window_start':CUTOFF.isoformat(),
          'window_end':TODAY.isoformat(),'message':str(e)[:450]})
        print('Pure scrape failed; preserved previous publications:',e,file=sys.stderr)
        sys.exit(1)
