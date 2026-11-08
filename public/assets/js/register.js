document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#register-form");
  const message = document.querySelector("#form-message");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    message.textContent = "";
    PrevClima.setBusy(button, true);
    const city = form.city.value.trim();
    const state = form.state.value.trim().toUpperCase();
    try {
      await PrevClima.request("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          name: form.name.value.trim(),
          email: form.email.value.trim(),
          password: form.password.value,
          city: city || null,
          state: state || null,
        }),
      });
      window.location.assign(`/confirmar-email.html?email=${encodeURIComponent(form.email.value.trim())}`);
    } catch (error) {
      message.textContent = error.message;
    } finally {
      PrevClima.setBusy(button, false);
    }
  });
});
