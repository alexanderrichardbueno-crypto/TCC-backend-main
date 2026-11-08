document.addEventListener("DOMContentLoaded", async () => {
  const button = document.querySelector("#allow-location");
  const message = document.querySelector("#location-message");

  try {
    PrevClima.applyTheme(await PrevClima.request("/users/me"));
  } catch (error) {
    if (error.status === 401) window.location.replace("/index.html?next=/localizacao.html");
    return;
  }

  button.addEventListener("click", () => {
    message.textContent = "";
    if (!navigator.geolocation) {
      message.textContent = "Este navegador não oferece geolocalização.";
      return;
    }
    PrevClima.setBusy(button, true);
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        try {
          await PrevClima.request("/users/me", {
            method: "PATCH",
            body: JSON.stringify({ latitude: coords.latitude, longitude: coords.longitude }),
          });
          window.location.assign("/inicio.html");
        } catch (error) {
          message.textContent = error.message;
          PrevClima.setBusy(button, false);
        }
      },
      () => {
        message.textContent = "Não foi possível obter a localização. Você pode continuar e tentar novamente no perfil.";
        PrevClima.setBusy(button, false);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
    );
  });
});
