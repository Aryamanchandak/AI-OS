from __future__ import annotations
from dataclasses import dataclass
from datetime import date,timedelta
from typing import Protocol
import json
from urllib.request import Request,urlopen
from .models import Decision,DecisionStatus
class ObservationAdapter(Protocol):
    name:str
    def observations(self,decision:Decision)->list[str]:...
@dataclass
class StaticAdapter:
    values:dict[str,list[str]];name:str="static"
    def observations(self,decision:Decision)->list[str]:return self.values.get(decision.id,[])
@dataclass
class JSONFeedAdapter:
    name:str;url:str;transport:callable=lambda req:urlopen(req,timeout=20).read()
    def observations(self,decision:Decision)->list[str]:
        try:
            data=json.loads(self.transport(Request(self.url,headers={"User-Agent":"decision-tracker/0.1"})))
            rows=data if isinstance(data,list) else data.get("observations",[])
            return [str(x.get("text",x)) if isinstance(x,dict) else str(x) for x in rows]
        except Exception:return []
def scan(decisions:list[Decision],adapters:list[ObservationAdapter]=[])->list[dict]:
    alerts=[]
    for d in decisions:
        if d.status!=DecisionStatus.LIVE:continue
        if d.claim.resolution_date and d.claim.resolution_date<=date.today():alerts.append({"decision_id":d.id,"kind":"resolution_due","message":"Resolution date reached; human close required if no configured resolver."})
        elif d.claim.resolution_date and d.claim.resolution_date<=date.today()+timedelta(days=7):alerts.append({"decision_id":d.id,"kind":"due_soon","message":"Resolution is due within 7 days."})
        observations=[o for a in adapters for o in a.observations(d)]
        for f in d.reasoning.falsifiers:
            if any(f.lower() in o.lower() for o in observations):alerts.append({"decision_id":d.id,"kind":"falsifier","message":f})
    return alerts
