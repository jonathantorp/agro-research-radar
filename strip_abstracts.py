"""Never store/publicly deploy publisher abstracts in the GitHub repository.

Abstracts are read only into the ephemeral GitHub runner for editorial analysis.
Preserve the cryptographic digest so unchanged evaluations can be cached.
"""
import hashlib
import json
from pathlib import Path
p=Path(__file__).resolve().parent/'publications.json'
obj=json.loads(p.read_text('utf-8'))
count=0
for item in obj.get('publications',[]):
    a=item.pop('abstract',None)
    if a:
        item['abstract_digest']=hashlib.sha256(a.encode('utf-8')).hexdigest()[:20]
        count+=1
p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Removed {count} abstracts before public commit.')
