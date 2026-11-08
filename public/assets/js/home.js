document.addEventListener("DOMContentLoaded", () => {
  const modal = document.querySelector("#location-modal");
  const form = document.querySelector("#location-form");
  const message = document.querySelector("#location-message");
  let currentUser = null;
  let requestId = 0;

  function showForecast(data) {
    const forecast = data.forecast;
    document.querySelector("#forecast-status").textContent = forecast ? (forecast.is_stale ? "Dado salvo" : "Previsão atualizada") : "Indisponível";
    if (forecast) {
      document.querySelector("#location-name").textContent = `${forecast.city}, ${forecast.state}`;
      document.querySelector("#home-map-link").href = `/mapa.html?${new URLSearchParams({ city: forecast.city, state: forecast.state })}`;
      const condition = forecast.condition.toLowerCase();
      PrevClimaWeatherArt(document.querySelector(".weather-icon"), condition);
      document.querySelector("#temperature").textContent = Math.round(Number(forecast.temperature_c));
      document.querySelector("#condition").textContent = forecast.condition;
      document.querySelector("#max-temperature").textContent = Math.round(Number(forecast.maximum_c));
      document.querySelector("#min-temperature").textContent = Math.round(Number(forecast.minimum_c));
      document.querySelector("#humidity").textContent = `${forecast.humidity}%`;
      document.querySelector("#wind").textContent = `${Number(forecast.wind_kmh)} km/h`;
      document.querySelector("#rain").textContent = `${forecast.rain_probability}%`;
      const source = document.querySelector("#data-source");
      source.textContent = `Fonte: ${forecast.source_name}${forecast.is_stale ? " (último dado salvo)" : ""}`;
      if (forecast.source_url) source.href = forecast.source_url; else source.removeAttribute("href");
      document.querySelector("#updated-at").textContent = `Atualizado ${PrevClima.relativeTime(forecast.issued_at)}`;
    } else {
      document.querySelector("#condition").textContent = "Sem previsão cadastrada para esta localidade";
      ["temperature", "max-temperature", "min-temperature", "humidity", "wind", "rain"].forEach((id) => {
        document.querySelector(`#${id}`).textContent = "--";
      });
      document.querySelector("#data-source").textContent = "";
      document.querySelector("#data-source").removeAttribute("href");
      document.querySelector("#updated-at").textContent = "";
    }

    const first = data.active_alerts[0];
    document.querySelector("#warning-panel").dataset.severity = first?.severity || "UNKNOWN";
    document.querySelector(".risk-icon").textContent = first ? "!" : "i";
    document.querySelector("#warning-feed").textContent = PrevClima.feedStatus(data.warning_feed);
    document.querySelector("#warning-title").textContent = first
      ? first.title
      : "Nenhum aviso disponível";
    document.querySelector("#warning-message").textContent = first
      ? first.message
      : "A ausência de avisos disponíveis não confirma ausência de risco. Confira também os avisos oficiais do INMET.";
    document.querySelector("#warning-source").textContent = first
      ? `Origem: ${first.source_name}`
      : "";
    document.querySelector("#alert-badge").textContent = data.unread_alert_count || "";
  }

  async function load(city, state) {
    const id = ++requestId;
    document.querySelector("#forecast-status").textContent = "Consultando";
    const params = new URLSearchParams();
    if (city && state) {
      params.set("city", city);
      params.set("state", state);
    }
    const suffix = params.size ? `?${params}` : "";
    try {
      const data = await PrevClima.request(`/home${suffix}`);
      if (id !== requestId) return false;
      showForecast(data);
      return true;
    } catch (error) {
      if (id !== requestId) return false;
      showForecast({ forecast: null, active_alerts: [], unread_alert_count: 0 });
      document.querySelector("#condition").textContent = error.message;
      document.querySelector("#warning-title").textContent = "Avisos indisponíveis";
      document.querySelector("#warning-message").textContent = "Não foi possível consultar os dados. Tente novamente em instantes.";
      return false;
    }
  }

  async function initialize() {
    try {
      currentUser = await PrevClima.request("/users/me");
      PrevClima.applyTheme(currentUser);
      document.querySelector("#auth-state").textContent = currentUser.name;
      if (currentUser.city && currentUser.state) {
        document.querySelector("#location-name").textContent = `${currentUser.city}, ${currentUser.state}`;
        form.city.value = currentUser.city;
        form.state.value = currentUser.state;
      }
    } catch (error) {
      if (error.status !== 401) document.querySelector("#auth-state").textContent = "Indisponível";
    }
    await load();
  }

  function closeLocation() { modal.close(); modal.classList.remove("open"); }
  document.querySelector("#open-location").addEventListener("click", () => {
    modal.classList.add("open");
    modal.showModal();
    form.city.focus();
  });
  modal.addEventListener("close", () => modal.classList.remove("open"));
  document.querySelector("#close-location").addEventListener("click", closeLocation);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    const submit = form.querySelector('button[type="submit"]');
    PrevClima.setBusy(submit, true);
    const city = form.city.value.trim();
    const state = form.state.value.trim().toUpperCase();
    try {
      if (currentUser) {
        currentUser = await PrevClima.request("/users/me", {
          method: "PATCH",
          body: JSON.stringify({ city, state }),
        });
      }
      document.querySelector("#location-name").textContent = `${city}, ${state}`;
      if (await load(city, state)) closeLocation();
      else message.textContent = "Não foi possível consultar esta localidade. Tente novamente.";
    } catch (error) {
      message.textContent = error.message;
    } finally {
      PrevClima.setBusy(submit, false);
    }
  });

  initialize();
});
