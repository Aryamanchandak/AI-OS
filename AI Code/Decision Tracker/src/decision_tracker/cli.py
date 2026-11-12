from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from .models import (
    Claim,
    DecisionClass,
    DecisionDraft,
    Reasoning,
    ResolutionInput,
    SourceClassification,
)
from .service import DecisionTracker, DecisionTrackerError
from .analytics import report
from .graph import project
from .interrogator import next_question
from .recall import recall
from .watcher import scan
from .integrations import LocalWhisperAdapter,TelegramAdapter,WhatsAppAdapter


app = typer.Typer(no_args_is_help=True, help="Pre-register and score falsifiable decisions.")


def tracker() -> DecisionTracker:
    return DecisionTracker(os.environ.get("DT_DB_PATH", ".decision-tracker/decision_tracker.db"))


def emit(value: object) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True)  # type: ignore[union-attr]
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False))


def fail(error: Exception) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(1)


@app.command("log")
def log_decision(
    entry: Annotated[
        str,
        typer.Argument(help="One-line claim, or the path to a complete JSON draft."),
    ],
    author: Annotated[str, typer.Option(help="Decision author.")] = "local-user",
    decision_class: Annotated[
        DecisionClass, typer.Option("--class", help="Decision class.")
    ] = DecisionClass.FORECAST,
    source_classification: Annotated[
        SourceClassification, typer.Option(help="Information source classification.")
    ] = SourceClassification.PUBLIC,
) -> None:
    """Capture a one-line DRAFT, or load a structured DRAFT from JSON."""
    try:
        input_file = Path(entry)
        if input_file.is_file():
            draft = DecisionDraft.model_validate_json(input_file.read_text(encoding="utf-8"))
        else:
            draft = DecisionDraft(
                author=author,
                **{"class": decision_class},
                source_classification=source_classification,
                title=entry,
                claim=Claim(statement=entry),
                reasoning=Reasoning(),
            )
        decision = tracker().log(draft)
        emit({"id": decision.id, "status": decision.status.value})
    except (OSError, ValidationError, DecisionTrackerError) as error:
        fail(error)


@app.command()
def commit(decision_id: str) -> None:
    """Pass the admission gate, lock the record, and activate it."""
    try:
        emit(tracker().commit(decision_id))
    except DecisionTrackerError as error:
        fail(error)


@app.command("open")
def open_decisions() -> None:
    """List DRAFT, COMMITTED, and LIVE decisions."""
    decisions = tracker().store.list(["DRAFT", "COMMITTED", "LIVE"])
    emit(
        [
            {"id": item.id, "status": item.status.value, "class": item.decision_class.value, "title": item.title}
            for item in decisions
        ]
    )


@app.command()
def show(decision_id: str) -> None:
    """Show the current projection of one decision."""
    try:
        emit(tracker().require(decision_id))
    except DecisionTrackerError as error:
        fail(error)


@app.command()
def resolve(
    decision_id: str,
    outcome: Annotated[str, typer.Option(help="For binary forecasts, use true or false.")],
    evidence: Annotated[str, typer.Option(help="Evidence supporting the resolution.")],
    resolver_source: Annotated[str | None, typer.Option(help="Required for FORECAST records.")] = None,
    automated: Annotated[bool,typer.Option(help="Assert resolution came from a configured resolver.")]=False,
) -> None:
    """Manually resolve a LIVE decision and score binary forecasts."""
    normalized: bool | float | str
    if outcome.lower() in {"true", "false"}:
        normalized = outcome.lower() == "true"
    else:
        try:
            normalized = float(outcome)
        except ValueError:
            normalized = outcome
    try:
        result = tracker().resolve(
            decision_id,
            ResolutionInput(
                outcome=normalized,
                evidence=evidence,
                resolver_source=resolver_source,
                automated=automated,
            ),
        )
        emit(result)
    except (ValidationError, DecisionTrackerError) as error:
        fail(error)


@app.command()
def score(decision_id: str) -> None:
    """Show the stored score for a resolved decision."""
    try:
        decision = tracker().require(decision_id)
        if decision.resolution is None:
            raise DecisionTrackerError("decision has not been resolved")
        emit(
            {
                "id": decision.id,
                "brier": decision.resolution.brier,
                "log_score": decision.resolution.log_score,
                "skill_vs_base_rate": decision.resolution.skill_vs_base_rate,
            }
        )
    except DecisionTrackerError as error:
        fail(error)


@app.command()
def verify() -> None:
    """Verify the append-only event and commit hash chains."""
    valid, message = tracker().store.verify()
    emit({"valid": valid, "message": message})
    if not valid:
        raise typer.Exit(1)


@app.command("rebuild")
def rebuild() -> None:
    """Rebuild the query projection entirely from the event log."""
    emit({"decisions_rebuilt": tracker().rebuild_projection()})

@app.command()
def interrogate(decision_id:str,asked:int=typer.Option(0,min=0,max=6))->None:
    """Return the next admission-gate question."""
    try:emit(next_question(tracker().require(decision_id),asked))
    except DecisionTrackerError as error:fail(error)

@app.command()
def recall_decisions(query:str,limit:int=typer.Option(3,min=1,max=20))->None:
    """Recall similar prior decisions from the local index."""
    emit(recall(query,tracker().store.list(),limit))

@app.command()
def watch()->None:
    """Scan live decisions for due dates and local triggers."""
    emit(scan(tracker().store.list()))

@app.command()
def retrospective()->None:
    """Produce deterministic weekly/calibration findings."""
    emit(report(tracker().store.list()))

@app.command("graph")
def graph_projection()->None:
    """Export the graph projection and correlated bets."""
    emit(project(tracker().store.list()))

@app.command()
def void(decision_id:str,reason:str=typer.Option(...))->None:emit(tracker().void(decision_id,reason))

@app.command()
def supersede(decision_id:str,replacement_id:str,reason:str=typer.Option(...))->None:emit(tracker().supersede(decision_id,replacement_id,reason))

@app.command()
def transcribe(audio:Path,model_size:str="small")->None:
    """Transcribe a local voice note; no decision fields are fabricated."""
    try:emit({"transcript":LocalWhisperAdapter(model_size).transcribe(audio)})
    except (RuntimeError,OSError) as error:fail(error)

@app.command("telegram-send")
def telegram_send(chat_id:str,text:str,token:str=typer.Option(...,envvar="TELEGRAM_BOT_TOKEN"))->None:
    """Send an intake acknowledgement or alert through Telegram."""
    emit(TelegramAdapter(token).send(chat_id,text))

@app.command("whatsapp-send")
def whatsapp_send(to:str,text:str,access_token:str=typer.Option(...,envvar="WHATSAPP_ACCESS_TOKEN"),phone_number_id:str=typer.Option(...,envvar="WHATSAPP_PHONE_NUMBER_ID"))->None:
    """Send an intake acknowledgement or alert through WhatsApp Cloud API."""
    emit(WhatsAppAdapter(access_token,phone_number_id).send(to,text))


if __name__ == "__main__":
    app()
