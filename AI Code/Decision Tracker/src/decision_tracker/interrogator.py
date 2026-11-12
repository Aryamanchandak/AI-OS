from __future__ import annotations
from .models import Decision

QUESTIONS=(
"How would a stranger check this on the resolution date?",
"What is the base rate and reference class?",
"What probability range would make you indifferent to either side?",
"Name the single observation that would make you abandon this.",
"What is the second-best option and why is it not first?",
"It is the resolution date and you were wrong. What most likely happened?",
)
def next_question(d:Decision,asked:int=0)->dict:
    complete=bool(d.claim.resolution_source and (d.claim.resolution_date or d.claim.resolution_triggers) and (d.claim.probability is not None or d.claim.distribution or d.claim.success_metric) and d.reasoning.falsifiers)
    if complete:return {"cleared":True,"question":None,"park":False}
    if asked>=6:return {"cleared":False,"question":None,"park":True}
    return {"cleared":False,"question":QUESTIONS[asked],"park":False,"number":asked+1}
