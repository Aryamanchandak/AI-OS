from __future__ import annotations
from collections import defaultdict
from .models import Decision,DecisionStatus
def project(decisions:list[Decision])->dict:
    nodes=[];edges=[]; assumptions:dict[str,list[str]]=defaultdict(list)
    for d in decisions:
        nodes.append({"id":d.id,"type":"Decision","label":d.title})
        for domain in d.domain:
            eid=f"entity:{domain.lower()}";nodes.append({"id":eid,"type":"Entity","label":domain});edges.append({"from":d.id,"to":eid,"type":"RELATES_TO"})
        if d.reasoning.key_assumption:
            aid=f"assumption:{d.reasoning.key_assumption.lower()}";nodes.append({"id":aid,"type":"Assumption","label":d.reasoning.key_assumption});edges.append({"from":d.id,"to":aid,"type":"DEPENDS_ON"})
            if d.status==DecisionStatus.LIVE:assumptions[d.reasoning.key_assumption].append(d.id)
        for source in d.reasoning.source_refs:
            sid=f"source:{source}";nodes.append({"id":sid,"type":"Source","label":source});edges.append({"from":d.id,"to":sid,"type":"CITES"})
        if d.supersedes_id:edges.append({"from":d.id,"to":d.supersedes_id,"type":"SUPERSEDES"})
        for other in d.contradicts_ids:edges.append({"from":d.id,"to":other,"type":"CONTRADICTS"})
    for ids in assumptions.values():
        for i,left in enumerate(ids):
            for right in ids[i+1:]:edges.append({"from":left,"to":right,"type":"SHARES_ASSUMPTION_WITH"})
    unique={n["id"]:n for n in nodes}
    return {"nodes":list(unique.values()),"edges":edges,"correlated_bets":[{"assumption":a,"decisions":ids} for a,ids in assumptions.items() if len(ids)>=2]}

def neo4j_cypher(graph:dict)->list[str]:
    lines=[]
    for n in graph["nodes"]:lines.append(f"MERGE (n:{n['type']} {{id: {n['id']!r}}}) SET n.label = {n['label']!r}")
    return lines
