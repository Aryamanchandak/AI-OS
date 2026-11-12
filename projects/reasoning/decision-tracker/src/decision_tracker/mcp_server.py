from __future__ import annotations
import os
from .analytics import report
from .models import DecisionDraft,ResolutionInput
from .recall import recall
from .service import DecisionTracker

def create_server():
    try:from fastmcp import FastMCP
    except ImportError as e:raise RuntimeError("Install the MCP extra: uv sync --extra mcp") from e
    mcp=FastMCP("decision-tracker-mcp")
    def tracker():return DecisionTracker(os.getenv("DT_DB_PATH",".decision-tracker/decision_tracker.db"))
    @mcp.tool
    def log_decision(payload:dict)->dict:
        d=tracker().log(DecisionDraft.model_validate(payload));return {"id":d.id,"status":d.status.value}
    @mcp.tool
    def commit_decision(decision_id:str)->dict:return tracker().commit(decision_id).model_dump(mode="json",by_alias=True)
    @mcp.tool
    def query_decisions(statuses:list[str]|None=None)->list[dict]:return [d.model_dump(mode="json",by_alias=True) for d in tracker().store.list(statuses)]
    @mcp.tool
    def get_calibration()->dict:return report(tracker().store.list())
    @mcp.tool
    def resolve(decision_id:str,payload:dict)->dict:return tracker().resolve(decision_id,ResolutionInput.model_validate(payload)).model_dump(mode="json",by_alias=True)
    @mcp.tool
    def recall_decisions(query:str,limit:int=3)->list[dict]:return recall(query,tracker().store.list(),limit)
    return mcp
def main():create_server().run()
if __name__=="__main__":main()
