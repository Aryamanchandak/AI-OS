(() => {
  "use strict";

  const app = document.querySelector("#app");
  const runStatus = document.querySelector("#run-status");
  const statusCopy = document.querySelector("#status-copy");
  const toast = document.querySelector("#toast");
  const announcer = document.querySelector("#sr-announcer");
  let snapshot = null;
  let renderKey = "";
  let startRequested = false;
  let submittedDraftKey = null;
  let submittedRevision = null;
  let pollTimer = null;
  let zoomState = { scale: 1, x: 0, y: 0 };
  const STAGES = [
    "preflight", "discover_intake", "intake_item", "intake_barrier",
    "capture_obsidian", "process_pending", "proposal_review",
    "dispatch_retry", "complete",
  ];
  const STAGE_LABELS = {
    preflight: "Preflight", discover_intake: "Discover", intake_item: "Intake",
    intake_barrier: "Handoff", capture_obsidian: "Capture", process_pending: "Extract",
    proposal_review: "Review", dispatch_retry: "Dispatch", complete: "Complete",
  };

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const unknown = (value) => value === null || value === undefined || value === "";
  const display = (value) => unknown(value) ? '<span class="unknown">Unknown</span>' : escapeHtml(value);
  const pendingKey = (view) => view?.pending ? `${view.run_id}:${view.pending.item_id}` : null;
  const draftStorageKey = (view) => `ingestion-review:${pendingKey(view)}`;

  function readDraft(view) {
    try { return JSON.parse(sessionStorage.getItem(draftStorageKey(view)) || "{}") || {}; }
    catch { return {}; }
  }

  function writeDraft(view, value) {
    sessionStorage.setItem(draftStorageKey(view), JSON.stringify(value));
    setSaveState("Unsaved locally");
  }

  function clearDraft(key) {
    if (key) sessionStorage.removeItem(`ingestion-review:${key}`);
  }

  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    window.setTimeout(() => { toast.hidden = true; }, 5000);
  }

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    let body = {};
    try { body = await response.json(); } catch { /* response detail is optional */ }
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }

  function schedulePoll(delay) {
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(refresh, delay);
  }

  async function refresh() {
    try {
      const next = await request("/api/run");
      acceptSnapshot(next);
      if (!next.view && next.operation.state === "idle" && !startRequested) {
        startRequested = true;
        acceptSnapshot(await request("/api/run/start", { method: "POST" }));
      }
    } catch (error) {
      setConnection("failed", "Connection lost");
      showToast(error.message);
    } finally {
      schedulePoll(snapshot?.operation?.state === "submitting" ? 650 : 2200);
    }
  }

  function acceptSnapshot(next) {
    const oldPending = pendingKey(snapshot?.view);
    const newPending = pendingKey(next.view);
    snapshot = next;
    if (
      submittedDraftKey && next.operation.state === "idle"
      && Number(next.operation.revision) > Number(submittedRevision)
    ) {
      clearDraft(submittedDraftKey);
      submittedDraftKey = null;
      submittedRevision = null;
      announcer.textContent = "Decision accepted. The pipeline advanced.";
    }
    const key = JSON.stringify([
      next.view?.run_id, next.view?.stage, newPending, next.view?.terminal_result,
      next.operation.state, next.operation.error, next.operation.revision,
    ]);
    if (key !== renderKey || oldPending !== newPending) {
      renderKey = key;
      render();
    } else {
      setConnection(next.operation.state, statusLabel(next));
      setActionsDisabled(next.operation.state === "submitting");
    }
  }

  function statusLabel(value) {
    if (value.operation.state === "submitting") return value.operation.name === "decision" ? "Saving decision" : "Pipeline working";
    if (value.operation.state === "failed") return "Action failed";
    if (value.view?.terminal_result === "complete") return "Run complete";
    if (value.view?.stage_status === "blocked") return "Waiting for review";
    return value.view ? "Connected" : "Ready to start";
  }

  function setConnection(state, copy) {
    runStatus.dataset.state = state;
    statusCopy.textContent = copy;
  }

  function setSaveState(copy, error = false) {
    const element = document.querySelector("#save-state");
    if (!element) return;
    element.textContent = copy;
    element.classList.toggle("error", error);
  }

  function setActionsDisabled(disabled) {
    document.querySelectorAll("[data-action]").forEach((button) => { button.disabled = disabled; });
    if (disabled) setSaveState("Submitting…");
  }

  function progress(view) {
    const done = view.progress?.intake_resolved ?? 0;
    const total = view.progress?.intake_total ?? 0;
    const semanticDone = view.progress?.envelopes_resolved ?? 0;
    const semanticTotal = view.progress?.envelopes_flagged ?? 0;
    const semantic = semanticTotal ? `<span>${semanticDone} / ${semanticTotal} semantic</span>` : "";
    return `<div class="progress-chip"><strong>${done} / ${total}</strong><span>intake resolved</span>${semantic}</div>`;
  }

  function stageRail(view) {
    const recorded = new Map((view.stages || []).map((stage) => [stage.stage, stage.status]));
    return `<ol class="stage-rail" aria-label="Pipeline stages">${STAGES.map((stage) => {
      const status = stage === view.stage ? view.stage_status : (recorded.get(stage) || "upcoming");
      return `<li class="stage-step" data-status="${escapeHtml(status)}"${stage === view.stage ? ' aria-current="step"' : ""}><span class="stage-dot"></span><span>${STAGE_LABELS[stage]}</span></li>`;
    }).join("")}</ol>`;
  }

  function heading(view, eyebrow, title, copy) {
    return `<header class="review-heading">
      <div><span class="eyebrow">${escapeHtml(eyebrow)}</span><h1>${escapeHtml(title)}</h1><p>${escapeHtml(copy)}</p></div>
      ${progress(view)}
    </header>${stageRail(view)}`;
  }

  function operationError() {
    const message = snapshot?.operation?.error;
    return message ? `<div class="error-banner" role="alert">${escapeHtml(message)} Your draft is still here.</div>` : "";
  }

  function render() {
    const state = snapshot?.operation?.state || "idle";
    setConnection(state, statusLabel(snapshot || { operation: { state } }));
    const view = snapshot?.view;
    if (!view) {
      app.innerHTML = `<section class="empty-state panel"><span class="eyebrow">Repository run</span><h1>${state === "failed" ? "The run could not start." : "Preparing the next decision."}</h1><p>${escapeHtml(snapshot?.operation?.error || "The coordinator is reconnecting to durable pipeline state.")}</p>${state === "submitting" ? '<div class="loader"><span></span><span></span><span></span></div>' : '<button class="button primary" data-start>Start run</button>'}</section>`;
      document.querySelector("[data-start]")?.addEventListener("click", startRun);
      return;
    }
    if (view.last_error || view.stage === "failed") return renderFailure(view);
    if (view.terminal_result) return renderTerminal(view);
    if (!view.pending) return renderWorking(view);
    if (view.pending.adapter === "book_identity") return renderBook(view);
    if (view.pending.adapter === "image_ocr") return renderImage(view);
    if (view.pending.adapter === "text_file") return renderTextFile(view);
    if (view.pending.adapter === "phase_handoff") return renderHandoff(view);
    if (view.pending.adapter === "knowledge_proposal") return renderProposal(view);
    renderUnsupported(view);
  }

  function renderWorking(view) {
    const current = STAGE_LABELS[view.stage] || view.stage.replaceAll("_", " ");
    app.innerHTML = `${heading(view, current, "The pipeline is moving.", "Long-running work stays serialized while this screen remains responsive.")}<section class="working-panel panel"><div class="working-orbit" aria-hidden="true"><span></span></div><div><span class="eyebrow">Automatic work</span><h2>${escapeHtml(current)} is running</h2><p>The coordinator owns this transition. This screen will update when work completes or a decision is required.</p></div><div class="loader" aria-label="Pipeline working"><span></span><span></span><span></span></div></section>`;
  }

  function renderTerminal(view) {
    app.innerHTML = `${heading(view, `Run ${view.terminal_result}`, view.terminal_result === "complete" ? "Everything in this run is settled." : "The run ended safely.", `Run ${view.run_id} has a durable report.`)}<section class="report-panel panel" id="report-panel"><div class="report-loading"><div class="loader"><span></span><span></span><span></span></div><p>Reading the durable run report…</p></div></section>`;
    loadReport(view);
  }

  function renderFailure(view) {
    const message = view.last_error?.message || snapshot.operation.error || "The current stage failed.";
    const retry = view.last_error?.retryable ? '<button class="button primary" data-retry>Retry this stage</button>' : "";
    app.innerHTML = `${heading(view, view.last_error?.retryable ? "Retryable failure" : "Mandatory failure", "The pipeline stopped safely.", message)}<section class="failure-panel panel"><div class="failure-mark" aria-hidden="true">!</div><div><h2>${escapeHtml(STAGE_LABELS[view.last_error?.stage] || "Current stage")} did not complete</h2><p>${escapeHtml(message)}</p></div>${retry}</section>`;
    document.querySelector("[data-retry]")?.addEventListener("click", retryRun);
  }

  function renderUnsupported(view) {
    const pending = view.pending;
    app.innerHTML = `${heading(view, "Current decision", pending.adapter.replaceAll("_", " "), pending.blocking_reason)}<section class="empty-state panel"><h1>This adapter belongs to another component.</h1><p>The coordinator is still blocked safely. No alternate transition is available here.</p></section>`;
  }

  function actionButtons(pending, primaryAction) {
    return pending.allowed_actions.map((action) => {
      const primary = action === primaryAction ? " primary" : "";
      const danger = ["discard", "retake"].includes(action) ? " danger" : "";
      const label = { confirm: "Confirm identity", correct: "Re-run lookup", approve: "Approve", edit: "Save edited proposal", reject: "Reject", discard: "Discard", retake: "Request retake", continue: "Continue to knowledge", stop: "Finish after intake" }[action] || action;
      return `<button class="button${primary}${danger}" data-action="${escapeHtml(action)}">${escapeHtml(label)}</button>`;
    }).join("");
  }

  function renderBook(view) {
    const pending = view.pending;
    const p = pending.payload;
    const draft = readDraft(view);
    const title = draft.title ?? p.proposed_title ?? "";
    const author = draft.author ?? p.proposed_author ?? "";
    const editing = Boolean(draft.editing);
    const cover = unknown(p.cover_url)
      ? '<div class="cover-placeholder"><span></span><p>Cover unavailable</p></div>'
      : `<img src="${escapeHtml(p.cover_url)}" alt="Proposed book cover" referrerpolicy="no-referrer">`;
    app.innerHTML = `${heading(view, "Book identity", "Confirm the book before its first page.", "Lookup evidence is a candidate, not an acceptance. Inspect it here, edit if needed, then confirm.")}
      <div class="review-grid">
        <section class="panel evidence-pane book-evidence" aria-label="Book evidence">
          <div class="cover-well">${cover}</div>
          <div class="evidence-list">
            <span class="eyebrow">Source evidence</span>
            <dl>
              <dt>Folder</dt><dd>${display(p.folder_name)}</dd>
              <dt>Photos</dt><dd>${display(p.photo_count)}</dd>
              <dt>Lookup source</dt><dd>${display(p.meta_source)}</dd>
              <dt>Confidence</dt><dd><span class="confidence">${escapeHtml(p.confidence || "unknown")}</span></dd>
              <dt>Resolved folder</dt><dd class="slug">${display(p.resolved_slug)}</dd>
            </dl>
          </div>
        </section>
        <section class="panel decision-pane"><div class="pane-inner">
          <div class="pane-label"><h2>Proposed identity</h2><span class="muted">Human confirmation required</span></div>
          ${operationError()}
          <div class="identity-form">
            ${editing ? `<div class="field"><label for="book-title">Corrected title</label><input id="book-title" value="${escapeHtml(title)}" autocomplete="off"></div><div class="field"><label for="book-author">Corrected author</label><input id="book-author" value="${escapeHtml(author)}" autocomplete="off"></div>` : `<div class="identity-summary"><h3>${display(p.proposed_title)}</h3><p>${display(p.proposed_author)}</p><p>${unknown(p.proposed_year) ? '<span class="unknown">Publication year unknown</span>' : escapeHtml(p.proposed_year)}</p></div>`}
            <div class="mode-switch"><span class="muted">${editing ? "Lookup will return a new candidate for inspection." : "Does this match the source book?"}</span><button class="text-button" type="button" data-edit>${editing ? "Cancel edit" : "Edit title or author"}</button></div>
          </div>
          <div class="action-area"><div class="actions">${editing ? actionButtons({ allowed_actions: pending.allowed_actions.filter((a) => a === "correct") }, "correct") : actionButtons({ allowed_actions: pending.allowed_actions.filter((a) => a === "confirm") }, "confirm")}</div><p class="save-state" id="save-state">${draft.title || draft.author ? "Unsaved locally" : "No decision submitted"}</p></div>
        </div></section>
      </div>`;
    bindBook(view, editing);
    setActionsDisabled(snapshot.operation.state === "submitting");
  }

  function bindBook(view, editing) {
    document.querySelector("[data-edit]")?.addEventListener("click", () => {
      const current = readDraft(view);
      if (editing) sessionStorage.removeItem(draftStorageKey(view));
      else writeDraft(view, { title: view.pending.payload.proposed_title || "", author: view.pending.payload.proposed_author || "", editing: true });
      renderKey = "";
      render();
    });
    if (editing) {
      ["book-title", "book-author"].forEach((id) => document.querySelector(`#${id}`)?.addEventListener("input", () => {
        writeDraft(view, { title: document.querySelector("#book-title").value, author: document.querySelector("#book-author").value, editing: true });
      }));
    }
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.action;
      const draft = readDraft(view);
      if (action === "correct" && !(draft.title || "").trim()) return showToast("Enter a corrected title first.");
      submitDecision(view, action, action === "correct" ? { title: draft.title.trim(), author: (draft.author || "").trim() || null } : {});
    }));
  }

  function renderTextFile(view) {
    const pending = view.pending;
    const p = pending.payload;
    const draft = readDraft(view);
    const text = Object.hasOwn(draft, "markdown_text") ? draft.markdown_text : (p.markdown_text || "");
    const sourceName = String(p.source_path || "Source file").split(/[\\/]/).pop();
    app.innerHTML = `${heading(view, "Source review", p.title || sourceName, "Inspect the extracted source before it is published into the vault.")}
      <div class="review-grid text-review-grid">
        <section class="panel evidence-pane source-evidence"><div class="document-header"><span class="document-icon" aria-hidden="true">¶</span><div><span class="eyebrow">Extracted source</span><h2>${escapeHtml(sourceName)}</h2></div></div><dl class="source-facts"><dt>Source</dt><dd class="slug">${display(p.source_path)}</dd><dt>Method</dt><dd>${display(p.extraction_method)}</dd><dt>Review reason</dt><dd>${display(p.approval_reason || pending.blocking_reason)}</dd></dl><div class="source-preview"><span class="field-label">Original extraction</span><pre>${escapeHtml(p.markdown_text || "No extracted text")}</pre></div></section>
        <section class="panel decision-pane"><div class="pane-inner"><div class="pane-label"><h2>Final editable draft</h2><span class="muted">Markdown</span></div>${operationError()}<div class="field"><label for="markdown-text">Text to publish</label><textarea class="document-editor" id="markdown-text">${escapeHtml(text)}</textarea></div><div class="action-area"><div class="actions">${actionButtons(pending, "approve")}</div><p class="save-state" id="save-state">${Object.hasOwn(draft, "markdown_text") ? "Unsaved locally" : "No edits yet"}</p></div></div></section>
      </div>`;
    document.querySelector("#markdown-text")?.addEventListener("input", (event) => writeDraft(view, { markdown_text: event.target.value }));
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.action;
      const markdown = document.querySelector("#markdown-text")?.value || "";
      if (action === "approve" && !markdown.trim()) return showToast("The final draft cannot be empty.");
      submitDecision(view, action, action === "approve" ? { markdown_text: markdown } : {});
    }));
    setActionsDisabled(snapshot.operation.state === "submitting");
  }

  function renderHandoff(view) {
    const pending = view.pending;
    const p = pending.payload;
    const notes = Array.isArray(p.note_paths) ? p.note_paths : [];
    app.innerHTML = `${heading(view, "Intake settled", "Continue into knowledge processing?", "This is the deliberate handoff between source publication and Obsidian capture.")}
      <div class="handoff-grid"><section class="panel handoff-summary"><span class="eyebrow">Intake result</span><div class="summary-metrics">${["discovered", "published", "discarded", "retake", "failed"].map((key) => `<div><strong>${escapeHtml(p[key] ?? 0)}</strong><span>${escapeHtml(key)}</span></div>`).join("")}</div><div class="note-list"><h2>Vault notes written</h2>${notes.length ? `<ul>${notes.map((note) => `<li class="slug">${escapeHtml(note)}</li>`).join("")}</ul>` : '<p class="muted">No new note paths were reported.</p>'}</div></section><section class="panel handoff-decision"><span class="eyebrow">Phase handoff</span><h2>Source work is safely committed.</h2><p>Continue to capture the vault, extract semantic proposals, review flagged knowledge, and dispatch approved results. Or finish this run at the station boundary.</p><div class="action-area"><div class="actions">${actionButtons(pending, "continue")}</div><p class="save-state" id="save-state">Waiting for your choice</p></div></section></div>`;
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => submitDecision(view, button.dataset.action, {})));
    setActionsDisabled(snapshot.operation.state === "submitting");
  }

  const SIGNAL_EXPLANATIONS = {
    low_confidence: "The model reported confidence below the automatic-acceptance threshold.",
    missing_evidence: "The proposal does not have a complete evidence pointer.",
    hierarchy: "The proposal may affect a hierarchical relationship and needs deliberate review.",
    cycle_risk: "The relationship may introduce a cycle in the knowledge graph.",
  };

  function signalCards(payload) {
    const signals = payload.signals || payload.review_signals || [];
    if (!signals.length) return '<p class="muted">No structured review signals were supplied.</p>';
    return `<div class="signal-list">${signals.map((signal) => `<details class="signal-card"><summary><span>${escapeHtml(String(signal.code || "review").replaceAll("_", " "))}</span><small>${escapeHtml(signal.scope || "envelope")}</small></summary><p>${escapeHtml(signal.detail || SIGNAL_EXPLANATIONS[signal.code] || "The deterministic review policy requires a human decision.")}</p><code>${escapeHtml(signal.code || "unknown_signal")}</code></details>`).join("")}</div>`;
  }

  function highlightedEvidence(payload) {
    const text = String(payload.highlight_text || "");
    const quote = String(payload.evidence_quote || "");
    const start = Number(payload.evidence_start_char);
    const end = Number(payload.evidence_end_char);
    if (Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= text.length) {
      return `<blockquote class="evidence-quote">${escapeHtml(text.slice(0, start))}<mark>${escapeHtml(text.slice(start, end))}</mark>${escapeHtml(text.slice(end))}</blockquote><p class="offset-copy">Recorded offsets ${start}–${end}</p>`;
    }
    return `<blockquote class="evidence-quote">${escapeHtml(text || quote || "No evidence text supplied")}</blockquote>${quote ? `<div class="offset-warning">Evidence quote: “${escapeHtml(quote)}” · recorded offsets unavailable in this displayed highlight</div>` : ""}`;
  }

  function editableProposalFields(proposal) {
    const hidden = new Set(["proposal_id", "source_record_id", "evidence", "model_confidence", "confidence", "status"]);
    return Object.entries(proposal || {}).filter(([key, value]) => !hidden.has(key) && ["string", "number", "boolean", "object"].includes(typeof value) && (value === null || !Array.isArray(value) || value.every((item) => typeof item !== "object"))).map(([key, value]) => {
      const label = key.replaceAll("_", " ");
      if (typeof value === "boolean") return `<label class="check-field"><input type="checkbox" data-proposal-field="${escapeHtml(key)}" data-value-type="boolean"${value ? " checked" : ""}><span>${escapeHtml(label)}</span></label>`;
      if (Array.isArray(value)) return `<div class="field"><label for="proposal-${escapeHtml(key)}">${escapeHtml(label)}</label><input id="proposal-${escapeHtml(key)}" data-proposal-field="${escapeHtml(key)}" data-value-type="array" value="${escapeHtml(value.join(", "))}"></div>`;
      const multiline = key === "text" || key === "rationale";
      const valueType = value === null ? "nullable" : typeof value;
      return `<div class="field"><label for="proposal-${escapeHtml(key)}">${escapeHtml(label)}</label>${multiline ? `<textarea id="proposal-${escapeHtml(key)}" data-proposal-field="${escapeHtml(key)}" data-value-type="${valueType}">${escapeHtml(value ?? "")}</textarea>` : `<input id="proposal-${escapeHtml(key)}" data-proposal-field="${escapeHtml(key)}" data-value-type="${valueType}" value="${escapeHtml(value ?? "")}">`}</div>`;
    }).join("");
  }

  function proposalFromForm(original) {
    const edited = structuredClone(original || {});
    document.querySelectorAll("[data-proposal-field]").forEach((field) => {
      const type = field.dataset.valueType;
      if (type === "boolean") edited[field.dataset.proposalField] = field.checked;
      else if (type === "array") edited[field.dataset.proposalField] = field.value.split(",").map((value) => value.trim()).filter(Boolean);
      else if (type === "number") edited[field.dataset.proposalField] = Number(field.value);
      else if (type === "nullable") edited[field.dataset.proposalField] = field.value.trim() ? field.value : null;
      else edited[field.dataset.proposalField] = field.value;
    });
    return edited;
  }

  function renderProposal(view) {
    const pending = view.pending;
    const p = pending.payload;
    const envelopeLevel = Boolean(p.envelope_level);
    const proposal = p.proposal || {};
    const confidence = (value) => unknown(value) ? "Unknown" : `${Math.round(Number(value) * 100)}%`;
    const typeLabel = envelopeLevel ? "Envelope decision" : `${p.proposal_type || "Knowledge"} proposal`;
    app.innerHTML = `${heading(view, "Semantic review", typeLabel, "Review what the model inferred from a stored highlight before anything reaches downstream knowledge stores.")}
      <div class="review-grid proposal-grid"><section class="panel evidence-pane proposal-evidence"><div class="provenance-bar"><div><span class="eyebrow">Frozen evidence</span><h2>${display(p.source_note_path || p.source_record_id)}</h2></div><span class="origin-badge">${display(p.origin_kind || "unknown origin")}</span></div>${highlightedEvidence(p)}<dl class="source-facts"><dt>Highlight</dt><dd>${display(p.highlight_index)}</dd><dt>Proposal confidence</dt><dd>${confidence(p.proposal_confidence)}</dd><dt>Envelope confidence</dt><dd>${confidence(p.envelope_confidence ?? p.model_confidence)}</dd><dt>Proposal ID</dt><dd class="slug">${display(p.proposal_id || pending.item_id)}</dd></dl><div class="signals"><h3>Why review is required</h3>${signalCards(p)}</div></section>
      <section class="panel decision-pane"><div class="pane-inner"><div class="pane-label"><h2>${envelopeLevel ? "Envelope decision" : "Proposed fields"}</h2><span class="muted">One decision at a time</span></div>${operationError()}${envelopeLevel ? '<p class="reason">This decision applies to the flagged semantic envelope as a whole.</p>' : `<div class="proposal-form">${editableProposalFields(proposal)}</div>`}<div class="reviewer-fields"><div class="field"><label for="reviewer">Resolver identity</label><input id="reviewer" value="${escapeHtml(snapshot.reviewer || "local-reviewer")}" autocomplete="name"></div><div class="field"><label for="review-note">Optional review note</label><textarea id="review-note" placeholder="Why did you make this decision?"></textarea></div></div><div class="action-area"><div class="actions">${actionButtons(pending, envelopeLevel ? "approve" : "edit")}</div><p class="save-state" id="save-state">No decision submitted</p></div></div></section></div>`;
    document.querySelectorAll("[data-proposal-field], #review-note").forEach((field) => field.addEventListener("input", () => setSaveState("Unsaved locally")));
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.action;
      const payload = action === "edit" ? { edited_proposal: proposalFromForm(proposal) } : {};
      submitDecision(view, action, payload, { resolver: document.querySelector("#reviewer")?.value || "", note: document.querySelector("#review-note")?.value || "" });
    }));
    setActionsDisabled(snapshot.operation.state === "submitting");
  }

  function renderImage(view) {
    const pending = view.pending;
    const p = pending.payload;
    const draft = readDraft(view);
    const pageNumber = Object.hasOwn(draft, "page_number") ? draft.page_number : (p.page_number ?? "");
    const passages = p.passages || [];
    const cards = passages.map((passage, index) => {
      const edited = draft.passages?.[String(passage.index)] ?? passage.edited_text ?? "";
      const confidence = unknown(passage.min_conf) ? "Confidence unknown" : `${Math.round(Number(passage.min_conf) * 100)}% confidence`;
      return `<article class="passage-card" id="passage-card-${passage.index}" data-passage="${passage.index}" tabindex="-1"><div class="passage-title"><strong>Passage ${index + 1}</strong><span>${escapeHtml(confidence)}</span></div><div class="ocr-original"><span class="field-label">Original OCR</span><br>${escapeHtml(passage.ocr_text || "No OCR text")}</div><div class="field"><label for="passage-${passage.index}">Final text</label><textarea id="passage-${passage.index}" data-passage-input="${passage.index}">${escapeHtml(edited)}</textarea></div></article>`;
    }).join("");
    const evidenceUrl = `/api/evidence/${encodeURIComponent(view.run_id)}/${encodeURIComponent(pending.item_id)}`;
    app.innerHTML = `${heading(view, "Image review", p.book_title || "Review the detected passages.", "Compare every editable passage with its linked location in the source photo.")}
      <div class="review-grid">
        <section class="panel evidence-pane image-panel" aria-label="Photo evidence">
          <div class="image-toolbar"><div><strong>${display(p.book_title)}</strong><span class="muted"> · ${display(p.book_author)}</span></div><div class="tool-group"><button class="icon-button" data-zoom="out" aria-label="Zoom out">−</button><span class="zoom-copy" id="zoom-copy">100%</span><button class="icon-button" data-zoom="in" aria-label="Zoom in">+</button><button class="icon-button" data-zoom="reset" aria-label="Reset zoom">↺</button></div></div>
          <div class="image-viewport" id="image-viewport"><div class="image-scene" id="image-scene"><img class="source-image" id="source-image" src="${evidenceUrl}" alt="Current source photograph" draggable="false"></div></div>
          <div class="metadata-strip">
            <div class="metric"><span>OCR confidence</span><strong>${unknown(p.conf_ratio) ? "Unknown" : `${Math.round(Number(p.conf_ratio) * 100)}%`}</strong></div>
            <div class="metric"><span>Blur score</span><strong>${display(p.blur_score)}</strong></div>
            <div class="metric"><span>Glare score</span><strong>${display(p.glare_score)}</strong></div>
            <div class="metric ${p.flagged_retake ? "quality-warning" : ""}"><span>Retake signal</span><strong>${p.flagged_retake ? "Flagged" : "Clear"}</strong></div>
          </div>
        </section>
        <section class="panel decision-pane"><div class="pane-inner">
          <div class="pane-label"><h2>Detected passages</h2><span class="muted">${passages.length} found</span></div>
          ${operationError()}<p class="reason">${escapeHtml(p.approval_reason || pending.blocking_reason)}${p.retake_reason ? ` · ${escapeHtml(p.retake_reason)}` : ""}</p>
          <div class="field page-field"><label for="page-number">Printed page</label><input id="page-number" type="number" step="1" value="${escapeHtml(pageNumber)}" placeholder="Unknown"></div>
          <div class="passage-stack" id="passage-stack">${cards || '<p class="unknown">No passages were detected. Retake or discard this photo.</p>'}</div>
          <div class="action-area"><div class="actions">${actionButtons(pending, "approve")}</div><p class="save-state" id="save-state">${Object.keys(draft).length ? "Unsaved locally" : "No edits yet"}</p></div>
        </div></section>
      </div>`;
    bindImage(view);
    setActionsDisabled(snapshot.operation.state === "submitting");
  }

  function imageDraft(view) {
    const passages = {};
    document.querySelectorAll("[data-passage-input]").forEach((field) => { passages[field.dataset.passageInput] = field.value; });
    return { page_number: document.querySelector("#page-number")?.value ?? "", passages };
  }

  function bindImage(view) {
    const image = document.querySelector("#source-image");
    const scene = document.querySelector("#image-scene");
    const viewport = document.querySelector("#image-viewport");
    zoomState = { scale: 1, x: 0, y: 0 };
    const updateTransform = () => {
      scene.style.transform = `translate(${zoomState.x}px, ${zoomState.y}px) scale(${zoomState.scale})`;
      document.querySelector("#zoom-copy").textContent = `${Math.round(zoomState.scale * 100)}%`;
    };
    const setZoom = (next) => { zoomState.scale = Math.min(4, Math.max(.7, next)); if (zoomState.scale === 1) zoomState.x = zoomState.y = 0; updateTransform(); };
    const drawBoxes = () => {
      scene.querySelectorAll(".bbox").forEach((box) => box.remove());
      const width = image.naturalWidth, height = image.naturalHeight;
      if (!width || !height) return;
      (view.pending.payload.passages || []).forEach((passage, visualIndex) => {
        if (!Array.isArray(passage.bbox) || passage.bbox.length !== 4) return;
        const [x, y, w, h] = passage.bbox.map(Number);
        if (![x, y, w, h].every(Number.isFinite)) return;
        const box = document.createElement("button");
        box.type = "button"; box.className = "bbox"; box.dataset.passage = passage.index;
        box.setAttribute("aria-label", `Focus passage ${visualIndex + 1}`);
        Object.assign(box.style, { left: `${x / width * 100}%`, top: `${y / height * 100}%`, width: `${w / width * 100}%`, height: `${h / height * 100}%` });
        box.innerHTML = `<span class="bbox-number">${visualIndex + 1}</span>`;
        box.addEventListener("click", () => focusPassage(passage.index, true));
        scene.append(box);
      });
    };
    image.addEventListener("load", drawBoxes);
    if (image.complete) drawBoxes();
    image.addEventListener("error", () => showToast("The current photo could not be loaded."));
    document.querySelectorAll("[data-zoom]").forEach((button) => button.addEventListener("click", () => {
      if (button.dataset.zoom === "in") setZoom(zoomState.scale + .25);
      if (button.dataset.zoom === "out") setZoom(zoomState.scale - .25);
      if (button.dataset.zoom === "reset") { zoomState = { scale: 1, x: 0, y: 0 }; updateTransform(); }
    }));
    viewport.addEventListener("wheel", (event) => { if (!event.ctrlKey && !event.metaKey) return; event.preventDefault(); setZoom(zoomState.scale + (event.deltaY < 0 ? .2 : -.2)); }, { passive: false });
    let drag = null;
    viewport.addEventListener("pointerdown", (event) => { if (zoomState.scale <= 1) return; drag = { x: event.clientX - zoomState.x, y: event.clientY - zoomState.y }; viewport.setPointerCapture(event.pointerId); viewport.classList.add("dragging"); });
    viewport.addEventListener("pointermove", (event) => { if (!drag) return; zoomState.x = event.clientX - drag.x; zoomState.y = event.clientY - drag.y; updateTransform(); });
    const endDrag = () => { drag = null; viewport.classList.remove("dragging"); };
    viewport.addEventListener("pointerup", endDrag); viewport.addEventListener("pointercancel", endDrag);
    document.querySelectorAll("[data-passage-input], #page-number").forEach((field) => field.addEventListener("input", () => writeDraft(view, imageDraft(view))));
    document.querySelectorAll("[data-passage-input]").forEach((field) => {
      field.addEventListener("focus", () => focusPassage(field.dataset.passageInput, false));
      field.addEventListener("mouseenter", () => highlightPassage(field.dataset.passageInput));
    });
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.action;
      if (action !== "approve") return submitDecision(view, action, {});
      const draft = imageDraft(view);
      const edits = (view.pending.payload.passages || []).map((passage) => ({ index: passage.index, edited_text: draft.passages[String(passage.index)] ?? passage.edited_text ?? "" }));
      if (!edits.some((edit) => edit.edited_text.trim())) return showToast("At least one passage needs text before approval.");
      const rawPage = String(draft.page_number).trim();
      if (rawPage && !/^-?\d+$/.test(rawPage)) return showToast("Page number must be a whole number.");
      submitDecision(view, action, { passages: edits, page_number: rawPage ? Number(rawPage) : null });
    }));
  }

  function highlightPassage(index) {
    document.querySelectorAll("[data-passage]").forEach((node) => node.classList.toggle("active", String(node.dataset.passage) === String(index)));
  }

  function focusPassage(index, scroll) {
    highlightPassage(index);
    const field = document.querySelector(`#passage-${CSS.escape(String(index))}`);
    if (field) { field.focus({ preventScroll: !scroll }); if (scroll) field.scrollIntoView({ behavior: "smooth", block: "center" }); }
  }

  function countCards(values) {
    return Object.entries(values).map(([label, value]) => `<div class="report-stat"><strong>${escapeHtml(value ?? 0)}</strong><span>${escapeHtml(label.replaceAll("_", " "))}</span></div>`).join("");
  }

  async function loadReport(view) {
    const panel = document.querySelector("#report-panel");
    if (!panel) return;
    try {
      const response = await request(`/api/run/${encodeURIComponent(view.run_id)}/report`);
      const wrapped = response.report || {};
      const report = wrapped.data || wrapped;
      if (snapshot?.view?.run_id !== view.run_id) return;
      const intake = report.intake || {};
      const review = report.review || {};
      const capture = report.capture_counts || {};
      const processing = report.processing_counts || {};
      const dispatch = report.dispatch_counts || {};
      const failures = report.retryable_failures || [];
      const discrepancies = report.discrepancies || [];
      panel.innerHTML = `<div class="report-hero"><div><span class="eyebrow">Durable report</span><h2>${report.terminal_result === "complete" ? "Run completed without unresolved mandatory work." : "Run ended with a recorded failure."}</h2><p class="slug">${escapeHtml(report.run_id || view.run_id)}</p></div><button class="button" data-start>Start another run</button></div><div class="report-section"><h3>Intake</h3><div class="report-stats">${countCards({ discovered: intake.discovered, published: intake.published, discarded: intake.discarded, retake: intake.retake, failed: intake.failed })}</div></div><div class="report-section report-columns"><div><h3>Knowledge processing</h3><div class="report-stats compact">${countCards({ captured: capture.captured ?? (report.capture || []).length, processed: processing.processed ?? (report.processing || []).length, flagged: review.flagged, resolved: review.resolved })}</div></div><div><h3>Dispatch results</h3><div class="dispatch-list">${Object.keys(dispatch).length ? Object.entries(dispatch).map(([target, count]) => `<div><span>${escapeHtml(target)}</span><strong>${escapeHtml(count)}</strong></div>`).join("") : '<p class="muted">No downstream dispatches were required.</p>'}</div></div></div>${failures.length ? `<div class="report-section report-alert"><h3>Retryable failures</h3><ul>${failures.map((failure) => `<li>${escapeHtml(failure.detail || failure.status || JSON.stringify(failure))}</li>`).join("")}</ul></div>` : ""}${discrepancies.length ? `<div class="report-section report-alert"><h3>Discrepancies</h3><ul>${discrepancies.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}`;
      panel.querySelector("[data-start]")?.addEventListener("click", startRun);
    } catch (error) {
      panel.innerHTML = `<div class="report-error"><h2>The run ended, but its report could not be read.</h2><p>${escapeHtml(error.message)}</p><button class="button" data-report-retry>Try reading report again</button></div>`;
      panel.querySelector("[data-report-retry]")?.addEventListener("click", () => loadReport(view));
    }
  }

  async function submitDecision(view, action, payload, options = {}) {
    if (snapshot.operation.state === "submitting") return;
    submittedDraftKey = pendingKey(view);
    submittedRevision = snapshot.operation.revision;
    setActionsDisabled(true);
    try {
      acceptSnapshot(await request("/api/run/decision", { method: "POST", body: JSON.stringify({ run_id: view.run_id, item_id: view.pending.item_id, gate: view.pending.gate, action, payload, resolver: options.resolver || "", note: options.note || "" }) }));
    } catch (error) {
      submittedDraftKey = null;
      submittedRevision = null;
      setActionsDisabled(false); setSaveState("Failed — draft retained", true); showToast(error.message);
    }
  }

  async function startRun() {
    try { startRequested = true; acceptSnapshot(await request("/api/run/start", { method: "POST" })); }
    catch (error) { showToast(error.message); }
  }

  async function retryRun() {
    try { acceptSnapshot(await request("/api/run/retry", { method: "POST" })); }
    catch (error) { showToast(error.message); }
  }

  document.addEventListener("keydown", (event) => {
    const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName || "");
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault(); document.querySelector("[data-action].primary:not(:disabled)")?.click(); return;
    }
    if (typing || snapshot?.operation?.state === "submitting") return;
    if (event.altKey && event.key.toLowerCase() === "d") document.querySelector('[data-action="discard"]')?.click();
    if (event.altKey && event.key.toLowerCase() === "r") document.querySelector('[data-action="retake"]')?.click();
    if (["j", "k"].includes(event.key.toLowerCase())) {
      const fields = [...document.querySelectorAll("[data-passage-input]")];
      if (!fields.length) return;
      event.preventDefault();
      const current = fields.indexOf(document.activeElement);
      const delta = event.key.toLowerCase() === "j" ? 1 : -1;
      fields[(current + delta + fields.length) % fields.length].focus();
    }
    if (event.key === "+" || event.key === "=") document.querySelector('[data-zoom="in"]')?.click();
    if (event.key === "-") document.querySelector('[data-zoom="out"]')?.click();
    if (event.key === "Escape") document.querySelector('[data-zoom="reset"]')?.click();
  });

  refresh();
})();
