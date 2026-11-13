"""Local research desk HTTP boundary. Sources are supplied text, never arbitrary server paths."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .models import GradeRequest, LearningRequest, ResearchRequest
from .service import ResearchAssistant

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]
CLIENT = Path(__file__).parent / "client"


def assistant(request):
    return ResearchAssistant(request.app.state.runtime.graph)


@router.get("/")
@router.get("/research")
async def desk():
    return FileResponse(CLIENT / "index.html")


@router.get("/research/app.js")
async def script():
    return FileResponse(CLIENT / "app.js", media_type="text/javascript")


@router.get("/research/style.css")
async def style():
    return FileResponse(CLIENT / "style.css", media_type="text/css")


@router.get("/v1/research/example")
async def example():
    paths = [ROOT / "Assignment.md", ROOT / "S15Code/README.md", ROOT / "Lecture.md"]
    return {"question": "When does cheaper-model routing save money per resolved task?",
            "documents": [{"name": p.name, "text": p.read_text(encoding="utf-8")} for p in paths]}


@router.post("/v1/research/runs")
async def research(body: ResearchRequest, request: Request):
    return await assistant(request).research(body, request.app.state.gateway)


@router.get("/v1/research/runs/{run_id}")
async def read(run_id: str, request: Request):
    try:
        return assistant(request).read(run_id)
    except (KeyError, ValueError):
        raise HTTPException(404, "research run not found") from None


@router.post("/v1/research/cards")
async def cards(body: LearningRequest, request: Request):
    try:
        return await assistant(request).cards(body, request.app.state.gateway)
    except KeyError:
        raise HTTPException(404, "research run not found") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/v1/research/grade")
async def grade(body: GradeRequest, request: Request):
    try:
        return await assistant(request).grade(body, request.app.state.gateway)
    except KeyError:
        raise HTTPException(404, "study-card run not found") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
