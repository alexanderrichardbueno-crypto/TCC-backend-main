document.addEventListener("DOMContentLoaded", () => {
  const $ = (selector) => document.querySelector(selector);
  const form = $("#map-search");
  const status = $("#map-status");
  const locationButton = $("#map-location");
  const refreshButton = $("#map-refresh");
  // Cores que o INMET envia para cada severidade, iguais às da central.
  const inmetColors = { LOW: "#FFFE00", MODERATE: "#FFFE00", HIGH: "#F96602", CRITICAL: "#e3001b" };
  const teamAlerts = { TORNADO: { fill: "#d21428", fillOpacity: .72, line: "#ff4257" }, SEVERE_STORM: { fill: "#f0c800", fillOpacity: .7, line: "#ffe100" } };
  const warningColor = (alert) => alert.origin === "MANUAL" ? (teamAlerts[alert.event_type] || teamAlerts.SEVERE_STORM).line : inmetColors[alert.severity] || inmetColors.MODERATE;
  function warningStyle(alert) {
    if (alert.origin !== "MANUAL") { const color = warningColor(alert); return { color, fillColor: color, fillOpacity: .32, weight: 1.6 }; }
    const team = teamAlerts[alert.event_type] || teamAlerts.SEVERE_STORM;
    return { color: team.line, fillColor: team.fill, fillOpacity: team.fillOpacity, weight: 2.2 };
  }
  // Mesmas cores e nomes da legenda do painel dos meteorologistas.
  const forecastLevels = {
    T: { name: "Tempestades não severas", color: "#39ff14", line: "#39ff14", opacity: .30 },
    1: { name: "Nível 1", color: "#ffe100", line: "#ffe100", opacity: .33 },
    2: { name: "Nível 2", color: "#ff7a00", line: "#ff7a00", opacity: .38 },
    3: { name: "Nível 3", color: "#ff1a1a", line: "#ff2a2a", opacity: .42 },
    4: { name: "Nível 4", color: "#9d1cff", line: "#a63bff", opacity: .45 },
  };
  const levelRank = (area) => (area.properties?.nivel === "T" ? 0 : Number(area.properties?.nivel) || 0);
  let map, forecastLayer, alertLayer, inmetTodayLayer, inmetFutureLayer, pointLayer;
  const layerVisible = { prev: true, alerta: true, inmHoje: true, inmFut: true };
  const layerGroup = (key) => ({ prev: forecastLayer, alerta: alertLayer, inmHoje: inmetTodayLayer, inmFut: inmetFutureLayer })[key];
  function setLayer(key, visible) {
    layerVisible[key] = visible;
    if (visible) layerGroup(key).addTo(map); else layerGroup(key).removeFrom(map);
  }
  let requestId = 0;
  let currentParams = new URLSearchParams();
  let lastData = null;
  let tileError = false;
  const shapes = new Map();
  const states = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");
  $("#map-state").replaceChildren(...states.map((state) => new Option(state, state, state === "SP", state === "SP")));

  // Mesmo mapa-base e mesmo modo escuro da central meteorológica.
  const MAP_KEY = (document.querySelector('meta[name="maptiler-key"]')?.content || "").replace(/^__.*__$/, "");
  const MT_STYLE = "https://api.maptiler.com/maps/openstreetmap/style.json";
  const FREE_STYLE = "https://tiles.openfreemap.org/styles/liberty";
  let baseStyle = null, baseLayer = null;
  function rgbToHsl(r, g, b) { const mx = Math.max(r, g, b), mn = Math.min(r, g, b); let h = 0, s = 0; const l = (mx + mn) / 2; if (mx !== mn) { const d = mx - mn; s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn); h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h /= 6; } return [h, s, l]; }
  function hslToRgb(h, s, l) { if (!s) return [l * 255, l * 255, l * 255]; const f = (p, q, t) => { if (t < 0) t += 1; if (t > 1) t -= 1; return t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; }; const q = l < .5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q; return [f(p, q, h + 1 / 3) * 255, f(p, q, h) * 255, f(p, q, h - 1 / 3) * 255]; }
  function parseColor(value) {
    const s = String(value).trim().toLowerCase(); let m;
    if ((m = s.match(/^#([0-9a-f]{3,8})$/))) { let h = m[1]; if (h.length <= 4) h = h.split("").map((c) => c + c).join(""); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1]; }
    if ((m = s.match(/^rgba?\(([^)]+)\)$/))) { const p = m[1].split(/[\s,/]+/).filter(Boolean).map(parseFloat); return p.length >= 3 ? [p[0], p[1], p[2], p[3] == null ? 1 : p[3]] : null; }
    if ((m = s.match(/^hsla?\(([^)]+)\)$/))) { const p = m[1].replace(/%|deg/g, "").split(/[\s,/]+/).filter(Boolean).map(parseFloat); if (p.length < 3) return null; const c = hslToRgb(p[0] / 360, p[1] / 100, p[2] / 100); return [c[0], c[1], c[2], p[3] == null ? 1 : p[3]]; }
    return s === "white" ? [255, 255, 255, 1] : s === "black" ? [0, 0, 0, 1] : null;
  }
  function darkColor(value) {
    const c = parseColor(value); if (!c) return value;
    let [h, s, l] = rgbToHsl(c[0] / 255, c[1] / 255, c[2] / 255); l = .07 + (1 - l) * .8; s *= .72;
    const r = hslToRgb(h, s, l), n = [10, 23, 52];
    return `rgba(${Math.round(r[0] * .82 + n[0] * .18)},${Math.round(r[1] * .82 + n[1] * .18)},${Math.round(r[2] * .82 + n[2] * .18)},${+c[3].toFixed(3)})`;
  }
  const mapColors = (v) => typeof v === "string" ? darkColor(v) : Array.isArray(v) ? v.map(mapColors) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, mapColors(x)])) : v;
  function themedStyle() {
    const style = JSON.parse(JSON.stringify(baseStyle));
    if (document.documentElement.getAttribute("data-theme") === "dark") {
      (style.layers || []).forEach((layer) => { if (layer.paint) Object.keys(layer.paint).forEach((key) => { if (/color/.test(key)) layer.paint[key] = mapColors(layer.paint[key]); }); });
    }
    return style;
  }
  function addRasterBase() {
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' })
      .on("tileerror", () => { tileError = true; visualNotice("Mapa-base indisponível. Consulte as previsões e os avisos na lista."); }).addTo(map);
  }
  async function addBase() {
    if (!L.maplibreGL || !window.maplibregl) { addRasterBase(); return; }
    const urls = MAP_KEY ? [`${MT_STYLE}?key=${encodeURIComponent(MAP_KEY)}`, FREE_STYLE] : [FREE_STYLE];
    for (const url of urls) {
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        baseStyle = await response.json();
        baseLayer = L.maplibreGL({ style: themedStyle(), attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map);
        document.addEventListener("prevclima:theme", () => baseLayer.getMaplibreMap().setStyle(themedStyle(), { diff: false }));
        return;
      } catch (_error) { /* Tenta a próxima fonte do mapa-base. */ }
    }
    addRasterBase();
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function sourceLink(url) {
    try {
      const parsed = new URL(url);
      const trusted = ["inmet.gov.br", "open-meteo.com"].some((host) => parsed.hostname === host || parsed.hostname.endsWith(`.${host}`));
      if (!trusted || parsed.protocol !== "https:" || parsed.username || parsed.password) return null;
      const link = element("a", "Consultar fonte ↗");
      link.href = parsed.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return link;
    } catch (_error) { return null; }
  }
  function visualNotice(message) {
    $("#map-visual-status").textContent = message;
    $("#map-visual-status").hidden = !message;
  }
  const ALERT_PANE = "severeAlerts";
  function popup(title, detail, source, url, date, description) {
    const node = element("div", "");
    node.append(element("strong", title));
    if (description) node.append(element("p", description));
    node.append(element("p", detail), element("p", `Fonte: ${source}`));
    if (date) node.append(element("p", `Válido até ${new Date(date).toLocaleString("pt-BR")}`));
    const link = sourceLink(url);
    if (link) node.append(link);
    return node;
  }
  function fitAll() {
    if (!map) return;
    const layers = [...pointLayer.getLayers(), ...Object.keys(layerVisible).filter((key) => layerVisible[key]).flatMap((key) => layerGroup(key).getLayers())];
    if (layers.length) {
      const bounds = L.featureGroup(layers).getBounds();
      if (bounds.isValid()) map.fitBounds(bounds.pad(.15), { maxZoom: 10 });
    }
  }
  function renderForecast(data) {
    const host = $("#map-forecast");
    const point = data.forecast_points?.[0];
    host.replaceChildren();
    if (!point) {
      host.append(element("span", "SEM PREVISÃO DISPONÍVEL", "data-tag"), element("h2", "Não foi possível obter a previsão"), element("p", "Confira a cidade e a UF ou tente atualizar em instantes. Nenhum valor estimado foi inserido."));
      return;
    }
    host.append(element("span", point.is_stale ? "Último dado salvo" : `Previsão · ${point.source_name}`, "data-tag"), element("h2", `${point.city}, ${point.state}`), element("div", `${Math.round(Number(point.temperature_c))}°`, "point-temperature"), element("p", `${point.condition} · Chuva: ${point.rain_probability}%`), element("p", `Atualizado ${PrevClima.relativeTime(point.issued_at)}`));
    const link = sourceLink(point.source_url);
    if (link) host.append(link);
    if (states.includes(point.state)) {
      form.elements.city.value = point.city;
      form.elements.state.value = point.state;
    }
  }
  function renderWarnings(data) {
    const list = $("#map-warning-list");
    list.replaceChildren();
    const alerts = [...(data.alerts || [])].sort((a, b) => ["CRITICAL", "HIGH", "MODERATE", "LOW"].indexOf(a.severity) - ["CRITICAL", "HIGH", "MODERATE", "LOW"].indexOf(b.severity));
    $("#map-warning-count").textContent = alerts.length;
    if (!alerts.length) {
      const item = element("li", "");
      item.append(element("strong", "Nenhum aviso disponível"), element("p", "Confira o estado da sincronização acima e consulte a fonte oficial."));
      list.append(item);
    }
    for (const alert of alerts) {
      const item = element("li", "");
      item.style.setProperty("--warning-color", warningColor(alert));
      const shape = shapes.get(alert.id);
      const title = element(shape ? "button" : "strong", alert.title);
      if (shape) {
        title.type = "button";
        title.addEventListener("click", () => {
          const key = alert.origin === "MANUAL" ? "alerta" : "inmHoje";
          $(`#layer-${key}`).checked = true;
          setLayer(key, true);
          map.fitBounds(shape.getBounds().pad(.2), { maxZoom: 10 });
          shape.openPopup();
          $("#weather-map").scrollIntoView({ block: "center" });
        });
      }
      item.append(element("span", PrevClima.severityName(alert.severity), "warning-level"), title, element("p", alert.area_name), element("p", `Fonte: ${alert.source_name}`), element("p", `Até ${new Date(alert.valid_until).toLocaleString("pt-BR")}`));
      if (!alert.polygon && !(alert.latitude != null && alert.longitude != null && Number(alert.radius_km) > 0)) item.append(element("p", "Área descrita em texto pela fonte, sem delimitação no mapa."));
      const link = sourceLink(alert.source_url);
      if (link) item.append(link);
      list.append(item);
    }
  }
  function draw(data, recenter) {
    if (!map) return;
    forecastLayer.clearLayers();
    alertLayer.clearLayers();
    inmetTodayLayer.clearLayers();
    inmetFutureLayer.clearLayers();
    pointLayer.clearLayers();
    shapes.clear();
    for (const point of data.forecast_points || []) {
      L.circleMarker([Number(point.latitude), Number(point.longitude)], { pane: "markerPane", radius: 10, color: "#fff", fillColor: "#258cce", fillOpacity: 1, weight: 3 })
        .bindPopup(popup(`${point.city}, ${point.state}`, `${point.condition} · ${Math.round(Number(point.temperature_c))} °C${point.is_stale ? " · Último dado salvo" : ""}`, point.source_name, point.source_url, point.valid_until)).addTo(pointLayer);
    }
    for (const area of data.forecast_areas || []) {
      L.geoJSON(area.polygon, { style: { color: "#258cce", fillOpacity: .1, dashArray: "5 6" } })
        .bindPopup(popup(`${area.city}, ${area.state}`, "Área de previsão cadastrada", area.source_name, null, area.valid_until)).addTo(forecastLayer);
    }
    let invalidGeometry = false;
    // Previsões de tempo severo emitidas pelos meteorologistas na central (/painel.html).
    const published = data.published_areas_at ? ` · publicado ${PrevClima.relativeTime(data.published_areas_at)}` : "";
    const panelAreas = [...(data.published_areas || [])].sort((a, b) => (a.properties?.tipo === "alerta") - (b.properties?.tipo === "alerta") || levelRank(a) - levelRank(b));
    for (const area of panelAreas) {
      try {
        const info = area.properties || {};
        if (info.tipo === "previsao") {
          const level = forecastLevels[info.nivel] || forecastLevels[1];
          L.geoJSON(area.geometry, { style: { color: level.line, fillColor: level.color, fillOpacity: level.opacity, weight: 2.2 } })
            .bindPopup(popup(info.nome || "Previsão de tempo severo", `${info.descricao ? `${info.descricao} · ` : ""}${forecastLevels[info.nivel]?.name || "nível não informado"}${published}`, "Meteorologistas PrevClima", null, info.validade || null)).addTo(forecastLayer);
        } else if (info.tipo === "alerta") {
          const tornado = info.alerta === "tornado";
          const color = tornado ? "#d2142a" : "#e0b800";
          L.geoJSON(area.geometry, { pane: ALERT_PANE, style: { color, fillColor: color, fillOpacity: .35, weight: 2.5 } })
            .bindPopup(popup(info.nome || "Alerta", `${tornado ? "Alerta de tornado" : "Alerta de tempestade severa"}${published}`, "Meteorologistas PrevClima", null, null)).addTo(alertLayer);
        }
      } catch (_error) { invalidGeometry = true; }
    }
    for (const alert of data.alerts || []) {
      try {
        const style = warningStyle(alert);
        const pane = alert.origin === "MANUAL" ? ALERT_PANE : "overlayPane";
        const shape = alert.polygon ? L.geoJSON(alert.polygon, { pane, style }) :
          alert.latitude != null && alert.longitude != null && Number(alert.radius_km) > 0 ?
            L.circle([Number(alert.latitude), Number(alert.longitude)], { ...style, pane, radius: Number(alert.radius_km) * 1000 }) : null;
        if (shape) {
          shape.bindPopup(popup(alert.title, alert.area_name, alert.source_name, alert.source_url, alert.valid_until, alert.message), { maxHeight: 280 }).addTo(alert.origin === "MANUAL" ? alertLayer : inmetTodayLayer);
          shapes.set(alert.id, shape);
        }
      } catch (_error) { invalidGeometry = true; }
    }
    for (const alert of data.upcoming_alerts || []) {
      try {
        const color = warningColor(alert);
        const style = { color, fillColor: color, fillOpacity: .13, weight: 1.6, dashArray: "6 4" };
        const shape = alert.polygon ? L.geoJSON(alert.polygon, { style }) : null;
        if (shape) shape.bindPopup(popup(alert.title, alert.area_name, alert.source_name, alert.source_url, alert.valid_until, alert.message), { maxHeight: 280 }).addTo(inmetFutureLayer);
      } catch (_error) { invalidGeometry = true; }
    }
    if (invalidGeometry) visualNotice("Algumas áreas não puderam ser desenhadas. Todos os avisos continuam na lista.");
    if (recenter) {
      const point = data.forecast_points?.[0];
      if (point) map.setView([Number(point.latitude), Number(point.longitude)], 9);
      else fitAll();
    }
    map.invalidateSize();
  }
  function expireDisplayedData() {
    // Never keep an expired warning on screen just because a refresh failed.
    if (!lastData) return;
    lastData.alerts = (lastData.alerts || []).filter((a) => Date.parse(a.valid_until) > Date.now());
    lastData.upcoming_alerts = (lastData.upcoming_alerts || []).filter((a) => Date.parse(a.valid_until) > Date.now());
    lastData.forecast_areas = (lastData.forecast_areas || []).filter((f) => Date.parse(f.valid_until) > Date.now());
    lastData.forecast_points = (lastData.forecast_points || []).filter((p) => Date.now() - Date.parse(p.issued_at) <= 86400000).map((p) => ({ ...p, is_stale: true }));
    draw(lastData, false);
    renderForecast(lastData);
    renderWarnings(lastData);
  }
  async function load(params = currentParams, { recenter = true } = {}) {
    const id = ++requestId;
    currentParams = new URLSearchParams(params);
    status.textContent = "Consultando fontes meteorológicas…";
    refreshButton.disabled = true;
    form.querySelector("button").disabled = true;
    try {
      const data = await PrevClima.request(`/map-data${params.size ? `?${params}` : ""}`);
      if (id !== requestId) return;
      lastData = data;
      if (map && !tileError) visualNotice("");
      draw(data, recenter);
      renderForecast(data);
      renderWarnings(data);
      $("#feed-status").textContent = PrevClima.feedStatus(data.warning_feed);
      status.textContent = `Consulta ${new Date(data.generated_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })} · Atualização automática a cada 5 min`;
    } catch (error) {
      if (id !== requestId) return;
      // A failed city search must not relabel the previous city's data.
      expireDisplayedData();
      status.textContent = `${error.message}${lastData ? " Exibindo a última consulta, sem atualização confirmada." : " Tente atualizar."}`;
      $("#feed-status").textContent = "Não foi possível verificar o estado da sincronização.";
      if (!lastData) {
        $("#map-forecast").replaceChildren(element("h2", "Dados indisponíveis"), element("p", "Confira a conexão e tente novamente."));
        $("#map-warning-list").replaceChildren(element("li", "Os avisos não puderam ser consultados."));
      }
    } finally {
      if (id === requestId) {
        refreshButton.disabled = false;
        form.querySelector("button").disabled = false;
      }
    }
  }
  if (window.L) {
    map = L.map("weather-map", { zoomControl: false }).setView([-15.7, -51.5], 4);
    // Plano próprio: os alertas ficam acima de previsões e INMET mesmo ao alternar as camadas.
    map.createPane(ALERT_PANE).style.zIndex = 450;
    L.control.zoom({ position: "bottomright" }).addTo(map);
    addBase();
    forecastLayer = L.layerGroup().addTo(map);
    alertLayer = L.layerGroup().addTo(map);
    inmetTodayLayer = L.layerGroup().addTo(map);
    inmetFutureLayer = L.layerGroup().addTo(map);
    pointLayer = L.layerGroup().addTo(map);
  } else {
    visualNotice("O mapa visual não carregou. A busca, as previsões e a lista de avisos continuam disponíveis abaixo ou ao lado.");
    $("#map-fit").disabled = true;
  }
  for (const key of Object.keys(layerVisible)) {
    $(`#layer-${key}`).disabled = !map;
    $(`#layer-${key}`).addEventListener("change", (event) => { if (map) setLayer(key, event.target.checked); });
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    load(new URLSearchParams({ city: form.elements.city.value.trim(), state: form.elements.state.value }));
  });
  refreshButton.addEventListener("click", () => load(currentParams, { recenter: false }));
  $("#map-fit").addEventListener("click", fitAll);
  locationButton.disabled = !navigator.geolocation;
  locationButton.addEventListener("click", async () => {
    locationButton.disabled = true;
    try {
      await PrevClima.request("/users/me");
      status.textContent = "Obtendo sua localização…";
      const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: false, timeout: 10000, maximumAge: 900000 }));
      await load(new URLSearchParams({ latitude: position.coords.latitude.toFixed(2), longitude: position.coords.longitude.toFixed(2) }));
    } catch (error) {
      status.textContent = error.status === 401 ? "Entre na sua conta para usar o GPS. A busca por cidade é pública. " : "Não foi possível obter sua localização. Use a busca por cidade.";
      if (error.status === 401) {
        const link = element("a", "Entrar");
        link.href = "/index.html?next=/mapa.html";
        status.append(link);
      }
    } finally { locationButton.disabled = false; }
  });
  setInterval(() => { if (!document.hidden) load(currentParams, { recenter: false }); }, 300000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(currentParams, { recenter: false }); });
  const initial = new URLSearchParams(window.location.search);
  if (initial.has("city") && initial.has("state")) currentParams = new URLSearchParams({ city: initial.get("city"), state: initial.get("state") });
  load();
});
