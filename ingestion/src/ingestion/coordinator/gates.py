from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol, cast

from ingestion.coordinator.errors import IllegalDecisionError
from ingestion.coordinator.state import DecisionRequest, PendingDecision
from ingestion.intake.base import IntakeResult
from ingestion.intake.extractors import ImageExtractor
from ingestion.intake.extractors.image import IMAGE_EXTENSIONS
from ingestion.intake.funnel import PreparedFile
from ingestion.sources import book_metadata
from ingestion.sources.page_scanner import store
from ingestion.text_cleanup import abbreviations, spelling
from ingestion.text_cleanup.models import Passage, SourceKind
from ingestion.text_cleanup.store import AuditEntry, MappingRepository
from ingestion.text_cleanup.working import IllegalCleanupAction, WorkingState


class ReviewGate(Protocol):
    name: str

    def pending(self, prepared: PreparedFile) -> PendingDecision | None: ...

    def apply(self, prepared: PreparedFile, decision: DecisionRequest) -> None: ...


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


class BookMetadataGate:
    """Settle one book folder's identity before any of its photos publish."""

    name = "book_metadata"

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        # `record_confirmation()` returns the folder it renamed to. Keeping it
        # here means the coordinator remaps stored photo paths against the path
        # that was actually used, rather than re-deriving the slug itself.
        self.finalized_folder: Path | None = None

    def pending(self, prepared: PreparedFile) -> PendingDecision | None:
        if not isinstance(prepared.extractor, ImageExtractor):
            return None
        folder = prepared.source_path.parent
        status = book_metadata.gate_status(folder)
        if status == "clear":
            return None
        metadata = book_metadata.load_or_resolve(folder)
        title = str(metadata.get("title") or "").strip()
        return PendingDecision(
            item_id=str(folder),
            item_type="book",
            gate=self.name,
            adapter="book_identity",
            payload={
                "folder_path": str(folder),
                "folder_name": folder.name,
                "photo_count": sum(
                    1
                    for path in folder.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
                ),
                "proposed_title": title or None,
                "proposed_author": metadata.get("author"),
                "proposed_year": metadata.get("year"),
                "cover_url": metadata.get("cover_url"),
                "confidence": metadata.get("confidence"),
                "meta_source": metadata.get("meta_source"),
                "resolved_slug": (
                    book_metadata.slugify_title(title) if title else None
                ),
            },
            allowed_actions=("confirm", "correct"),
            blocking_reason=(
                "book identity must be confirmed"
                if status == "needs_confirm"
                else "book identity needs a cover"
            ),
        )

    def apply(self, prepared: PreparedFile, decision: DecisionRequest) -> None:
        folder = prepared.source_path.parent
        if decision.action == "confirm":
            self.finalized_folder = book_metadata.record_confirmation(
                folder, db_path=self.db_path
            )
            return
        if decision.action == "correct":
            title = str(decision.payload.get("title") or "").strip()
            if not title:
                raise IllegalDecisionError(
                    "a corrected book identity requires a title"
                )
            author = decision.payload.get("author")
            # Correction stores a newly resolved candidate but intentionally
            # leaves this folder in place. The coordinator immediately
            # re-evaluates the same item and blocks for a separate confirm.
            self.finalized_folder = None
            book_metadata.record_correction(
                folder,
                title=title,
                author=str(author) if author else None,
                db_path=self.db_path,
            )
            return
        raise IllegalDecisionError(
            f"book metadata accepts confirm or correct, not {decision.action!r}"
        )


