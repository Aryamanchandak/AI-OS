from __future__ import annotations
import math,re
from collections import Counter
from .models import Decision
TOKEN=re.compile(r"[a-z0-9]+")
def text(d:Decision)->str:return " ".join([d.title,d.claim.statement,*d.domain,*d.reasoning.drivers,d.reasoning.key_assumption or "",*d.reasoning.falsifiers]).lower()
def recall(query:str,decisions:list[Decision],limit:int=3)->list[dict]:
    q=Counter(TOKEN.findall(query.lower())); out=[]
    for d in decisions:
        v=Counter(TOKEN.findall(text(d))); dot=sum(q[k]*v[k] for k in q); den=math.sqrt(sum(x*x for x in q.values())*sum(x*x for x in v.values()))
        if dot and den:out.append({"id":d.id,"title":d.title,"status":d.status.value,"similarity":dot/den,"outcome":d.resolution.outcome if d.resolution else None,"assumption":d.reasoning.key_assumption,"confidence":d.claim.probability})
    chosen=sorted(out,key=lambda x:x["similarity"],reverse=True)[:limit]
    resolved=[x for x in chosen if isinstance(x["outcome"],bool)]
    for x in chosen:x["peer_hit_rate"]=sum(bool(y["outcome"]) for y in resolved)/len(resolved) if resolved else None;x["peer_mean_confidence"]=sum(y["confidence"] for y in resolved if y["confidence"] is not None)/len([y for y in resolved if y["confidence"] is not None]) if any(y["confidence"] is not None for y in resolved) else None
    return chosen
