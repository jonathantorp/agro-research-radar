#!/usr/bin/env python3
"""Optional OpenAI editorial assessments of public Pure metadata.

Without OPENAI_API_KEY the source's rule-based candidate scores remain visibly marked.
No full texts, internal documents, or credentials are ever sent to the provider.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import requests

ROOT = Path(__file__).resolve().parent
MODEL = os.getenv('OPENAI_MODEL', 'gpt-6-luna')
API_KEY = os.getenv('OPENAI_API_KEY', '').strip()
PATH = ROOT / 'publications.json'
SYNC = ROOT / 'sync.json'

SYSTEM = '''Du er redaktør i forskningskommunikation ved Institut for Agroøkologi, Aarhus Universitet.
Du vurderer KOMMUNIKATIONSPOTENTIALE – aldrig forskningens faglige kvalitet.
Analyser KUN ud fra verificerede metadata og evt. abstract i input. Opfind aldrig resultater, data, forskertilknytning, journalister, presseomtale eller bevis for nyhedsværdi.
Ved manglende abstract skal du ALLIGEVEL vurdere titel/forfatter/metadata – sænk sikkerheden og gør den foreslåede vinkel til et spørgsmål, der skal undersøges, ikke en faktapåstand.
Vær kræsen: ikke alle artikler skal have 4 eller 5. Vurder disse fire kriterier 1–5 i PRÆCIS rækkefølge: nyhedsværdi, samfundsrelevans, aktualitet, formidlingspotentiale.
Svar KUN gyldig JSON som et objekt {"items": [{"id": str, "scores": [int,int,int,int], "angle": str, "reason": str, "caveat": str, "topic": str, "confidence": "lav"|"middel", "contact": str}] }.
Skriv felterne angle, reason, caveat og topic på konkret og naturligt dansk. Maks. to sætninger i hvert fritekstfelt. Kontakt kun en faktisk nævnt forfatter eller skriv 'Afklares i Pure'.
Ingen interne AU-data. Du kan ikke kontrollere om artiklen allerede er presseomtalt, og du må ikke hævde det.
'''

def fingerprint(p):
    # Change only when the verifiable evidence changes, not when the date of scraping changes.
    fields=[p.get(x,'') for x in ('title','authors','date','journal','type','evidence_type')]+[p.get('abstract_digest') or hashlib.sha256(p.get('abstract','').encode()).hexdigest()[:20]]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False).encode()).hexdigest()[:20]

def in_radar(p):
    return p.get('window') in ('yes','possible')

def batch_request(batch):
    items=[]
    for p in batch:
        items.append({'id':p['id'],'title':p.get('title',''),'authors':p.get('authors',''),
                      'publication_date':p.get('date',''),'publication_type':p.get('type',''),
                      'journal':p.get('journal',''),'abstract':(p.get('abstract') or '')[:4500],
                      'basis':'abstract' if p.get('abstract') else 'title_metadata'})
    payload={
        'model':MODEL,
        'messages':[{'role':'system','content':SYSTEM},
                    {'role':'user','content':'Vurdér publikationerne. Returnér præcis én item pr. id. '+json.dumps(items,ensure_ascii=False)}],
        'max_completion_tokens':2600,
    }
    # GPT-6 Luna: simple structured editorial classification, no reasoning tokens required.
    if MODEL.startswith('gpt-6'):
        payload['reasoning_effort']='none'
    payload['response_format']={'type':'json_object'}
    res=requests.post('https://api.openai.com/v1/chat/completions',
        headers={'Authorization':'Bearer '+API_KEY,'Content-Type':'application/json'},
        json=payload,timeout=110)
    res.raise_for_status()
    response=res.json()
    content=response['choices'][0]['message']['content']
    if isinstance(content,list):
        content=''.join(b.get('text','') for b in content if isinstance(b,dict))
    content=str(content).strip()
    if content.startswith('```'):
        content=content.split('\n',1)[1].rsplit('```',1)[0].strip()
    data=json.loads(content)
    return data['items']

def validate(item, valid_ids):
    if not isinstance(item,dict) or item.get('id') not in valid_ids: return False
    scores=item.get('scores')
    if not (isinstance(scores,list) and len(scores)==4 and all(type(n) is int and 1<=n<=5 for n in scores)): return False
    if any(not isinstance(item.get(k),str) or len(item[k])>900 for k in ('angle','reason','caveat','topic','contact')): return False
    return item.get('confidence') in ('lav','middel')

def main():
    data=json.loads(PATH.read_text('utf-8'))
    sync=json.loads(SYNC.read_text('utf-8'))
    active=[p for p in data['publications'] if in_radar(p)]
    if not API_KEY:
        sync.update({'ai_status':'not_configured', 'ai_message':'OPENAI_API_KEY mangler; regelbaserede scorer bevares. Ingen automatisk AI-vurdering.'})
        SYNC.write_text(json.dumps(sync,ensure_ascii=False,indent=2),encoding='utf-8')
        print('AI ikke aktiveret: ingen API-nøgle. Regelbaserede kandidatscorer anvendes.')
        return
    # Editorial seed ratings should not automatically be overwritten unless newly scraped evidence is present.
    candidates=[]
    for p in active:
        fp=fingerprint(p)
        if p.get('ai_fingerprint')==fp and p.get('ai_model')==MODEL:
            continue
        if p.get('source')=='Redaktionel pilotvurdering' and not p.get('discovered_at'):
            continue
        candidates.append(p)
    done=0;errors=[]
    for index in range(0,len(candidates),5):
        subset=candidates[index:index+5]
        try:
            rated=batch_request(subset)
            valid={p['id'] for p in subset}
            verified={x['id']:x for x in rated if validate(x,valid)}
            for p in subset:
                x=verified.get(p['id'])
                if x is None:
                    errors.append('Manglende/ugyldig vurdering af '+p['id']);continue
                for k in ('scores','angle','reason','caveat','topic','contact'):
                    p[k]=x[k]
                p['rating']=round(sum(x['scores'])/4,2)
                p['confidence']='lav' if not p.get('abstract') else x['confidence']
                p['source']='AI-vurdering (OpenAI) – kræver redaktionel kontrol'
                p['evidence']='Kun titel/forfatter/metadata – lav sikkerhed' if not p.get('abstract') else 'Abstract og offentlige metadata – redaktionel kontrol nødvendig'
                p['ai_fingerprint']=fingerprint(p)
                p['ai_model']=MODEL
                p['reviewed_at']=dt.date.today().isoformat()
                done+=1
        except Exception as exc:
            errors.append(type(exc).__name__+': '+str(exc)[:180])
        # Persist partial progress, to allow safe next-week retries.
        PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        if index+5<len(candidates):time.sleep(1)
    sync.update({'ai_status':'partial' if errors else 'complete',
                 'ai_last_attempt':dt.date.today().isoformat(),
                 'ai_model':MODEL,'ai_scored_this_run':done,
                 'ai_remaining':len(candidates)-done,
                 'ai_message':f'AI-vurderinger: {done} nye/ændrede. '+('; '.join(errors[:3]) if errors else 'Alle valgte vurderinger gennemført.')})
    SYNC.write_text(json.dumps(sync,ensure_ascii=False,indent=2),encoding='utf-8')
    print(sync['ai_message'])
    # Failure to rate is explicitly visible in sync and should not suppress the dashboard itself.

if __name__=='__main__': main()
