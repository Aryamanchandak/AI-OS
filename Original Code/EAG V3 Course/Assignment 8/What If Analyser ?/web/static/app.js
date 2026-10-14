(() => {
  "use strict";

  const form = document.querySelector("#analysis-form");
  const briefInput = document.querySelector("#brief");
  const modeInput = document.querySelector("#mode");
  const submitButton = form?.querySelector("button[type='submit']");
  const progressPanel = document.querySelector("#progress-panel");
  const progressList = document.querySelector("#progress-list");
  const formError = document.querySelector("#form-error");
  const results = document.querySelector("#results");
  const runCost = document.querySelector("#run-cost");
  const runCostInr = document.querySelector("#run-cost-inr");
  const runCallCount = document.querySelector("#run-call-count");
  const runTokenCount = document.querySelector("#run-token-count");
  const runCostNote = document.querySelector("#run-cost-note");

  let activeStream = null;
  let vizInstancePromise = null;

  function showError(message) {
    formError.textContent = message;
    formError.hidden = false;
  }

  function clearError() {
    formError.textContent = "";
    formError.hidden = true;
  }

  function addProgress(message, stepId) {
    const item = document.createElement("li");
    item.textContent = message;
    item.dataset.stepId = stepId;
    progressList.append(item);
  }

  function updateCost(usage) {
    if (!usage || !runCost) return;
    runCost.hidden = false;
    runCostInr.textContent = `₹${Number(usage.cost_inr || 0).toFixed(2)}`;
    runCallCount.textContent = Number(usage.calls || 0).toLocaleString("en-IN");
    runTokenCount.textContent = Number(usage.total_tokens || 0).toLocaleString("en-IN");
    runCostNote.textContent = `Paid-tier estimate at ₹${Number(usage.usd_to_inr || 0).toFixed(2)}/USD; actual billing may differ.`;
  }

  function resetCost() {
    if (!runCost) return;
    runCost.hidden = false;
    runCostInr.textContent = "₹0.00";
    runCallCount.textContent = "0";
    runTokenCount.textContent = "0";
    runCostNote.textContent = "Paid-tier estimate; actual billing may differ.";
  }

  async function renderGraph(shell) {
    const source = shell.querySelector(".graph-dot");
    const output = shell.querySelector(".graph-output");
    const fallback = shell.querySelector(".graph-fallback");
    if (!source || !output || !fallback) return;

    let dot;
    try {
      dot = JSON.parse(source.textContent);
      if (!window.Viz?.instance) {
        throw new Error("The local Graphviz renderer did not load.");
      }
      vizInstancePromise ||= window.Viz.instance();
      const viz = await vizInstancePromise;
      const svg = viz.renderSVGElement(dot);
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", "Causal graph");
      output.replaceChildren(svg);
    } catch (error) {
      output.innerHTML = "";
      fallback.hidden = false;
      const note = document.createElement("p");
      note.className = "notice notice-warning";
      note.textContent = `${error.message} DOT source is shown below.`;
      output.append(note);
    }
  }

  function renderGraphs(root = document) {
    root.querySelectorAll("[data-graphviz]").forEach(renderGraph);
  }

  async function loadResult(jobId) {
    const response = await fetch(`/result/${encodeURIComponent(jobId)}`, {
      headers: { Accept: "text/html" },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "The completed result could not be loaded.");
    }
    const html = await response.text();
    results.innerHTML = html;
    results.classList.remove("is-refreshing");
    await renderGraphs(results);
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function followProgress(jobId) {
    activeStream?.close();
    activeStream = new EventSource(`/events/${encodeURIComponent(jobId)}`);

    activeStream.onmessage = async (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "usage") {
        updateCost(payload.usage);
        return;
      }
      addProgress(payload.message, payload.step_id);

      if (payload.type === "complete") {
        activeStream.close();
        progressPanel.classList.add("is-complete");
        try {
          await loadResult(jobId);
        } catch (error) {
          showError(error.message);
          results.classList.remove("is-refreshing");
        } finally {
          submitButton.disabled = false;
        }
      }

      if (payload.type === "error") {
        activeStream.close();
        showError(payload.message);
        results.classList.remove("is-refreshing");
        submitButton.disabled = false;
      }
    };

    activeStream.onerror = () => {
      activeStream.close();
      showError("The progress connection was interrupted. The running job was not cancelled.");
      results.classList.remove("is-refreshing");
      submitButton.disabled = false;
    };
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();

    const brief = briefInput.value.trim();
    if (!brief) {
      showError("Type a situation first.");
      briefInput.focus();
      return;
    }

    submitButton.disabled = true;
    progressPanel.hidden = false;
    progressPanel.classList.remove("is-complete");
    progressList.innerHTML = "";
    resetCost();
    results.classList.add("is-refreshing");
    addProgress("Starting analysis", "analysis_start");

    try {
      const response = await fetch("/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          brief,
          mode: modeInput.value,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "The analysis could not be started.");
      }
      followProgress(payload.job_id);
    } catch (error) {
      showError(error.message);
      results.classList.remove("is-refreshing");
      submitButton.disabled = false;
    }
  });

  window.addEventListener("beforeunload", () => activeStream?.close());
  window.addEventListener("DOMContentLoaded", () => renderGraphs());
})();
