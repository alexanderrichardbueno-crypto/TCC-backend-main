export const api = window.PrevClima.request;
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const date = (value) =>
  value ? new Date(value).toLocaleString("pt-BR") : "Não disponível";
export const metric = (value, unit = "") =>
  value == null ? "—" : `${Number(value).toLocaleString("pt-BR")}${unit}`;
export const empty = (message) => `<div class="empty">${esc(message)}</div>`;
export const field = (label, name, type = "text", extra = "") =>
  `<label>${label}<input class="field" name="${name}" type="${type}" ${extra}></label>`;
export const panel = (title, body, action = "") =>
  `<section class="panel"><div class="panel-h"><h2>${title}</h2>${action}</div><div class="panel-b">${body}</div></section>`;
export function notify(message, error = false) {
  const node = document.querySelector("#notice");
  node.textContent = message;
  node.className = error ? "notice error" : "notice";
  node.hidden = false;
}
export async function action(button, operation) {
  button.disabled = true;
  try {
    return await operation();
  } catch (error) {
    notify(error.message, true);
  } finally {
    button.disabled = false;
  }
}
export function submit(form, handler) {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    action(form.querySelector("[type=submit]"), () =>
      handler(Object.fromEntries(new FormData(form))),
    );
  });
}
export const json = (method, body) => ({ method, body: JSON.stringify(body) });
export function alertCard(a) {
  const color = { LOW: "ok", MODERATE: "mod", HIGH: "high", CRITICAL: "crit" }[
    a.severity
  ];
  return `<article class="data-card"><div class="row spread"><strong>${esc(a.title)}</strong><span class="pill ${color}">${esc(PrevClima.severityName(a.severity))}</span></div><p>${esc(a.message)}</p><p class="hint">${esc(a.area_name)} · ${esc(a.source_name)}</p><p class="hint">Até ${date(a.valid_until)}</p><ul>${a.recommendations.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></article>`;
}
