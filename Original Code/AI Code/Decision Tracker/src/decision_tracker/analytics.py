from __future__ import annotations
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean
from .models import ClaimType, Decision, DecisionClass, DecisionStatus

def wilson(successes:int,n:int,z:float=1.96)->tuple[float,float]:
    if not n:return (0.0,0.0)
    p=successes/n; d=1+z*z/n; c=(p+z*z/(2*n))/d
    m=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/d
    return max(0,c-m),min(1,c+m)

def calibration(decisions:list[Decision], minimum_n:int=20)->list[dict]:
    buckets:dict[int,list[Decision]]=defaultdict(list)
    for d in decisions:
        if d.status==DecisionStatus.RESOLVED and d.decision_class==DecisionClass.FORECAST and d.claim.type==ClaimType.BINARY and d.claim.probability is not None and d.resolution and isinstance(d.resolution.outcome,bool) and not d.backfilled:
            buckets[min(9,int(d.claim.probability*10))].append(d)
    result=[]
    for b,items in sorted(buckets.items()):
        if len(items)<minimum_n:continue
        wins=sum(bool(x.resolution.outcome) for x in items); lo,hi=wilson(wins,len(items))
        result.append({"bucket":f"{b*10}-{(b+1)*10}%","n":len(items),"declared":mean(x.claim.probability for x in items),"realised":wins/len(items),"wilson_low":lo,"wilson_high":hi})
    return result

def murphy(decisions:list[Decision],minimum_n:int=30)->dict|None:
    rows=[d for d in decisions if d.resolution and d.resolution.brier is not None and isinstance(d.resolution.outcome,bool) and not d.backfilled]
    if len(rows)<minimum_n:return None
    overall=mean(int(d.resolution.outcome) for d in rows); groups:dict[float,list[Decision]]=defaultdict(list)
    for d in rows:groups[round(d.claim.probability or 0,1)].append(d)
    reliability=sum(len(g)/len(rows)*(p-mean(int(x.resolution.outcome) for x in g))**2 for p,g in groups.items())
    resolution=sum(len(g)/len(rows)*(mean(int(x.resolution.outcome) for x in g)-overall)**2 for g in groups.values())
    uncertainty=overall*(1-overall)
    return {"n":len(rows),"reliability":reliability,"resolution":resolution,"uncertainty":uncertainty,"brier":reliability-resolution+uncertainty}

def report(decisions:list[Decision])->dict:
    resolved=[d for d in decisions if d.status==DecisionStatus.RESOLVED]
    scored=[d.resolution.brier for d in resolved if d.resolution and d.resolution.brier is not None and not d.backfilled]
    due=[d.id for d in decisions if d.status==DecisionStatus.LIVE and d.claim.resolution_date and d.claim.resolution_date<=date.today()+timedelta(days=7)]
    wrong=[d for d in resolved if d.resolution and d.resolution.attribution and "WRONG" in d.resolution.attribution.value]
    exogenous=sum("EXOGENOUS" in d.resolution.failure_tags for d in wrong if d.resolution)/len(wrong) if wrong else None
    pairs=[(d.process.process_score,1-float(d.resolution.brier)) for d in resolved if d.resolution and d.resolution.brier is not None]
    process_slope=_slope(pairs) if len(pairs)>=20 else None
    sizing=[(d.claim.probability,d.action.size_bps_risk) for d in decisions if d.claim.probability is not None and d.action and d.action.size_bps_risk is not None]
    red=[d for d in resolved if d.red_team and d.resolution and d.resolution.brier is not None];plain=[d for d in resolved if not d.red_team and d.resolution and d.resolution.brier is not None]
    sources=defaultdict(set)
    for d in decisions:
        if d.reasoning.base_rate:sources[d.title.lower()].add(d.reasoning.base_rate.source)
    return {"total":len(decisions),"live":sum(d.status==DecisionStatus.LIVE for d in decisions),"resolved":len(resolved),"mean_brier":mean(scored) if scored else None,"calibration":calibration(decisions),"murphy":murphy(decisions),"due_next_7_days":due,"exogenous_rate":exogenous,"exogenous_warning":exogenous is not None and exogenous>.15,"process_outcome_slope":process_slope,"sizing_confidence_slope":_slope(sizing) if len(sizing)>=20 else None,"red_team_brier_delta":mean(d.resolution.brier for d in red)-mean(d.resolution.brier for d in plain) if red and plain else None,"reference_class_drift":[k for k,v in sources.items() if len(v)>1],"cadence":{"weekly":{"resolved":len(resolved),"due":due},"monthly":{"mean_brier":mean(scored) if scored else None},"quarterly":{"murphy":murphy(decisions),"process_outcome_slope":process_slope}}}

def _slope(rows:list[tuple[float,float]])->float|None:
    if len(rows)<2:return None
    mx=mean(x for x,_ in rows);my=mean(y for _,y in rows);den=sum((x-mx)**2 for x,_ in rows)
    return sum((x-mx)*(y-my) for x,y in rows)/den if den else None
