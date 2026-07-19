/* MatchDay Copilot frontend — vanilla JS, no dependencies. */
"use strict";

const $ = (id) => document.getElementById(id);

/* ---------- helpers ---------- */

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/* ---------- chat ---------- */

function addUserMessage(text) {
  const msg = el("div", "msg user");
  msg.appendChild(el("p", null, text));
  appendToLog(msg);
}

function addBotMessage(data) {
  const msg = el("div", "msg bot");
  // Tag non-English replies so screen readers switch pronunciation.
  msg.lang = $("language").value;
  msg.appendChild(el("p", null, data.message));

  const meta = el(
    "p",
    data.priority === "P1" ? "meta p1" : "meta",
    `${data.intent} · ${data.priority} · ${data.generated_by}`
  );
  msg.appendChild(meta);

  if (data.actions && data.actions.length) {
    const actions = el("ul");
    data.actions.forEach((a) => actions.appendChild(el("li", null, a)));
    msg.appendChild(actions);
  }

  if (data.reasoning && data.reasoning.length) {
    const details = el("details");
    details.appendChild(el("summary", null, "Why this answer?"));
    const list = el("ul");
    data.reasoning.forEach((r) => list.appendChild(el("li", null, r)));
    details.appendChild(list);
    msg.appendChild(details);
  }
  appendToLog(msg);
}

function addErrorMessage(text) {
  const msg = el("div", "msg bot");
  msg.appendChild(el("p", null, `⚠ ${text}`));
  appendToLog(msg);
}

function appendToLog(node) {
  const log = $("chat-log");
  log.appendChild(node);
  log.scrollTop = log.scrollHeight;
}

$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("message");
  const text = input.value.trim();
  if (!text) return;
  addUserMessage(text);
  input.value = "";
  try {
    const data = await api("/api/assist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        role: $("role").value,
        language: $("language").value,
        zone: $("zone").value || null,
        accessibility_needs: $("accessibility").checked,
      }),
    });
    addBotMessage(data);
  } catch (err) {
    addErrorMessage(err.message);
  }
});

/* ---------- live ops dashboard ---------- */

function renderState(state) {
  const zones = $("zones");
  zones.replaceChildren();
  state.zones.forEach((zone) => {
    const item = el("li");
    const label = el("div", "zone-name");
    label.appendChild(el("span", null, zone.name));
    const pct = Math.round(zone.occupancy * 100);
    label.appendChild(
      el("span", zone.alert ? "zone-alert" : null, zone.alert ? `${pct}% ⚠` : `${pct}%`)
    );
    const bar = el("div", zone.occupancy >= 0.9 ? "bar high" : "bar");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${zone.name} ${pct} percent full`);
    const fill = el("span");
    fill.style.width = `${pct}%`;
    bar.appendChild(fill);
    item.append(label, bar);
    zones.appendChild(item);
  });

  const gates = $("gates");
  gates.replaceChildren();
  state.gates.forEach((gate) => {
    const row = el("tr");
    row.appendChild(el("td", null, `${gate.id} — ${gate.name}`));
    row.appendChild(el("td", null, gate.zone));
    row.appendChild(el("td", null, gate.step_free ? "Yes" : "No"));
    row.appendChild(el("td", null, `${Math.round(gate.load * 100)}%`));
    gates.appendChild(row);
  });
}

async function refreshState() {
  try {
    renderState(await api("/api/stadium/state"));
  } catch {
    /* transient — retry on next poll */
  }
}

/* ---------- incidents ---------- */

function renderIncidents(items) {
  const list = $("incidents");
  list.replaceChildren();
  items
    .slice()
    .reverse()
    .forEach((incident) => {
      const item = el(
        "li",
        incident.priority.toLowerCase(),
        `[${incident.priority}] ${incident.zone}: ${incident.description}`
      );
      list.appendChild(item);
    });
}

$("incident-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/incidents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        description: $("incident-desc").value,
        zone: $("incident-zone").value,
        reporter_role: $("role").value,
      }),
    });
    $("incident-desc").value = "";
    renderIncidents(await api("/api/incidents"));
  } catch (err) {
    addErrorMessage(err.message);
  }
});

/* ---------- boot ---------- */

(async function boot() {
  try {
    const health = await api("/healthz");
    $("llm-status").textContent =
      health.llm === "rules-only"
        ? "Engine: deterministic rules (no API key needed)"
        : `Engine: rules + ${health.llm} polish`;
  } catch {
    $("llm-status").textContent = "Engine status unavailable";
  }
  await refreshState();
  setInterval(refreshState, 5000);
})();
