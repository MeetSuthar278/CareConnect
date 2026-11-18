/* Same-origin API integration. Polling only performs GET requests. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const form = $("request-form");
  if (!form) return;
  const terminal = new Set(["matched", "unmatched", "completed", "cancelled", "in_progress"]);
  let catalogs = null, requestId = null, posting = false, fetching = false;
  let timer = null, pollUntil = 0, generation = 0;
  const labels = {submitted:"Submitted", matched:"Matched", unmatched:"Unmatched",
    in_progress:"In progress", completed:"Completed", cancelled:"Cancelled"};

  function message(text) {
    $("form-message").textContent = text;
    $("form-message").hidden = !text;
  }
  async function api(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(url, {...options, signal:controller.signal, cache:"no-store"});
      let data;
      try { data = await response.json(); } catch (_) { throw new Error("The server returned an unreadable response."); }
      if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
      return data;
    } finally { clearTimeout(timeout); }
  }
  function errorText(error) {
    return error.name === "AbortError" ? "The server took too long to respond." :
      error instanceof TypeError ? "Could not connect to CareConnect. Check your connection and Flask server." : error.message;
  }
  function fillSelect(id, rows, label) {
    const select = $(id);
    select.replaceChildren(new Option(select.options[0].text, ""));
    for (const row of rows) select.add(new Option(label(row), String(row.id)));
  }
  async function loadCatalogs() {
    message(""); $("catalog-loading").hidden = false; $("catalog-retry").hidden = true;
    $("request-fields").disabled = true;
    try {
      const [services, areas, priorities] = await Promise.all([
        api("/api/services"), api("/api/service-areas"), api("/api/priorities")]);
      if (![services, areas, priorities].every(rows => Array.isArray(rows) && rows.length &&
          rows.every(row => Number.isInteger(row.id) && row.id > 0))) {
        throw new Error("The service catalog is unavailable or empty. Please try again later.");
      }
      catalogs = {services, areas, priorities};
      fillSelect("service", services, r => r.name);
      fillSelect("area", areas, r => `${r.region}, ${r.city}`);
      fillSelect("priority", priorities, r => `${r.name} - ${r.deadline_hours} hours`);
      $("request-fields").disabled = form.dataset.demoEnabled !== "true" || Boolean(requestId) || posting;
      if (form.dataset.demoEnabled !== "true") message("This preview cannot submit requests. Start the local demo server using run.py.");
    } catch (error) { message(errorText(error)); $("catalog-retry").hidden = false; }
    finally { $("catalog-loading").hidden = true; }
  }
  function lookup(rows, id, label) {
    const row = rows?.find(r => r.id === id);
    return row ? label(row) : `ID ${id ?? "unavailable"}`;
  }
  function render(data) {
    $("status-empty").hidden = true; $("status-content").hidden = false;
    $("detail-id").textContent = `#${data.request_id}`;
    $("detail-service").textContent = lookup(catalogs?.services, data.service_id, r => r.name);
    $("detail-area").textContent = lookup(catalogs?.areas, data.service_area_id, r => `${r.region}, ${r.city}`);
    $("detail-priority").textContent = lookup(catalogs?.priorities, data.priority_id, r => r.name);
    const deadline = new Date(data.attendance_deadline);
    $("detail-deadline").textContent = data.attendance_deadline && !Number.isNaN(deadline.valueOf()) ?
      new Intl.DateTimeFormat(undefined, {dateStyle:"medium", timeStyle:"short"}).format(deadline) + " (your local time)" : "Not available";
    $("status-badge").textContent = labels[data.status] || data.status || "Unknown";
    $("status-badge").dataset.status = data.status;
    $("status-explanation").textContent = data.status === "matched" ?
      "Your request has been matched with an eligible organization. This does not confirm acceptance or attendance." :
      data.status === "unmatched" ? "No match was made. Your request needs coordinator assistance." :
      data.status === "submitted" ? "Your request is saved and awaiting matching. We will check for updates automatically." :
      "This is the latest request status reported by CareConnect.";
  }
  function stopPolling() { clearTimeout(timer); timer = null; }
  async function refresh(manual = false) {
    if (!requestId || fetching) return;
    stopPolling(); fetching = true; $("refresh-status").disabled = true;
    const mine = generation, id = requestId;
    try {
      const data = await api(`/api/requests/${id}`);
      if (mine !== generation) return;
      if (data.request_id !== id || typeof data.status !== "string") throw new Error("Unexpected request status response.");
      render(data);
      $("poll-message").textContent = `Updated ${new Date().toLocaleTimeString()}.`;
      if (terminal.has(data.status)) { pollUntil = 0; }
      else if (Date.now() < pollUntil) timer = setTimeout(() => refresh(), 2000);
      else $("poll-message").textContent = "Automatic updates paused after two minutes. Use Refresh status to check again.";
    } catch (error) {
      if (mine !== generation) return;
      $("poll-message").textContent = errorText(error) + " Use Refresh status to try again. Your saved request has not been resubmitted.";
      // Transient failures keep retrying only within the original two-minute window.
      if (!manual && Date.now() < pollUntil) timer = setTimeout(() => refresh(), 2000);
    } finally {
      fetching = false; $("refresh-status").disabled = false;
    }
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (posting || requestId || !catalogs || form.dataset.demoEnabled !== "true") return;
    for (const id of ["title", "description"]) {
      $(id).setCustomValidity($(id).value.trim() ? "" : "Please enter a value, not only spaces.");
    }
    if (!form.reportValidity()) return;
    const payload = {service_id:Number($("service").value), service_area_id:Number($("area").value),
      priority_id:Number($("priority").value), title:$("title").value.trim(), description:$("description").value.trim()};
    posting = true; $("request-fields").disabled = true;
    $("submit-request").textContent = "Submitting..."; message("");
    try {
      const data = await api("/api/requests", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
      if (!Number.isInteger(data.request_id) || data.request_id <= 0) throw new Error("The server did not return a valid request ID.");
      requestId = data.request_id;
      try { sessionStorage.setItem("careconnect.requestId", String(requestId)); } catch (_) { /* optional recovery */ }
      $("submission-receipt").textContent = `Request #${requestId} saved | Initial status: ${labels[data.status] || data.status}`;
      render({...payload, ...data});
      pollUntil = Date.now() + 120000;
      $("poll-message").textContent = "Checking for matching updates...";
      $("new-request").hidden = false;
      $("submit-request").textContent = "Request submitted";
      $("status-heading").setAttribute("tabindex", "-1"); $("status-heading").focus();
      timer = setTimeout(() => refresh(), 2000);
    } catch (error) {
      message(errorText(error) + " If the connection failed, the request may already have been saved. Check /api/requests before starting another; submission is never retried automatically.");
      $("submit-request").textContent = "Submission stopped";
      $("new-request").hidden = false;
    } finally { posting = false; }
  });
  for (const id of ["title", "description"]) $(id).addEventListener("input", () => $(id).setCustomValidity(""));
  $("refresh-status").addEventListener("click", () => refresh(true));
  $("catalog-retry").addEventListener("click", loadCatalogs);
  $("new-request").addEventListener("click", () => {
    if (fetching || posting) return;
    generation++; stopPolling(); requestId = null; pollUntil = 0;
    try { sessionStorage.removeItem("careconnect.requestId"); } catch (_) {}
    form.reset(); message(""); $("new-request").hidden = true;
    $("submit-request").textContent = "Submit Request";
    $("status-content").hidden = true; $("status-empty").hidden = false;
    $("request-fields").disabled = !catalogs || form.dataset.demoEnabled !== "true";
    $("service").focus();
  });
  window.addEventListener("pagehide", stopPolling);
  (async () => {
    await loadCatalogs();
    try {
      const saved = Number(sessionStorage.getItem("careconnect.requestId"));
      if (Number.isInteger(saved) && saved > 0 && form.dataset.demoEnabled === "true") {
        requestId = saved; $("request-fields").disabled = true; $("new-request").hidden = false;
        $("status-empty").hidden = true; $("status-content").hidden = false;
        $("detail-id").textContent = `#${saved}`;
        $("submission-receipt").textContent = "Restored your last request in this tab. No new submission was made.";
        pollUntil = Date.now() + 120000; await refresh();
      }
    } catch (_) { /* Session storage is optional. */ }
  })();
})();
