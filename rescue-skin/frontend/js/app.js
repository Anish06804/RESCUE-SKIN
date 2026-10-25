// RESCUE SKIN — frontend application
// Connects to the local backend WebSocket and drives the engineering dashboard.

(function () {
  const BASE = window.location.origin;
  const WS_URL = BASE.replace(/^http/, "ws") + "/ws";

  // DOM
  const mapSvg = document.getElementById("mapSvg");
  const edgesLayer = document.getElementById("edgesLayer");
  const zonesLayer = document.getElementById("zonesLayer");
  const routePath = document.getElementById("routePath");
  const routeHead = document.getElementById("routeHead");
  const mapHint = document.getElementById("mapHint");
  const modeBadge = document.getElementById("modeBadge");
  const modeNote = document.getElementById("modeNote");

  const routeValue = document.getElementById("routeValue");
  const routeExitChip = document.getElementById("routeExitChip");
  const metDist = document.getElementById("metDist");
  const metRisk = document.getElementById("metRisk");
  const metAlgo = document.getElementById("metAlgo");
  const prevRouteEl = document.getElementById("prevRoute");
  const newRouteEl = document.getElementById("newRoute");
  const routeWhyEl = document.getElementById("routeWhy");
  const guidLed = document.getElementById("guidLed");
  const guidAudio = document.getElementById("guidAudio");
  const guidHaptic = document.getElementById("guidHaptic");

  const statMode = document.getElementById("statMode");
  const statProfile = document.getElementById("statProfile");
  const statNodes = document.getElementById("statNodes");
  const statLinks = document.getElementById("statLinks");
  const statRestricted = document.getElementById("statRestricted");
  const statUncertain = document.getElementById("statUncertain");
  const commSvg = document.getElementById("commSvg");

  const perfRouteTarget = document.getElementById("perfRouteTarget");
  const perfRouteMeasured = document.getElementById("perfRouteMeasured");
  const perfDashTarget = document.getElementById("perfDashTarget");
  const perfDashMeasured = document.getElementById("perfDashMeasured");
  const perfHbTarget = document.getElementById("perfHbTarget");
  const perfHbMeasured = document.getElementById("perfHbMeasured");

  const teleTbody = document.getElementById("teleTbody");
  const teleCount = document.getElementById("teleCount");
  const eventList = document.getElementById("eventList");
  const demoProgress = document.getElementById("demoProgress");
  const demoStepText = document.getElementById("demoStepText");

  // State
  let zonesById = {};
  let zoneCoords = {};
  let edges = [];
  let nodeZoneMap = {};
  let commsTopology = null;
  let ws = null;
  let routeAnim = null; // {start, duration, nodes, coords}
  let lastRouteKey = null;

  // ---------- init ----------
  async function init() {
    try {
      const r = await fetch("/api/map");
      const m = await r.json();
      zonesById = {};
      m.zones.forEach((z) => { zonesById[z.id] = z; zoneCoords[z.id] = [z.x, z.y]; });
      edges = m.edges;
      nodeZoneMap = m.node_zone_map;
      commsTopology = m.comms_topology;
    } catch (e) {
      console.error("Failed to load map config", e);
      mapHint.textContent = "Map configuration unavailable.";
    }
    renderEdges();
    renderZones({});
    renderComms();
    connectWs();

    // Manual trigger buttons (wired after DOM ready)
    document.getElementById("btnRecompute").onclick = () => apiPost("/api/route/calculate", { algorithm: "A*", profile: document.getElementById("selProfile").value });
    document.getElementById("btnClearEvents").onclick = () => { eventList.innerHTML = ""; };
    document.getElementById("btnStartDemo").onclick = () => apiPost("/api/demo/start");
    document.getElementById("btnPauseDemo").onclick = () => apiPost("/api/demo/pause");
    document.getElementById("btnResetDemo").onclick = () => apiPost("/api/demo/reset");

    // Profile select
    const selProfile = document.getElementById("selProfile");
    if (selProfile) {
      selProfile.onchange = () => apiPost("/api/profile/accessibility", { profile: selProfile.value });
    }

    // Manual scenario triggers
    wire("btnHazard", "/api/simulation/hazard", { node_id: "NODE_03", delta: 10 });
    wire("btnOccupancy", "/api/simulation/occupancy", { node_id: "NODE_03", amount: 3 });
    wire("btnLinkFail", "/api/simulation/link-failure", { link_id: "NODE_01-NODE_02" });
    document.getElementById("btnLinkRestore").onclick = () => apiPost("/api/simulation/reset");
  }

  function wire(btnId, path, body) {
    const b = document.getElementById(btnId);
    if (!b) return;
    b.onclick = () => apiPost(path, body);
  }

  function apiPost(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then((r) => r.json()).catch((e) => console.error("API error", path, e));
  }

  // ---------- websocket ----------
  function connectWs() {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      modeBadge.textContent = "CONNECTED";
      modeBadge.className = "pill ok";
      modeNote.textContent = "Live WebSocket feed — backend streaming state";
    };
    ws.onclose = () => {
      modeBadge.textContent = "DISCONNECTED";
      modeBadge.className = "pill bad";
      modeNote.textContent = "WebSocket disconnected — retrying…";
      setTimeout(connectWs, 2000);
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state") render(msg.payload);
      } catch (e) {
        console.error("Bad WS message", e);
      }
    };
    ws.onerror = () => { ws.close(); };
  }

  // ---------- render ----------
  function render(snap) {
    if (!snap) return;

    const modeHard = snap.mode === "hardware";
    modeBadge.textContent = modeHard ? "HARDWARE MODE" : "SIMULATION MODE";
    modeBadge.className = modeHard ? "pill bad" : "pill ok";
    modeNote.textContent = modeHard
      ? "Real hardware providers active"
      : "No real hardware connected — software prototype";

    const zones = snap.zones || {};
    const nodes = snap.nodes || {};
    const links = snap.links || {};

    renderZones(zones);
    renderRoute(snap.current_route, snap.previous_route, snap.route_change_reason);
    renderTelemetry(nodes);
    renderEvents(snap.events || []);
    renderStatus(snap, nodes, links);
    renderComms(links);

    // performance
    const pf = snap.performance || {};
    if (pf.route_recalculation) {
      perfRouteTarget.textContent = "target: " + pf.route_recalculation.target;
      perfRouteMeasured.textContent = "measured: " + pf.route_recalculation.measured;
    }
    if (pf.dashboard_updates) {
      perfDashTarget.textContent = "target: " + pf.dashboard_updates.target;
      perfDashMeasured.textContent = "measured: " + pf.dashboard_updates.measured;
    }
    if (pf.communication_heartbeat) {
      perfHbTarget.textContent = "target: " + pf.communication_heartbeat.target;
      perfHbMeasured.textContent = "measured: " + pf.communication_heartbeat.measured;
    }

    // demo progress
    if (snap.demo_active) {
      const total = 10;
      const step = Math.min(snap.demo_step || 0, total);
      demoProgress.style.width = ((step / total) * 100) + "%";
      demoStepText.textContent = "Demo step " + step + " of " + total + (snap.demo_paused ? " — paused" : "");
    } else {
      demoProgress.style.width = "0%";
      demoStepText.textContent = "Idle";
    }
  }

  function zoneClass(state, type, blocked) {
    if (blocked) return "restricted";
    if (state === "RESTRICTED") return "restricted";
    if (state === "HIGH RISK") return "high";
    if (state === "WATCH") return "watch";
    if (state === "UNCERTAIN" || state === "STALE") return "uncertain";
    if (type === "exit") return "exit";
    if (type === "start") return "start";
    return "normal";
  }

  function renderZones(zones) {
    // Rebuild zone elements only when the set changes; otherwise update classes/text.
    const existing = {};
    zonesLayer.querySelectorAll(".zone, .zone-label, .zone-state").forEach((el) => {
      existing[el.dataset.zid + "|" + el.dataset.kind] = el;
    });

    const want = new Set();
    Object.values(zones).forEach((z) => {
      const cls = zoneClass(z.state, z.type, z.blocked);
      const isExit = z.type === "exit";
      const isStart = z.type === "start";

      // zone shape
      let el = existing[z.zone_id + "|shape"];
      if (!el) {
        el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        el.setAttribute("class", "zone");
        el.setAttribute("rx", "7"); el.setAttribute("ry", "7");
        el.setAttribute("width", "100"); el.setAttribute("height", "56");
        el.setAttribute("data-zid", z.zone_id); el.setAttribute("data-kind", "shape");
        zonesLayer.appendChild(el);
        el.addEventListener("click", () => selectZone(z.zone_id));
      }
      el.setAttribute("x", z.x - 50);
      el.setAttribute("y", z.y - 28);
      el.setAttribute("class", "zone " + cls);
      want.add(z.zone_id + "|shape");

      // label
      let lab = existing[z.zone_id + "|label"];
      if (!lab) {
        lab = document.createElementNS("http://www.w3.org/2000/svg", "text");
        lab.setAttribute("class", "zone-label");
        lab.setAttribute("data-zid", z.zone_id); lab.setAttribute("data-kind", "label");
        zonesLayer.appendChild(lab);
      }
      lab.setAttribute("x", z.x); lab.setAttribute("y", z.y - 6);
      lab.textContent = z.label;
      want.add(z.zone_id + "|label");

      // state tag
      let st = existing[z.zone_id + "|state"];
      if (!st) {
        st = document.createElementNS("http://www.w3.org/2000/svg", "text");
        st.setAttribute("class", "zone-state");
        st.setAttribute("data-zid", z.zone_id); st.setAttribute("data-kind", "state");
        zonesLayer.appendChild(st);
      }
      st.setAttribute("x", z.x); st.setAttribute("y", z.y + 20);
      const tag = (z.blocked ? "RESTRICTED" : z.state) + (z.stale ? " (stale)" : "");
      st.textContent = tag + (z.occupancy != null ? "  occ:" + z.occupancy : "");
      want.add(z.zone_id + "|state");
    });

    // remove stale elements
    zonesLayer.querySelectorAll(".zone, .zone-label, .zone-state").forEach((el) => {
      if (!want.has(el.dataset.zid + "|" + el.dataset.kind)) el.remove();
    });
  }

  function selectZone(zoneId) {
    const z = zonesById[zoneId];
    if (!z) return;
    const zs = document.querySelectorAll(".zone-state");
    // find current state text
    mapHint.textContent = zoneId + " — " + z.label + " (" + z.type + ")";
  }

  function renderEdges() {
    edgesLayer.innerHTML = "";
    edges.forEach((e) => {
      const a = zoneCoords[e.from] || [0, 0];
      const b = zoneCoords[e.to] || [0, 0];
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("class", "edge" + (e.accessible ? "" : " inaccessible"));
      line.setAttribute("x1", a[0]); line.setAttribute("y1", a[1]);
      line.setAttribute("x2", b[0]); line.setAttribute("y2", b[1]);
      line.dataset.edge = e.from + "-" + e.to;
      edgesLayer.appendChild(line);
    });
  }

  function updateEdgeStates(zones) {
    edges.forEach((e) => {
      const line = edgesLayer.querySelector(`[data-edge="${e.from}-${e.to}"]`);
      if (!line) return;
      const fa = zones[e.from] || {};
      const fb = zones[e.to] || {};
      const blocked = fa.blocked || fb.blocked;
      const cls = "edge" +
        (blocked ? " blocked" : "") +
        (e.accessible ? "" : " inaccessible");
      line.setAttribute("class", cls);
    });
  }

  // ---------- route ----------
  function renderRoute(current, previous, reason) {
    // metrics
    if (current) {
      routeValue.textContent = current.nodes.join(" → ");
      routeExitChip.textContent = current.exit_id + " (" + current.profile + ")";
      routeExitChip.className = "route-chip" + (current.exit_id === "ExitB" ? " ok" : "");
      metDist.textContent = (current.total_distance != null ? current.total_distance + " m" : "—");
      metRisk.textContent = (current.total_risk != null ? current.total_risk.toFixed(1) : "—");
      metAlgo.textContent = current.algorithm || "A*";
    } else {
      routeValue.textContent = "No feasible route";
      routeExitChip.textContent = "—";
      metDist.textContent = "—";
      metRisk.textContent = "—";
      metAlgo.textContent = "—";
    }

    // previous / new / why
    if (previous) {
      prevRouteEl.innerHTML = previous.nodes.join(" → ") + " → " + previous.exit_id;
      newRouteEl.innerHTML = current ? current.nodes.join(" → ") + " → " + current.exit_id : "recalculating…";
    } else {
      prevRouteEl.innerHTML = "<em>—</em>";
      newRouteEl.innerHTML = current ? current.nodes.join(" → ") + " → " + current.exit_id : "<em>—</em>";
    }
    routeWhyEl.textContent = reason || "No recalculation yet.";

    // guidance
    if (current) {
      guidLed.textContent = "ACTIVE — path lit to " + current.exit_id;
      guidAudio.textContent = "Proceed to " + current.exit_id;
      guidHaptic.textContent = current.profile === "ACCESSIBLE" ? "PATTERN 1" : "PATTERN 2";
    } else {
      guidLed.textContent = "STANDBY";
      guidAudio.textContent = "—";
      guidHaptic.textContent = "—";
    }

    // draw + animate path
    const key = current ? current.nodes.join(",") + "|" + current.exit_id : "none";
    if (key !== lastRouteKey && current && current.nodes.length > 1) {
      lastRouteKey = key;
      const points = current.nodes.map((n) => zoneCoords[n]).filter(Boolean);
      routePath.setAttribute("points", points.map((p) => p.join(",")).join(" "));
      // reset dasharray animation
      routePath.classList.remove("animate");
      void routePath.offsetWidth; // reflow
      routePath.classList.add("animate");
      startHeadAnimation(points);
    } else if (!current) {
      routePath.setAttribute("points", "");
      routeHead.setAttribute("cx", "0"); routeHead.setAttribute("cy", "0");
      lastRouteKey = null;
      cancelHeadAnimation();
    }
    // update edge route highlighting
    updateRouteEdges(current ? current.nodes : []);
  }

  function updateRouteEdges(routeNodes) {
    const routeSet = new Set();
    for (let i = 0; i < routeNodes.length - 1; i++) {
      routeSet.add(routeNodes[i] + "-" + routeNodes[i + 1]);
      routeSet.add(routeNodes[i + 1] + "-" + routeNodes[i]);
    }
    edges.forEach((e) => {
      const id1 = e.from + "-" + e.to;
      const id2 = e.to + "-" + e.from;
      const line = edgesLayer.querySelector(`[data-edge="${e.from}-${e.to}"]`);
      if (!line) return;
      if (routeSet.has(id1) || routeSet.has(id2)) {
        line.setAttribute("class", "edge route");
      } else {
        line.setAttribute("class", "edge" + (e.accessible ? "" : " inaccessible"));
      }
    });
  }

  function startHeadAnimation(points) {
    cancelHeadAnimation();
    // build segment table with lengths
    const segs = [];
    let total = 0;
    for (let i = 0; i < points.length - 1; i++) {
      const dx = points[i + 1][0] - points[i][0];
      const dy = points[i + 1][1] - points[i][1];
      const len = Math.hypot(dx, dy);
      segs.push({ from: points[i], to: points[i + 1], len, dx, dy });
      total += len;
    }
    const duration = 1500;
    const start = performance.now();
    routeAnim = { segs, total, start, duration };
    tickHead();
  }

  function cancelHeadAnimation() {
    if (routeAnim) cancelAnimationFrame(routeAnim.raf);
    routeAnim = null;
    routeHead.setAttribute("cx", "0"); routeHead.setAttribute("cy", "0");
  }

  function tickHead() {
    if (!routeAnim) return;
    const now = performance.now();
    const t = Math.min(1, (now - routeAnim.start) / routeAnim.duration);
    let d = t * routeAnim.total;
    let pos = { x: 0, y: 0 };
    for (const s of routeAnim.segs) {
      if (d <= s.len) {
        const r = d / s.len;
        pos.x = s.from[0] + s.dx * r;
        pos.y = s.from[1] + s.dy * r;
        break;
      }
      d -= s.len;
    }
    routeHead.setAttribute("cx", pos.x); routeHead.setAttribute("cy", pos.y);
    if (t < 1) {
      routeAnim.raf = requestAnimationFrame(tickHead);
    }
  }

  // ---------- telemetry ----------
  function renderTelemetry(nodes) {
    teleCount.textContent = Object.keys(nodes).length + " nodes";
    teleTbody.innerHTML = "";
    let online = 0, upLinks = 0;
    Object.values(nodes).forEach((n) => {
      if (n.online) online++;
      const tr = document.createElement("tr");
      tr.className = n.online ? "online" : "offline";
      const ts = n.last_reading ? new Date(n.last_reading * 1000).toLocaleTimeString([], { hour12: false }) : "—";
      tr.innerHTML = `
        <td>${n.node_id}</td>
        <td>${n.zone_id}</td>
        <td class="${n.online ? 'online-y' : 'online-n'}">${n.online ? "YES" : "NO"}</td>
        <td>${n.communication}</td>
        <td>${n.health != null ? n.health.toFixed(2) : "—"}</td>
        <td>${n.temperature != null ? n.temperature.toFixed(1) : "—"}</td>
        <td>${n.occupancy != null ? n.occupancy : "—"}</td>
        <td>${n.presence ? "YES" : "no"}</td>
        <td>${n.pressure != null ? n.pressure.toFixed(2) : "—"}</td>
        <td>${n.proximity != null ? n.proximity.toFixed(1) : "—"}</td>
        <td>${ts}</td>
      `;
      teleTbody.appendChild(tr);
    });
    statNodes.textContent = online + " / " + Object.keys(nodes).length;
  }

  // ---------- status ----------
  function renderStatus(snap, nodes, links) {
    statMode.textContent = snap.mode === "hardware" ? "Hardware" : "Simulation";
    statProfile.textContent = snap.profile || "STANDARD";
    const up = Object.values(links).filter((l) => l.online).length;
    statLinks.textContent = up + " / " + Object.values(links).length;
    const zones = snap.zones || {};
    let restricted = 0, uncertain = 0;
    Object.values(zones).forEach((z) => {
      if (z.blocked || z.state === "RESTRICTED") restricted++;
      if (z.stale || z.state === "UNCERTAIN") uncertain++;
    });
    statRestricted.textContent = restricted;
    statUncertain.textContent = uncertain;
    statRestricted.className = restricted ? "risk-restricted" : "risk-normal";
    statUncertain.className = uncertain ? "risk-watch" : "risk-normal";
  }

  // ---------- comms topology ----------
  function renderComms(links) {
    if (!commsTopology) return;
    commSvg.innerHTML = "";
    const gw = commsTopology.gateway;
    // fixed layout for the 6-node tree topology
    const layout = {
      NODE_01: [130, 50],
      NODE_02: [55, 115],
      NODE_03: [205, 115],
      NODE_04: [20, 180],
      NODE_05: [90, 180],
      NODE_06: [240, 180],
    };
    const linkById = {};
    (links || []).forEach((l) => { linkById[l.link_id] = l; });

    // draw links
    commsTopology.links.forEach((pair) => {
      const a = layout[pair[0]], b = layout[pair[1]];
      if (!a || !b) return;
      const lid = pair[0] + "-" + pair[1];
      const l = linkById[lid];
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("class", "comm-link " + (l && l.online ? "up" : "down"));
      line.setAttribute("x1", a[0]); line.setAttribute("y1", a[1]);
      line.setAttribute("x2", b[0]); line.setAttribute("y2", b[1]);
      commSvg.appendChild(line);
    });
    // nodes
    Object.entries(layout).forEach(([nid, p]) => {
      const nodeState = (nodes && nodes[nid]) || {};
      const online = nodeState.online !== false;
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("class", "comm-node " + (online ? "online" : "offline"));
      circle.setAttribute("cx", p[0]); circle.setAttribute("cy", p[1]); circle.setAttribute("r", 11);
      commSvg.appendChild(circle);
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("class", "comm-label");
      label.setAttribute("x", p[0]); label.setAttribute("y", p[1] + 17);
      label.textContent = nid;
      commSvg.appendChild(label);
    });
  }

  // ---------- events ----------
  function renderEvents(events) {
    eventList.innerHTML = "";
    (events || []).slice().reverse().forEach((e) => {
      const div = document.createElement("div");
      div.className = "ev " + (e.type || "").toLowerCase().replace(/ /g, "-");
      div.innerHTML = `<div class="time">${e.timestamp}</div>
        <span class="type">${e.type}</span> <b>${e.zone}</b>: ${e.message}`;
      eventList.appendChild(div);
    });
    eventList.scrollTop = eventList.scrollHeight;
  }

  // ---------- manual trigger wiring ----------
  function apiPostJson(path, body) { return apiPost(path, body); }
  document.getElementById("btnLinkRestore").onclick = () => apiPost("/api/simulation/reset");

  // profile select element may not exist in HTML yet — add a select to status panel? 
  // We reference selProfile; ensure it exists. It is not in index.html, so guard.
  // (kept defensive above)

  init();
})();
