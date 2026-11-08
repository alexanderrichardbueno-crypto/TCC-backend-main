document.addEventListener("DOMContentLoaded", async () => {
  const form = document.querySelector("#profile-form");
  const message = document.querySelector("#profile-message");
  const toast = document.querySelector("#toast");
  const toggles = {
    weather_notifications: document.querySelector("#weather-notifications"),
    alert_sound: document.querySelector("#alert-sound"),
    dark_theme: document.querySelector("#dark-theme"),
  };

  function notify(text) {
    toast.textContent = text;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function render(user) {
    PrevClima.applyTheme(user);
    document.querySelector("#profile-name").textContent = user.name;
    document.querySelector("#profile-email").textContent = user.email;
    document.querySelector("#profile-role").textContent = PrevClima.roleName(user.role);
    document.querySelector("#profile-code").textContent = `Código: ${user.public_code}`;
    form.name.value = user.name;
    form.city.value = user.city || "";
    form.state.value = user.state || "";
    Object.entries(toggles).forEach(([field, element]) => { element.checked = user[field]; });
  }

  try {
    render(await PrevClima.request("/users/me"));
  } catch (error) {
    if (error.status === 401) window.location.replace("/index.html?next=/perfil.html");
    else message.textContent = error.message;
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    message.textContent = "";
    PrevClima.setBusy(button, true);
    try {
      render(await PrevClima.request("/users/me", {
        method: "PATCH",
        body: JSON.stringify({
          name: form.name.value.trim(),
          city: form.city.value.trim() || null,
          state: form.state.value.trim().toUpperCase() || null,
        }),
      }));
      notify("Perfil atualizado");
    } catch (error) {
      message.textContent = error.message;
    } finally {
      PrevClima.setBusy(button, false);
    }
  });

  Object.entries(toggles).forEach(([field, element]) => {
    element.addEventListener("change", async () => {
      const previous = !element.checked;
      try {
        await PrevClima.request("/users/me", {
          method: "PATCH",
          body: JSON.stringify({ [field]: element.checked }),
        });
        notify("Preferência atualizada");
      } catch (error) {
        element.checked = previous;
        notify(error.message);
      }
    });
  });

  document.querySelector("#logout").addEventListener("click", async () => {
    try {
      await PrevClima.request("/auth/logout", { method: "POST" });
    } finally {
      window.location.assign("/index.html");
    }
  });
});
