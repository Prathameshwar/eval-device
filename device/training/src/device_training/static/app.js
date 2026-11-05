"use strict";
const $ = id => document.getElementById(id);
let token = "", config, current, local, access = null, control = null, requestKey = null;
const urls = new Set();
const base = () => `/platform/organizations/${config.organization_id}/training`;
const sid = () => current?.id;
function clearMedia() { for (const url of urls) URL.revokeObjectURL(url); urls.clear(); $("timeline").replaceChildren(); $("frame").hidden = true; }
async function api(path, method = "GET", body, bearer = token, blob = false) {
  const response = await fetch(path, {method, headers: {Authorization: `Bearer ${bearer}`, ...(body === undefined ? {} : {"Content-Type": "application/json"})}, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store", credentials: "omit", redirect: "error"});
  if (!response.ok) { let detail = await response.json().catch(() => ({})); throw new Error(detail.detail || detail.error?.message || `Request failed (${response.status}). Check session state before retrying.`); }
  return blob ? response.blob() : response.json();
}
async function grant(isControl = false) {
  let value = isControl ? control : access;
  if (!value || Date.parse(value.expires_at) - Date.now() < 5000) {
    value = await api(`${base()}/sessions/${sid()}/access${isControl ? "?control=true" : ""}`, "POST", {});
    if (isControl) control = value; else access = value;
  }
  return value.grant;
}
function option(value, label) { const item = document.createElement("option"); item.value = value; item.textContent = label; return item; }
function text(tag, value) { const element = document.createElement(tag); element.textContent = value; return element; }
async function refresh() {
  const [cases, sessions] = await Promise.all([api(`${base()}/scenarios`), api(`${base()}/sessions`)]);
  $("scenario").replaceChildren(...cases.items.filter(c => c.approved && c.is_active).map(c => option(c.id, `${c.title} (v${c.version})`)));
  $("session").replaceChildren(...sessions.items.map(s => option(s.id, `${s.created_at} ? ${s.language} ? ${s.status}`)));
  if (sid()) $("session").value = sid();
}
async function load() {
  if (!$("session").value) throw new Error("Choose a session first.");
  current = await api(`${base()}/sessions/${$("session").value}`);
  access = control = null;
  local = await api(`/sessions/${sid()}`, "GET", undefined, await grant());
  $("status").textContent = `${local.simulated ? "SIMULATED ? " : ""}${local.status} ? recording: ${local.recording_status} ? platform sync: ${local.sync_status}`;
  clearMedia();
  for (const turn of local.turns) {
    const row = document.createElement("article");
    row.append(text("small", `${(turn.start_ms/1000).toFixed(1)}s ? playback: ${turn.playback}${turn.fallback ? " ? clarification fallback" : ""}`), text("p", `Learner: ${turn.text || "?"}`), text("p", `Patient: ${turn.answer || "?"}`));
    for (const kind of ["learner", "patient"]) {
      if ((kind === "learner" && turn.kind === "greeting") || turn.playback === "processing") continue;
      const button = text("button", `Review ${kind} audio`);
      button.addEventListener("click", () => action(button, async () => {
        const blob = await api(`/sessions/${sid()}/turns/${turn.id}/${kind}.wav`, "GET", undefined, await grant(), true);
        const url = URL.createObjectURL(blob); urls.add(url);
        const audio = document.createElement("audio"); audio.controls = true; audio.src = url; row.append(audio);
        const origin = kind === "learner" ? turn.start_ms : (turn.started_ms ?? turn.start_ms);
        let lastFrame = -1;
        audio.addEventListener("timeupdate", async () => {
          const at = origin + audio.currentTime*1000;
          const frames = local.replay_frames || [];
          const index = frames.findLastIndex(f => f.offset_ms <= at);
          if (index < 0 || index === lastFrame) return;
          lastFrame = index;
          try { const frame = await api(`/sessions/${sid()}/frames/${index}.jpg`, "GET", undefined, await grant(), true); const image = URL.createObjectURL(frame); urls.add(image); if (index === lastFrame) { $("frame").src = image; $("frame").hidden = false; } } catch (error) { $("error").textContent = error.message; }
        });
        await audio.play();
      }));
      row.append(button);
    }
    $("timeline").append(row);
  }
  $("downloads").replaceChildren();
  for (const video of local.video) {
    const button = text("button", "List original video segments");
    button.addEventListener("click", () => action(button, async () => {
      const manifest = await api(`/sessions/${sid()}/video/${video.id}`, "GET", undefined, await grant());
      button.disabled = true;
      for (let index=0; index<manifest.segments; index++) {
        const download = text("button", `Download segment ${index+1}`);
        download.addEventListener("click", () => action(download, async () => {
          const blob = await api(`/sessions/${sid()}/video/${video.id}/${index}.mkv`, "GET", undefined, await grant(), true);
          const url = URL.createObjectURL(blob); urls.add(url); const link = document.createElement("a"); link.href = url; link.download = `${video.id}-${index}.mkv`; link.click();
        })); $("downloads").append(download);
      }
    })); $("downloads").append(button);
  }
  const rubric = await api(`${base()}/sessions/${sid()}/rubric`);
  $("rubric").replaceChildren();
  for (const item of rubric.items) { const label = text("label", item.description); const select = document.createElement("select"); select.dataset.rubric = item.id; for (const value of ["not_observed","met","partial","not_met"]) select.append(option(value, value.replaceAll("_"," "))); select.value = current.feedback?.scores[item.id] || "not_observed"; label.append(select); $("rubric").append(label); }
  $("comments").value = current.feedback?.comments || "";
}
async function action(button, work) { button.disabled = true; $("error").textContent = ""; try { await work(); } catch (error) { $("error").textContent = error.message; } finally { button.disabled = false; } }
function bind(id, work) { $(id).addEventListener("click", () => action($(id), work)); }
bind("connect", async () => { token = $("token").value.trim(); $("token").value = ""; config = await (await fetch("/configuration")).json(); await refresh(); });
bind("logout", async () => { token = ""; access = control = current = local = null; clearMedia(); $("rubric").replaceChildren(); $("downloads").replaceChildren(); $("comments").value = ""; $("status").textContent = "Access cleared"; });
bind("refresh", refresh); bind("open", load);
bind("create", async () => { requestKey ||= crypto.randomUUID(); const row = await api(`${base()}/sessions`, "POST", {request_key: requestKey, device_id: config.device_id, learner_id: $("learner").value.trim(), scenario_id: $("scenario").value, language: $("language").value, duration_seconds: Number($("duration").value)}); requestKey = null; current = row; await refresh(); $("status").textContent = "Session authorized. The paired Pi will start it; open the session to review status."; });
bind("stop", async () => { if (!sid()) throw new Error("Open a session first."); let localError; try { await api(`/sessions/${sid()}/stop`, "POST", {}, await grant(true)); } catch(error) { localError = error; } await api(`${base()}/sessions/${sid()}/stop`, "POST", {}); await load(); if (localError) throw new Error("Platform stop saved. Local connection unavailable; the Pi stops when its lease expires."); });
bind("finish", async () => { await api(`/sessions/${sid()}/stop`, "POST", {status:"completed"}, await grant(true)); await load(); });
bind("prepare", async () => { await api(`/sessions/${sid()}/prepare-replay`, "POST", {}, await grant()); await load(); });
$("feedback").addEventListener("submit", event => { event.preventDefault(); action(event.submitter, async () => { const scores = Object.fromEntries([...document.querySelectorAll("[data-rubric]")].map(s => [s.dataset.rubric, s.value])); await api(`${base()}/sessions/${sid()}/feedback`, "POST", {expected_version: current.feedback_version, scores, comments: $("comments").value}); await load(); }); });
