document.addEventListener("DOMContentLoaded", async () => {
  const list = document.querySelector("#alert-list");
  const count = document.querySelector("#active-count");
  const location = document.querySelector("#confirmed-location");
  let signedIn = true;
  try {
    const user = await PrevClima.request("/users/me");
    PrevClima.applyTheme(user);
  } catch (error) {
    signedIn = false;
  }

  function paragraph(text, className) {
    const node = document.createElement("p");
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  function render(alert) {
    const card = document.createElement("article");
    card.className = "alert-card";
    card.dataset.severity = alert.severity;

    const summary = document.createElement("button");
    summary.type = "button";
    summary.className = "alert-summary";
    summary.setAttribute("aria-expanded", "false");
    const icon = document.createElement("strong");
    icon.textContent = "!";
    const info = document.createElement("div");
    const origin = alert.origin === "MANUAL" ? "PREVCLIMA" : "INMET";
    info.append(paragraph(`${PrevClima.severityName(alert.severity).toUpperCase()} · ${origin}`, "alert-level"));
    const title = document.createElement("h2");
    title.className = "alert-title";
    title.textContent = alert.title;
    info.append(title, paragraph(alert.area_name, "muted"));
    const issued = new Date(alert.issued_at);
    const timeText = `Emitido ${PrevClima.relativeTime(issued)} · válido até ${new Date(alert.valid_until).toLocaleString("pt-BR")}`;
    info.append(paragraph(timeText, "alert-time"));
    const read = paragraph(alert.is_read ? "Lido" : "Abrir", alert.is_read ? "read-label" : "muted");
    summary.append(icon, info, read);

    const detail = document.createElement("div");
    detail.className = "alert-detail";
    detail.append(paragraph(alert.message));
    const source = paragraph(`Origem: ${alert.source_name}`, "data-source");
    detail.append(source);
    if (alert.source_url && alert.source_url.startsWith("https://")) {
      const sourceLink = document.createElement("a");
      sourceLink.href = alert.source_url;
      sourceLink.target = "_blank";
      sourceLink.rel = "noopener noreferrer";
      sourceLink.textContent = "Abrir fonte oficial";
      sourceLink.className = "helper";
      detail.append(sourceLink);
    }
    const recommendations = document.createElement("div");
    recommendations.className = "recommendations";
    const heading = document.createElement("strong");
    heading.textContent = "Recomendações";
    const items = document.createElement("ul");
    alert.recommendations.forEach((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      items.append(item);
    });
    recommendations.append(heading, items);
    detail.append(recommendations);
    card.append(summary, detail);

    summary.addEventListener("click", async () => {
      card.classList.toggle("open");
      summary.setAttribute("aria-expanded", String(card.classList.contains("open")));
      if (signedIn && !alert.is_read) {
        try {
          await PrevClima.request(`/alerts/${alert.id}/read`, { method: "POST" });
          alert.is_read = true;
          read.className = "read-label";
          read.textContent = "Lido";
        } catch (error) {
          read.textContent = error.message;
        }
      }
    });
    return card;
  }

  // Sem permissão ou sem sinal, a API usa a cidade do perfil.
  function deviceCoordinates() {
    return new Promise((resolve) => {
      if (!navigator.geolocation) { resolve(null); return; }
      navigator.geolocation.getCurrentPosition(
        (position) => resolve({ latitude: position.coords.latitude.toFixed(2), longitude: position.coords.longitude.toFixed(2) }),
        () => resolve(null),
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 900000 },
      );
    });
  }

  function renderForecast(forecast) {
    const card = document.createElement("article");
    card.className = "alert-card";
    card.dataset.severity = forecast.severity;
    const body = document.createElement("div");
    body.className = "alert-summary";
    body.style.cursor = "default";
    const icon = document.createElement("strong");
    icon.textContent = "!";
    const info = document.createElement("div");
    const title = document.createElement("h2");
    title.className = "alert-title";
    title.textContent = "Previsão de tempo severo";
    info.append(
      paragraph(`${forecast.level_name.toUpperCase()} · PREVCLIMA`, "alert-level"),
      title,
      paragraph(forecast.description, "muted"),
      paragraph(`Emitida ${PrevClima.relativeTime(new Date(forecast.issued_at))} · válida até ${new Date(forecast.valid_until).toLocaleString("pt-BR")}`, "alert-time"),
    );
    body.append(icon, info);
    card.append(body);
    return card;
  }

  try {
    const coords = await deviceCoordinates();
    const data = await PrevClima.request(`/alerts/nearby${coords ? `?${new URLSearchParams(coords)}` : ""}`);
    const total = data.alerts.length + data.forecasts.length;
    count.textContent = `${total} ativo${total === 1 ? "" : "s"}`;
    location.textContent = data.location
      ? `Sua região: ${data.location}${coords || signedIn ? "" : " · Permita a localização ou entre e informe sua cidade no perfil"}`
      : "Não foi possível identificar sua região. Confira a cidade no seu perfil.";
    list.replaceChildren();
    if (!total) list.append(paragraph("Nenhum alerta ou previsão para a sua região. Confira também a fonte oficial do INMET; a ausência de avisos não confirma ausência de risco.", "empty"));
    data.alerts.forEach((alert) => list.append(render(alert)));
    data.forecasts.forEach((forecast) => list.append(renderForecast(forecast)));
  } catch (error) {
    location.textContent = "";
    count.textContent = "Indisponível";
    list.replaceChildren(paragraph(error.message, "error"));
  }
});
