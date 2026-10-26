/* Breadcrumbs front end. Plain JS + Leaflet.
   Works in two modes:
   - demo: loads demo/session.json (precomputed with the real model), no backend needed
   - live: uploads photos to the local server (server/app.py) and polls for the result */

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const state = {
  mode: null,          // "demo" | "live"
  data: null,          // analysis result
  job: null,
  step: 0,             // number of photos added in the replay
  playing: null,
  fixed: false,
  files: [],
  home: null,
};

/* ------------------------------------------------------------------ routing */
function show(view) {
  for (const id of ["landing", "upload", "analysis"]) $("#" + id).hidden = id !== view;
  if (view === "analysis") setTimeout(() => map && map.invalidateSize(), 50);
  if (view === "upload") setTimeout(() => homeMap && homeMap.invalidateSize(), 50);
  $("#modePill").hidden = view !== "analysis";
  window.scrollTo(0, 0);
}
$$("[data-nav=home]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); stop(); show("landing"); }));

$("#startDemo").addEventListener("click", async () => {
  const res = await fetch("demo/session.json");
  state.mode = "demo";
  load(await res.json());
});
$("#startOwn").addEventListener("click", () => { show("upload"); initHomeMap(); checkServer(); });

/* ------------------------------------------------------------------ maps */
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
let map, layers;

function initMap() {
  if (map) return;
  map = L.map("map", { zoomControl: false, worldCopyJump: true }).setView([25, 0], 2);
  L.control.zoom({ position: "topright" }).addTo(map);
  L.tileLayer(TILES, { attribution: ATTR, maxZoom: 19, className: "tiles" }).addTo(map);
  layers = L.layerGroup().addTo(map);
}

const icon = (cls) => L.divIcon({ className: "", html: `<div class="${cls}"></div>`, iconSize: [22, 22], iconAnchor: [11, 11] });

function drawBelief(s, { fly = true } = {}) {
  layers.clearLayers();
  const home = state.data.home;
  if (s) {
    const maxW = Math.max(...s.heat.map((h) => h[2]), 1e-9);
    for (const [lat, lon, w] of s.heat.slice(0, 250)) {
      const a = Math.pow(w / maxW, 0.5);
      if (a < 0.04) continue;
      L.circle([lat, lon], { radius: 850, stroke: false, fillColor: "#d6402b", fillOpacity: 0.08 + 0.5 * a }).addTo(layers);
    }
    const area = L.circle([s.lat, s.lon], { radius: s.radius_km * 1000, color: "#d6402b", weight: 2, dashArray: "6 6", fillColor: "#d6402b", fillOpacity: 0.05 }).addTo(layers);
    L.marker([s.lat, s.lon], { icon: icon("guess-marker"), zIndexOffset: 500 }).addTo(layers);
    if (fly) {
      const b = area.getBounds();
      if (home) b.extend(home);
      map.flyToBounds(b.pad(0.25), { duration: 1.2, maxZoom: 14 });
    }
  } else if (fly) {
    map.flyTo([25, 0], 2, { duration: 1 });
  }
  if (home) {
    L.circle(home, { radius: 2000, color: "#1f4fd1", weight: 1.5, dashArray: "2 5", fill: false }).addTo(layers);
    L.marker(home, { icon: icon("home-marker"), zIndexOffset: 1000 }).addTo(layers);
  }
}

/* ------------------------------------------------------------------ load result */
function photoSrc(i, fixed = false) {
  const p = state.data.photos[i];
  if (state.mode === "demo") return fixed && p.fixed ? p.fixed : p.src;
  return `/api/jobs/${state.job}/photo/${i}${fixed ? "?fixed=1" : ""}`;
}

function load(data) {
  state.data = data;
  state.step = 0;
  state.fixed = false;
  show("analysis");
  initMap();
  $("#modePill").hidden = false;
  $("#modePill").textContent = state.mode === "demo" ? "Demo feed" : "Your photos";
  const noHome = !data.home;
  $(".gauge-cap").innerHTML = noHome
    ? `the AI's confidence in its <b>top ~2 km area</b><br><span class="muted">(mark your home to measure distance)</span>`
    : `chance the AI picks <b>your neighbourhood</b><br><span class="muted">(within 2 km of home)</span>`;
  $("#modelNote").textContent = `Model: ${data.model}.` + (noHome ? "" : " Neighbourhood = within 2 km of the marked home.");
  renderFeed();
  renderSpark();
  renderRank();
  renderPlan();
  setTab("replay");
  setStep(0);
}

function renderFeed() {
  const n = state.data.photos.length;
  $("#railCount").textContent = `${n} photos`;
  $("#feed").innerHTML = state.data.photos.map((p, i) =>
    `<li data-i="${i}"><img src="${photoSrc(i)}" alt="Posted photo ${i + 1}" loading="lazy"><span class="tag">#${i + 1}</span></li>`).join("");
  $$("#feed li").forEach((li) => li.addEventListener("click", () => {
    const i = +li.dataset.i;
    if ($("#tab-leaks").hidden) { stop(); setStep(i + 1); } else selectLeak(i);
  }));
}

function renderSpark() {
  $("#spark").innerHTML = state.data.replay.map(() => "<i></i>").join("");
}

/* ------------------------------------------------------------------ replay */
const pct = (x) => Math.round(x * 100);
const km = (x) => (x == null ? "—" : x < 10 ? `${x.toFixed(1)} km` : `${Math.round(x).toLocaleString()} km`);

function setStep(k) {
  const R = state.data.replay;
  state.step = Math.max(0, Math.min(R.length, k));
  const s = state.step ? R[state.step - 1] : null;
  $$("#feed li").forEach((li, i) => {
    li.classList.toggle("in", i < state.step);
    li.classList.toggle("current", i === state.step - 1);
  });
  animateNumber($("#oddsNum"), s ? pct(s.home_mass ?? 0) : 0);
  $$("#spark i").forEach((bar, i) => {
    const v = R[i].home_mass ?? 0;
    bar.style.height = i < state.step ? `${Math.max(4, v * 64)}px` : "3px";
    bar.classList.toggle("on", i < state.step);
  });
  $("#statGuess").textContent = s && s.home_km != null ? km(s.home_km) : "—";
  $("#statArea").textContent = s ? km(s.radius_km) : "—";
  $("#stepLabel").textContent = s ? `After photo ${state.step} of ${R.length}` : "Before any photos";
  $("#replayNote").innerHTML = s ? noteFor(state.step - 1) : "Press play to add the photos one by one, in the order they were posted.";
  drawBelief(s);
  showPop(s ? state.step - 1 : null);
}

function noteFor(i) {
  const R = state.data.replay;
  const s = R[i], alone = s.photo_alone || {};
  const prev = i ? R[i - 1].home_mass : 0;
  const delta = pct(s.home_mass) - pct(prev);
  const aloneTxt = alone.home_km != null
    ? (alone.home_km < 2 ? `On its own, this photo points ${km(alone.home_km)} from home.` :
       alone.home_km > 500 ? `On its own, this photo points somewhere else entirely (${km(alone.home_km)} away).` :
       `On its own, this photo lands ${km(alone.home_km)} from home.`)
    : "";
  const where = state.data.home ? "for your neighbourhood" : "of confidence";
  const deltaTxt = delta > 0 ? `<b>+${delta} points</b> ${where}.` : delta < 0 ? `${delta} points — this one muddies the picture.` : "No change.";
  return `${aloneTxt} ${deltaTxt}`;
}

function showPop(i) {
  if (i == null) { $("#photoPop").hidden = true; return; }
  const alone = state.data.replay[i].photo_alone || {};
  $("#photoPop").hidden = false;
  $("#popImg").src = photoSrc(i, state.fixed);
  $("#popIdx").textContent = `Photo #${i + 1}`;
  $("#popAlone").textContent = alone.home_km != null ? `alone: ${km(alone.home_km)} off` : "";
}

function animateNumber(el, to) {
  const from = +el.textContent || 0;
  const t0 = performance.now();
  const tick = (t) => {
    const f = Math.min(1, (t - t0) / 600);
    el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - f, 3)));
    if (f < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function play() {
  if (state.playing) return stop();
  if (state.step >= state.data.replay.length) setStep(0);
  $("#playBtn").textContent = "❚❚ Pause";
  state.playing = setInterval(() => {
    if (state.step >= state.data.replay.length) return stop();
    setStep(state.step + 1);
  }, 2200);
  setStep(state.step + 1);
}
function stop() {
  clearInterval(state.playing);
  state.playing = null;
  $("#playBtn").textContent = "▶ Play feed";
}
$("#playBtn").addEventListener("click", play);
$("#stepFwd").addEventListener("click", () => { stop(); setStep(state.step + 1); });
$("#stepBack").addEventListener("click", () => { stop(); setStep(state.step - 1); });

/* ------------------------------------------------------------------ tabs */
function setTab(t) {
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
  for (const id of ["replay", "leaks", "fix"]) $("#tab-" + id).hidden = id !== t;
  stop();
  if (t === "replay") setStep(state.step || 0);
  if (t === "leaks") { setStep(state.data.replay.length); if (!state.leakSel) selectLeak(rankOrder()[0]); }
  if (t === "fix") { $("#photoPop").hidden = true; drawBelief(state.fixed ? state.data.plan.after : state.data.replay.at(-1)); }
}
$$(".tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

/* ------------------------------------------------------------------ giveaways */
function contribution(i) {
  const full = state.data.replay.at(-1).home_mass ?? 0;
  const w = state.data.influence[i].without_home_mass;
  return w == null ? 0 : Math.max(0, full - w);
}
function rankOrder() {
  return state.data.photos.map((_, i) => i).sort((a, b) => contribution(b) - contribution(a));
}
function renderRank() {
  const order = rankOrder();
  const max = Math.max(...order.map(contribution), 1e-6);
  $("#rank").innerHTML = order.slice(0, 6).map((i) => `
    <li data-i="${i}">
      <img src="${photoSrc(i)}" alt="">
      <div>
        <div class="rl"><span>Photo #${i + 1}</span><b>${contribution(i) > 0.005 ? "−" + pct(contribution(i)) + " pts if removed" : "barely matters"}</b></div>
        <div class="bar"><i style="width:${(contribution(i) / max) * 100}%"></i></div>
      </div>
    </li>`).join("");
  $$("#rank li").forEach((li) => li.addEventListener("click", () => selectLeak(+li.dataset.i)));
}

function selectLeak(i) {
  state.leakSel = i;
  $$("#rank li").forEach((li) => li.classList.toggle("sel", +li.dataset.i === i));
  $$("#feed li").forEach((li, j) => li.classList.toggle("current", j === i));
  const leak = state.data.regions[i].leak;
  const links = state.data.links.filter((l) => l[0] === i || l[1] === i).sort((a, b) => b[2] - a[2]).slice(0, 4);
  const partners = links.map((l) => `<b>#${(l[0] === i ? l[1] : l[0]) + 1}</b>`).join(", ");
  $("#leakDetail").innerHTML = `
    <p class="kicker">Which part of photo #${i + 1} leaks</p>
    <div class="leak-photo">
      <img src="${photoSrc(i)}" alt="">
      <div class="leak-grid">${leak.map((v) => `<i style="background:rgba(214,64,43,${(0.75 * v * v).toFixed(3)})"></i>`).join("")}</div>
    </div>
    <p class="links">Red regions are where blurring cuts this photo's support for the AI's guess the most.
      ${partners ? `It points at the same place as photos ${partners}, so they corroborate each other.` : "It doesn't strongly agree with any other single photo."}</p>`;
  showPop(i);
}

/* ------------------------------------------------------------------ fix plan */
function describe(step) {
  if (step.action === "drop") return { t: `Hold back photo #${step.photo + 1}`, img: step.photo };
  return { t: `Blur the leak zone in photo #${step.photo + 1}`, img: step.photo };
}
function renderPlan() {
  const P = state.data.plan;
  $("#plan").innerHTML = P.steps.map((s, n) => {
    const d = describe(s);
    return `<li data-n="${n}"><img src="${photoSrc(d.img)}" alt="">
      <div><div class="pt">${n + 1}. ${d.t}</div>
      <div class="ps">${state.data.home ? `neighbourhood odds → ${pct(s.home_mass)}% · guess ${km(s.home_km)} from home` : `search radius → ${km(s.radius_km)}`}</div></div></li>`;
  }).join("") || `<li class="done"><div></div><div class="pt">Nothing to fix: the AI never settles on your neighbourhood.</div></li>`;
  const before = state.data.replay.at(-1);
  $("#after").className = "after";
  $("#after").innerHTML = state.data.home
    ? `<div class="label">Right now</div><div class="big">${pct(before.home_mass)}%</div>
    chance the AI picks your neighbourhood; best guess ${km(before.home_km)} from home.`
    : `<div class="label">Right now</div><div class="big">${km(before.radius_km)}</div>search radius. Mark your home for a neighbourhood-specific plan.`;
  $("#applyFix").hidden = false;
  $("#undoFix").hidden = true;
}

async function applyFix() {
  const P = state.data.plan;
  $("#applyFix").disabled = true;
  const items = $$("#plan li");
  for (let n = 0; n < P.steps.length; n++) {
    items[n].classList.add("done");
    const s = P.steps[n];
    if (s.action === "drop") $(`#feed li[data-i="${s.photo}"]`).classList.add("held");
    await new Promise((r) => setTimeout(r, 900));
  }
  state.fixed = true;
  renderFeedFixed();
  const a = P.after;
  $("#after").className = "after" + (P.cleared ? " good" : "");
  $("#after").innerHTML = !state.data.home
    ? `<div class="label">After the fix (re-run through the model)</div><div class="big">${km(a.radius_km)}</div>search radius.`
    : `<div class="label">After the fix (re-run through the model)</div><div class="big">${pct(a.home_mass)}%</div>
    chance the AI picks your neighbourhood; its best guess is now <b>${km(a.home_km)}</b> from home.
    ${P.cleared ? "Your neighbourhood is out of the AI's reach." : "Better, but not out of reach: consider holding back more."}`;
  drawBelief(a);
  $("#applyFix").hidden = true;
  $("#applyFix").disabled = false;
  $("#undoFix").hidden = false;
}
function renderFeedFixed() {
  const blurred = state.data.plan.blurred || {};
  Object.keys(blurred).forEach((i) => { $(`#feed li[data-i="${i}"] img`).src = photoSrc(+i, true); });
}
$("#applyFix").addEventListener("click", applyFix);
$("#undoFix").addEventListener("click", () => {
  state.fixed = false;
  $$("#feed li").forEach((li) => li.classList.remove("held"));
  renderFeed(); setStep(state.data.replay.length); renderPlan(); setTab("fix");
});

/* ------------------------------------------------------------------ live mode */
let homeMap, homeMarker;
function initHomeMap() {
  if (homeMap) return;
  homeMap = L.map("homeMap").setView([30, 10], 2);
  L.tileLayer(TILES, { attribution: ATTR, maxZoom: 19, className: "tiles" }).addTo(homeMap);
  homeMap.on("click", (e) => {
    state.home = [e.latlng.lat, e.latlng.lng];
    if (homeMarker) homeMarker.setLatLng(e.latlng);
    else homeMarker = L.marker(e.latlng, { icon: icon("home-marker") }).addTo(homeMap);
  });
}

async function checkServer() {
  try {
    const r = await fetch("/api/health");
    if (!r.ok) throw 0;
    $("#serverNote").textContent = "Local analysis server connected.";
    state.server = true;
  } catch {
    $("#serverNote").innerHTML = "Live analysis needs the local server: <code>uvicorn server.app:app</code>. The demo works without it.";
    state.server = false;
  }
  updateRun();
}

$("#fileInput").addEventListener("change", (e) => {
  state.files = [...e.target.files].slice(0, 24);
  $("#dropSub").textContent = `${state.files.length} photo${state.files.length === 1 ? "" : "s"} selected`;
  $("#thumbs").innerHTML = "";
  state.files.forEach((f) => { const img = new Image(); img.src = URL.createObjectURL(f); $("#thumbs").appendChild(img); });
  updateRun();
});
function updateRun() { $("#runOwn").disabled = !(state.server && state.files.length >= 2); }

$("#runOwn").addEventListener("click", async () => {
  const fd = new FormData();
  state.files.forEach((f) => fd.append("files", f, f.name));
  if (state.home) { fd.append("home_lat", state.home[0]); fd.append("home_lon", state.home[1]); }
  $("#progress").hidden = false;
  $("#runOwn").disabled = true;
  const r = await fetch("/api/analyze", { method: "POST", body: fd });
  if (!r.ok) { $("#progressText").textContent = (await r.json()).detail || "Upload failed"; $("#runOwn").disabled = false; return; }
  state.job = (await r.json()).job;
  const poll = async () => {
    const s = await (await fetch(`/api/jobs/${state.job}`)).json();
    $("#progressBar").style.width = `${Math.round(s.progress * 100)}%`;
    $("#progressText").textContent = s.progress < 0.8 ? "Encoding photos and blurring each region…" : "Fusing evidence and searching for a fix…";
    if (s.status === "done") {
      state.mode = "live";
      const d = s.result;
      d.home = state.home;
      if (!d.home) d.replay.forEach((x) => (x.home_mass = x.confidence));
      load(d);
    } else if (s.status === "error") $("#progressText").textContent = "Analysis failed: " + s.error;
    else setTimeout(poll, 1200);
  };
  poll();
});
