// Dependency-free behavioral tests for the map's no-Leaflet fallback and request races.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

class Element {
  constructor() { this.children = []; this.events = {}; this.textContent = ''; this.style = { setProperty() {} }; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(name, action) { this.events[name] = action; }
  querySelector() { return this.button ||= new Element(); }
  get text() { return this.textContent + this.children.map((c) => c.text ?? c).join(' '); }
}
const flush = () => new Promise(setImmediate);
// Leaflet mínimo: registra o que foi desenhado em cada camada.
function fakeLeaflet() {
  const chain = () => ({ addTo() { return this; }, on() { return this; } });
  const group = () => ({ items: [], addTo() { return this; }, removeFrom() { return this; },
    clearLayers() { this.items = []; }, getLayers() { return this.items; } });
  const groups = [];
  const shape = (kind, geometry, options) => ({ kind, geometry, options,
    bindPopup(content) { this.popup = content; return this; },
    addTo(layer) { layer.items.push(this); return this; } });
  return {
    groups,
    L: {
      map: () => ({ setView() { return this; }, fitBounds() {}, invalidateSize() {}, createPane: () => ({ style: {} }) }),
      control: { zoom: chain }, tileLayer: chain,
      layerGroup: () => { const g = group(); groups.push(g); return g; },
      geoJSON: (geometry, options) => shape('geojson', geometry, options),
      circle: (center, options) => shape('circle', center, options),
      circleMarker: (center, options) => shape('marker', center, options),
      featureGroup: () => ({ getBounds: () => ({ isValid: () => false }) }),
    },
  };
}
async function setup(leaflet) {
  const nodes = new Map();
  const node = (id) => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
  const form = node('#map-search');
  form.elements = { city: { value: '' }, state: { value: 'SP' } };
  const requests = [];
  let ready;
  const context = {
    document: { querySelector: node, createElement: () => new Element(), hidden: false,
      addEventListener: (name, fn) => { if (name === 'DOMContentLoaded') ready = fn; } },
    window: { location: { search: '' }, L: leaflet }, L: leaflet, navigator: { geolocation: {} },
    URL, URLSearchParams, Date, Map, Option: class extends Element {}, setInterval() {},
    PrevClima: {
      request: (url) => new Promise((resolve, reject) => requests.push({ url, resolve, reject })),
      relativeTime: () => 'agora', severityName: (x) => x, feedStatus: (x) => x.status,
    },
  };
  vm.runInNewContext(fs.readFileSync('public/assets/js/map.js', 'utf8'), context);
  ready();
  return { node, requests, form };
}
const data = (city = 'Mongaguá') => ({
  generated_at: new Date().toISOString(), warning_feed: { status: 'current' }, alerts: [],
  forecast_points: [{ city, state: 'SP', temperature_c: 23, rain_probability: 25,
    condition: 'Nublado', source_name: 'Open-Meteo', source_url: 'https://open-meteo.com/',
    issued_at: new Date().toISOString(), valid_until: new Date(Date.now() + 60000).toISOString() }],
});

test('missing Leaflet keeps city search, forecast and text-only warning usable', async () => {
  const { node, requests, form } = await setup();
  const payload = data();
  payload.alerts = [{ id: 1, title: '<script>untrusted</script>', area_name: 'Litoral',
    source_name: 'INMET', severity: 'HIGH', source_url: 'https://evil.example/',
    valid_until: payload.forecast_points[0].valid_until }];
  requests[0].resolve(payload);
  await flush();
  assert.match(node('#map-forecast').text, /Mongaguá/);
  assert.match(node('#map-warning-list').text, /sem delimitação/);
  assert.equal(node('#map-fit').disabled, true);
  assert.equal(node('#layer-prev').disabled, true);
  // The external title remains text; untrusted source links are never emitted.
  assert.match(node('#map-warning-list').text, /<script>untrusted<\/script>/);
  assert.equal(node('#map-warning-list').children[0].children.some((x) => x.href), false);
  form.elements.city.value = 'Santos';
  form.events.submit({ preventDefault() {} });
  assert.equal(requests[1].url, '/map-data?city=Santos&state=SP');
  requests[1].resolve(data('Santos'));
  await flush();
  assert.match(node('#map-forecast').text, /Santos/);
});

test('late request cannot overwrite a more recent city selection', async () => {
  const { node, requests, form } = await setup();
  form.elements.city.value = 'Santos';
  form.events.submit({ preventDefault() {} });
  requests[1].resolve(data('Santos'));
  await flush();
  requests[0].resolve(data('Mongaguá'));
  await flush();
  assert.match(node('#map-forecast').text, /Santos/);
  assert.doesNotMatch(node('#map-forecast').text, /Mongaguá/);
});

test('failed refresh labels saved forecast and removes expired warnings', async () => {
  const { node, requests } = await setup();
  const payload = data();
  payload.alerts = [{ id: 3, title: 'Aviso vencido', area_name: 'Litoral', severity: 'HIGH',
    source_name: 'INMET', valid_until: new Date(Date.now() - 1000).toISOString() }];
  requests[0].resolve(payload);
  await flush();
  node('#map-refresh').events.click();
  requests[1].reject(new Error('Sem conexão'));
  await flush();
  assert.match(node('#map-forecast').text, /Último dado salvo/);
  assert.doesNotMatch(node('#map-warning-list').text, /Aviso vencido/);
  assert.match(node('#map-status').text, /sem atualização confirmada/);
  assert.equal(node('#map-refresh').disabled, false);
});

test('areas published in the panel are drawn in the forecast and alert layers', async () => {
  const fake = fakeLeaflet();
  const { requests } = await setup(fake.L);
  const square = { type: 'Polygon', coordinates: [[[-47, -24], [-46, -24], [-46, -23], [-47, -24]]] };
  const payload = data();
  payload.published_areas_at = new Date().toISOString();
  payload.published_areas = [
    { type: 'Feature', properties: { id: 2, nome: 'Alerta de tornado – Santos', tipo: 'alerta', alerta: 'tornado' }, geometry: square },
    { type: 'Feature', properties: { id: 1, nome: 'Previsão nível 3 – Santos', tipo: 'previsao', nivel: 3 }, geometry: square },
    { type: 'Feature', properties: { id: 3, nome: 'Previsão T', tipo: 'previsao', nivel: 'T' }, geometry: square },
  ];
  requests[0].resolve(payload);
  await flush();
  const [forecastLayer, alertLayer] = fake.groups;
  const forecastAreas = forecastLayer.items.filter((x) => x.kind === 'geojson');
  // nível mais alto desenhado por último (fica por cima)
  assert.deepEqual(forecastAreas.map((x) => x.options.style.color), ['#39ff14', '#ff2a2a']);
  assert.match(forecastAreas[1].popup.text, /Previsão nível 3 – Santos/);
  assert.match(forecastAreas[1].popup.text, /Nível 3/);
  assert.equal(alertLayer.items.length, 1);
  assert.equal(alertLayer.items[0].options.style.color, '#d2142a');
  assert.match(alertLayer.items[0].popup.text, /Alerta de tornado/);
});

test('GPS asks for login without invoking geolocation for anonymous visitors', async () => {
  const { node, requests } = await setup();
  const pending = node('#map-location').events.click();
  requests[1].reject(Object.assign(new Error('Login'), { status: 401 }));
  await pending;
  assert.match(node('#map-status').text, /Entre na sua conta/);
  assert.equal(node('#map-status').children[0].href, '/index.html?next=/mapa.html');
  assert.equal(node('#map-location').disabled, false);
});