class CleanupGate:
    """Component 8: human-controlled abbreviation and spelling review.

    Owns at most this run's ephemeral working states, keyed by content hash
    (component_8.md section 7.2). A fresh ``RunCoordinator`` gets a fresh
    ``CleanupGate``, so this in-memory dict is naturally scoped to one run --
    see ``coordinator/__init__.py``'s ``start_run`` replacing the whole
    coordinator (and therefore this gate) on every new run.
    """

    name = "cleanup"

    def __init__(
        self,
        *,
        mapping_repository: MappingRepository,
        chat_client: spelling.ChatClient | None,
        spelling_provider: str,
    ) -> None:
        self._mappings = mapping_repository
        self._chat_client = chat_client
        self._provider = spelling_provider
        self._states: dict[str, WorkingState] = {}

    @staticmethod
    def _source_kind(prepared: PreparedFile) -> SourceKind:
        return "image" if isinstance(prepared.extractor, ImageExtractor) else "text_file"

    @staticmethod
    def _passages_from_result(prepared: PreparedFile, source_kind: SourceKind) -> list[Passage]:
        if source_kind == "image":
            scanner = _mapping(prepared.result.frontmatter.get("page_scanner"))
            raw = scanner.get("passages")
            items = raw if isinstance(raw, list) else []
            passages: list[Passage] = []
            for index, item in enumerate(items):
                item_map = _mapping(item)
                text = str(item_map.get("edited_text") or item_map.get("text") or "")
                passages.append(Passage(index=index, text=text))
            return passages
        return [Passage(index=None, text=prepared.result.markdown_text)]

    def _ensure_state(self, prepared: PreparedFile) -> WorkingState:
        state = self._states.get(prepared.content_hash)
        if state is not None:
            return state
        source_kind = self._source_kind(prepared)
        passages = self._passages_from_result(prepared, source_kind)
        candidates = abbreviations.find_candidates(passages, self._mappings.active_mappings())
        state = WorkingState(
            content_hash=prepared.content_hash,
            source_kind=source_kind,
            abbreviation_base_passages=tuple(passages),
            abbreviation_candidates=tuple(candidates),
        )
        self._states[prepared.content_hash] = state
        return state

    def _install_spelling(self, state: WorkingState) -> None:
        settled_passages = state.working_passages("abbreviation")
        if self._chat_client is None:
            state.mark_unavailable("no shared LLM gateway client is configured")
            return
        try:
            candidates = spelling.request_spelling_proposals(
                settled_passages, chat_client=self._chat_client, provider=self._provider
            )
        except spelling.SpellingUnavailable as error:
            state.mark_unavailable(str(error))
            return
        state.install_spelling(settled_passages, candidates)

    def overlay(self, prepared: PreparedFile) -> PreparedFile:
        """Force approval and splice in-memory revised text (section 7.3).

        Every item reaching this gate always requires the existing final
        approval button press, even with zero cleanup suggestions (C8-C3) --
        that is set here, unconditionally, before this gate's own pending()
        even runs, so a later ContentApprovalGate.pending() always blocks.
        """

        result = prepared.result
        if not result.needs_approval:
            result = result.model_copy(
                update={
                    "needs_approval": True,
                    "approval_reason": result.approval_reason or "cleanup review required",
                }
            )
        state = self._states.get(prepared.content_hash)
        if state is None:
            return prepared if result is prepared.result else replace(prepared, result=result)

        working_passages = state.current_working_passages()
        if state.source_kind == "image":
            scanner = dict(_mapping(result.frontmatter.get("page_scanner")))
            passages_meta = scanner.get("passages")
            if isinstance(passages_meta, list):
                by_index = {passage.index: passage.text for passage in working_passages}
                updated_passages = []
                for index, meta in enumerate(passages_meta):
                    meta_map = dict(_mapping(meta))
                    if index in by_index:
                        meta_map["edited_text"] = by_index[index]
                    updated_passages.append(meta_map)
                scanner["passages"] = updated_passages
                frontmatter = dict(result.frontmatter)
                frontmatter["page_scanner"] = scanner
                result = result.model_copy(
                    update={
                        "frontmatter": frontmatter,
                        "markdown_text": "\n\n".join(
                            passage.text for passage in working_passages
                        ),
                    }
                )
        elif working_passages:
            result = result.model_copy(update={"markdown_text": working_passages[0].text})
        return replace(prepared, result=result)

    @staticmethod
    def _allowed_actions(
        state: WorkingState, *, can_continue: bool, is_fallback_display: bool
    ) -> tuple[str, ...]:
        if is_fallback_display:
            # Nothing left to act on in this (empty) phase; this occurrence
            # is shown for context only. can_continue is always true here --
            # a fallback display only happens once every real phase is
            # settled (see WorkingState.current_view()).
            return ("continue",) if can_continue else ()
        base = (
            ("apply_once", "apply_remember", "skip")
            if state.phase == "abbreviation"
            else ("accept", "reject")
        )
        actions = (*base, "previous", "next")
        return (*actions, "continue") if can_continue else actions

    def _review_pending(
        self, prepared: PreparedFile, state: WorkingState, *, can_continue: bool
    ) -> PendingDecision:
        view = state.current_view()
        if view is None:
            raise RuntimeError(
                f"cleanup expected a current {state.phase} occurrence but found none"
            )
        candidate = view.candidate
        working_text = "\n\n".join(
            passage.text for passage in state.current_working_passages()
        )
        payload = {
            "state": "review",
            "source_kind": state.source_kind,
            "phase": state.phase,
            "interaction_revision": state.interaction_revision,
            "working_draft_revision": state.working_draft_revision,
            "occurrence": {
                "occurrence_id": candidate.occurrence_id,
                "ordinal": candidate.ordinal,
                "total": view.total,
                "passage_index": candidate.passage_index,
                "base_start": candidate.base_start,
                "base_end": candidate.base_end,
                "current_start": view.current_start,
                "current_end": view.current_end,
                "original_text": candidate.original_text,
                "proposed_text": candidate.proposed_text,
                "context_before": view.context_before,
                "context_after": view.context_after,
                "before_sentence": view.before_sentence,
                "after_sentence": view.after_sentence,
                "current_decision": view.current_decision,
                "mapping_id": candidate.mapping_id,
                "proposal_source": candidate.proposal_source,
            },
            "authoritative_sentence": view.sentence,
            "authoritative_working_text": working_text,
            "can_continue": can_continue,
        }
        return PendingDecision(
            item_id=prepared.content_hash,
            item_type="image" if state.source_kind == "image" else "file",
            gate=self.name,
            adapter="cleanup",
            payload=payload,
            allowed_actions=self._allowed_actions(
                state, can_continue=can_continue, is_fallback_display=view.is_fallback_display
            ),
            blocking_reason=f"{state.phase} review required",
        )

    def _unavailable_pending(
        self, prepared: PreparedFile, state: WorkingState
    ) -> PendingDecision:
        payload = {
            "state": "unavailable",
            "source_kind": state.source_kind,
            "phase": "spelling",
            "interaction_revision": state.interaction_revision,
            "working_draft_revision": state.working_draft_revision,
            "error": state.spelling_unavailable_error,
        }
        return PendingDecision(
            item_id=prepared.content_hash,
            item_type="image" if state.source_kind == "image" else "file",
            gate=self.name,
            adapter="cleanup",
            payload=payload,
            allowed_actions=("retry",),
            blocking_reason="the spelling checker is unavailable",
        )

    def pending(self, prepared: PreparedFile) -> PendingDecision | None:
        state = self._ensure_state(prepared)
        if state.handed_to_final_approval:
            return None

        if not state.is_phase_settled("abbreviation"):
            return self._review_pending(prepared, state, can_continue=False)

        if not state.spelling_installed():
            self._install_spelling(state)

        if state.spelling_unavailable_error is not None:
            return self._unavailable_pending(prepared, state)

        if state.spelling_installed() and not state.is_phase_settled("spelling"):
            return self._review_pending(prepared, state, can_continue=False)

        if not state.has_any_cleanup_work():
            state.mark_handed_off()
            return None

        return self._review_pending(prepared, state, can_continue=True)

    def apply(self, prepared: PreparedFile, decision: DecisionRequest) -> None:
        state = self._states.get(prepared.content_hash)
        if state is None:
            raise IllegalDecisionError("cleanup has no pending decision for this item")
        action = decision.action

        expected_interaction = decision.payload.get("expected_interaction_revision")
        if expected_interaction is None or int(cast(Any, expected_interaction)) != state.interaction_revision:
            raise IllegalDecisionError(
                "cleanup decision has a stale or missing interaction revision"
            )

        if action in ("previous", "next"):
            occurrence_id = str(decision.payload.get("occurrence_id") or "")
            if not occurrence_id or occurrence_id != state.current_occurrence_id:
                raise IllegalDecisionError(
                    "cleanup navigation targets the wrong or missing occurrence"
                )
            state.navigate(action)
            return

        if action == "continue":
            expected_working = decision.payload.get("expected_working_draft_revision")
            if (
                expected_working is None
                or int(cast(Any, expected_working)) != state.working_draft_revision
            ):
                raise IllegalDecisionError(
                    "cleanup continue has a stale or missing working-draft revision"
                )
            if not state.is_fully_resolved():
                raise IllegalDecisionError(
                    "cleanup cannot continue with unresolved occurrences"
                )
            state.mark_handed_off()
            return

        occurrence_id = str(decision.payload.get("occurrence_id") or "")
        if not occurrence_id:
            raise IllegalDecisionError("a cleanup decision requires an occurrence_id")
        if occurrence_id != state.current_occurrence_id:
            raise IllegalDecisionError(
                "cleanup decision targets an occurrence that is not currently visible"
            )
        expected_working = decision.payload.get("expected_working_draft_revision")
        if (
            expected_working is None
            or int(cast(Any, expected_working)) != state.working_draft_revision
        ):
            raise IllegalDecisionError(
                "cleanup decision has a stale or missing working-draft revision"
            )

        try:
            if action == "apply_remember":
                candidate = next(
                    (c for c in state.phase_candidates() if c.occurrence_id == occurrence_id),
                    None,
                )
                if candidate is None:
                    raise IllegalCleanupAction(
                        f"occurrence {occurrence_id!r} is not in the current phase"
                    )
                shorthand = str(decision.payload.get("shorthand") or "") or candidate.original_text
                expansion = str(decision.payload.get("expansion") or "") or candidate.proposed_text
                case_sensitive = bool(decision.payload.get("case_sensitive", True))
                if shorthand != candidate.original_text:
                    raise IllegalCleanupAction(
                        "Apply + remember shorthand must match the visible occurrence exactly"
                    )
                _, before_text, after_text, text_changed = state.decision_effect(
                    occurrence_id, action, proposed_text=expansion
                )
                self._mappings.record_apply_remember(
                    shorthand=shorthand,
                    expansion=expansion,
                    case_sensitive=case_sensitive,
                    audit=AuditEntry(
                        source_kind=state.source_kind,
                        run_id=decision.run_id,
                        item_id=prepared.content_hash,
                        occurrence_id=occurrence_id,
                        phase=state.phase,
                        action=action,
                        before=before_text,
                        after=after_text,
                        interaction_revision=state.interaction_revision + 1,
                        working_draft_revision=(
                            state.working_draft_revision + int(text_changed)
                        ),
                    ),
                )
                # Only publish the new authoritative in-memory decision after
                # the mapping and audit transaction above committed.
                state.decide(occurrence_id, action, proposed_text=expansion)
            else:
                proposed_text: str | None = None
                if action == "apply_once" and (
                    "shorthand" in decision.payload or "expansion" in decision.payload
                ):
                    candidate = next(
                        (
                            item
                            for item in state.phase_candidates()
                            if item.occurrence_id == occurrence_id
                        ),
                        None,
                    )
                    if candidate is None:
                        raise IllegalCleanupAction(
                            f"occurrence {occurrence_id!r} is not in the current phase"
                        )
                    shorthand = str(decision.payload.get("shorthand") or "")
                    proposed_text = str(decision.payload.get("expansion") or "")
                    if shorthand != candidate.original_text:
                        raise IllegalCleanupAction(
                            "Apply once shorthand must match the visible occurrence exactly"
                        )
                    if not proposed_text.strip():
                        raise IllegalCleanupAction(
                            "Apply once expansion cannot be blank"
                        )
                _, before_text, after_text, text_changed = state.decision_effect(
                    occurrence_id, action, proposed_text=proposed_text
                )
                self._mappings.append_audit(
                    AuditEntry(
                        source_kind=state.source_kind,
                        run_id=decision.run_id,
                        item_id=prepared.content_hash,
                        occurrence_id=occurrence_id,
                        phase=state.phase,
                        action=action,
                        before=before_text,
                        after=after_text,
                        interaction_revision=state.interaction_revision + 1,
                        working_draft_revision=(
                            state.working_draft_revision + int(text_changed)
                        ),
                    )
                )
                # Audit durability is part of the successful cleanup action;
                # a failed write leaves the working state untouched.
                state.decide(
                    occurrence_id, action, proposed_text=proposed_text
                )
        except IllegalCleanupAction as error:
            raise IllegalDecisionError(str(error)) from error

    def clear(self, content_hash: str) -> None:
        self._states.pop(content_hash, None)


