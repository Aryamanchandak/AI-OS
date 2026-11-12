from datetime import date,timedelta
from decision_tracker.analytics import report,wilson
from decision_tracker.graph import project
from decision_tracker.interrogator import next_question
from decision_tracker.recall import recall
from decision_tracker.watcher import scan
from test_tracker import forecast_draft
from decision_tracker.service import DecisionTracker

def test_interrogator_recall_graph_watcher_and_report(tmp_path):
    tracker=DecisionTracker(tmp_path/"roadmap.db")
    first=tracker.log(forecast_draft())
    assert next_question(first)["cleared"] is True
    live=tracker.commit(first.id)
    assert recall("falsifiable rates forecast",[live])[0]["id"]==live.id
    graph=project([live]);assert any(n["type"]=="Entity" for n in graph["nodes"])
    assert isinstance(scan([live]),list)
    summary=report([live]);assert summary["live"]==1 and summary["calibration"]==[]

def test_minimum_n_and_wilson():
    low,high=wilson(5,10)
    assert 0<low<.5<high<1