class ContentApprovalGate:
    """Show an approval-bound item's own text, and save what comes back."""

    name = "content_approval"

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def _page(self, prepared: PreparedFile) -> dict[str, object] | None:
        return cast(
            dict[str, object] | None,
            store.get_page_by_file_hash(self.db_path, prepared.content_hash),
        )

    def _image_payload(
        self, prepared: PreparedFile, page: dict[str, object], page_id: int
    ) -> dict[str, Any]:
        scanner = _mapping(prepared.result.frontmatter.get("page_scanner"))
        book = _mapping(prepared.result.frontmatter.get("book_meta"))
        # Stored passage rows own stable id/bbox/min_conf; cleanup's overlay
        # (in prepared.result.frontmatter, never persisted before Approve --
        # see pending() below) owns display text once it has run. Preferring
        # the overlay's edited_text here is what makes an accepted cleanup
        # change visible in final approval without writing it to the DB early
        # (component_8.md section 7.3).
        overlay_passages = scanner.get("passages")
        overlay_texts: list[str | None] = (
            [
                str(_mapping(item).get("edited_text"))
                if _mapping(item).get("edited_text") is not None
                else None
                for item in overlay_passages
            ]
            if isinstance(overlay_passages, list)
            else []
        )
        return {
            "page_id": page_id,
            "photo_path": str(page.get("image_path") or prepared.source_path),
            "book_title": book.get("title"),
            "book_author": book.get("author") or page.get("author"),
            "page_number": page.get("page_number"),
            "approval_reason": prepared.result.approval_reason,
            "flagged_retake": bool(scanner.get("flagged_retake", False)),
            "blur_score": page.get("blur_score"),
            "glare_score": page.get("glare_score"),
            "conf_ratio": page.get("conf_ratio"),
            "passages": [
                {
                    "index": index,
                    "ocr_text": passage.get("ocr_text") or "",
                    "edited_text": (
                        overlay_texts[index]
                        if index < len(overlay_texts) and overlay_texts[index] is not None
                        else (passage.get("edited_text") or passage.get("ocr_text") or "")
                    ),
                    "min_conf": passage.get("min_conf"),
                    "bbox": passage.get("bbox"),
                }
                for index, passage in enumerate(
                    store.get_passages(self.db_path, page_id)
                )
            ],
        }

    def _text_payload(self, prepared: PreparedFile) -> dict[str, Any]:
        return {
            "source_path": str(prepared.source_path),
            "title": prepared.result.title,
            "approval_reason": prepared.result.approval_reason,
            "extraction_method": prepared.result.frontmatter.get(
                "extraction_method"
            ),
            "markdown_text": prepared.result.markdown_text,
        }

    def pending(
        self, prepared: PreparedFile, *, park_result: IntakeResult | None = None
    ) -> PendingDecision | None:
        """``park_result`` -- when given -- is written to the store instead
        of ``prepared.result`` the first time this item is parked.

        The coordinator passes the pre-cleanup-overlay extraction here so a
        restart between Continue and Approve rebuilds cleanup from the raw
        extracted text, never from an already-applied cleanup edit (section
        7.3: "Do not persist either overlay before final Approve"; DoD:
        "restart rebuilds cleanup"). ``prepared.result`` itself may carry the
        overlay for *display* -- see ``_image_payload``/``_text_payload``.
        """

        if not prepared.result.needs_approval:
            return None
        page = self._page(prepared)
        if page is None:
            store.park_intake_result(
                self.db_path, prepared.source_path, park_result or prepared.result
            )
            page = self._page(prepared)
        if page is None:
            raise RuntimeError("approval-bound intake item could not be parked")
        status = str(page.get("status") or "")
        scanner = _mapping(prepared.result.frontmatter.get("page_scanner"))
        flagged_retake = bool(scanner.get("flagged_retake", False))
        if status in {"reviewed", "published", "discarded"}:
            return None
        if status == "retake" and not flagged_retake:
            return None
        page_id = int(cast(Any, page["id"]))
        is_image = isinstance(prepared.extractor, ImageExtractor)
        return PendingDecision(
            item_id=prepared.content_hash,
            item_type="image" if is_image else "file",
            gate=self.name,
            adapter="image_ocr" if is_image else "text_file",
            payload=(
                self._image_payload(prepared, page, page_id)
                if is_image
                # An auto-flagged photo is still shown to you, and a text file
                # has no photo to take again — so its payload carries the text
                # itself rather than a passage list.
                else {"page_id": page_id, **self._text_payload(prepared)}
            ),
            allowed_actions=(
                ("approve", "discard", "retake")
                if is_image
                else ("approve", "discard")
            ),
            blocking_reason=prepared.result.approval_reason or "approval required",
        )

    def _save_edits(
        self, page_id: int, decision: DecisionRequest, *, is_image: bool
    ) -> None:
        """Persist the human's corrections before the status says 'reviewed'.

        `approved_intake_result()` rebuilds the published note out of the stored
        passages, so an edit that is not written here is an edit the published
        note silently loses.
        """

        passages = store.get_passages(self.db_path, page_id)
        if is_image:
            edits = decision.payload.get("passages")
            for edit in edits if isinstance(edits, Sequence) else ():
                if not isinstance(edit, Mapping):
                    raise IllegalDecisionError("each passage edit must be an object")
                index = int(cast(Any, edit["index"]))
                if not 0 <= index < len(passages):
                    raise IllegalDecisionError(
                        f"passage index {index} is not on page {page_id}"
                    )
                store.update_passage(
                    self.db_path,
                    int(passages[index]["id"]),
                    str(edit.get("edited_text") or ""),
                )
            if "page_number" in decision.payload:
                number = decision.payload["page_number"]
                store.update_page_number(
                    self.db_path, page_id, int(number) if number is not None else None
                )
            return
        text = decision.payload.get("markdown_text")
        if text is None:
            return
        if not passages:
            raise IllegalDecisionError(
                f"page {page_id} has no passage to hold edited text"
            )
        store.update_passage(self.db_path, int(passages[0]["id"]), str(text))

    def apply(self, prepared: PreparedFile, decision: DecisionRequest) -> None:
        page = self._page(prepared)
        if page is None:
            raise IllegalDecisionError("approval item is not parked")
        page_id = int(cast(Any, page["id"]))
        is_image = isinstance(prepared.extractor, ImageExtractor)
        if decision.action == "approve":
            self._save_edits(page_id, decision, is_image=is_image)
            if is_image:
                saved_passages = store.get_passages(self.db_path, page_id)
                if not any(
                    str(
                        passage.get("edited_text")
                        or passage.get("ocr_text")
                        or ""
                    ).strip()
                    for passage in saved_passages
                ):
                    raise IllegalDecisionError(
                        "a photo cannot be approved with no highlighted passages; "
                        "retake or discard it"
                    )
            parked_source = Path(str(page.get("image_path") or ""))
            if parked_source.is_file():
                store.restore_from_retake(self.db_path, page_id, parked_source)
            store.update_page_status(self.db_path, page_id, "reviewed")
        elif decision.action == "discard":
            store.update_page_status(self.db_path, page_id, "discarded")
        elif decision.action == "retake":
            if not is_image:
                raise IllegalDecisionError("only a photo can be retaken")
            source = Path(str(page.get("image_path") or prepared.source_path))
            if source.is_file():
                store.mark_retake(self.db_path, page_id, source)
            store.update_page_status(self.db_path, page_id, "retake")
        else:
            raise IllegalDecisionError(f"unsupported content action: {decision.action}")


class PhaseHandoffGate:
    name = "phase_handoff"

    @staticmethod
    def pending(
        *,
        intake_worked: bool,
        counts: dict[str, int],
        note_paths: Sequence[str] = (),
    ) -> PendingDecision | None:
        if not intake_worked:
            return None
        return PendingDecision(
            item_id="",
            item_type="phase_handoff",
            gate="phase_handoff",
            adapter="phase_handoff",
            payload={**counts, "note_paths": list(note_paths)},
            allowed_actions=("continue", "stop"),
            blocking_reason="intake is complete; choose whether to continue",
        )
