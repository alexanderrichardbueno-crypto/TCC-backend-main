document.addEventListener("DOMContentLoaded", async () => {
  const form = document.querySelector("#login-form");
  const message = document.querySelector("#form-message");
  const next = new URLSearchParams(window.location.search).get("next");
  let destination = "/inicio.html";
  if (next && next.startsWith("/") && !next.startsWith("//") && !next.includes("\\")) {
    try {
      const target = new URL(next, window.location.origin);
      if (target.origin === window.location.origin) {
        destination = `${target.pathname}${target.search}${target.hash}`;
      }
    } catch (_error) { /* Destino malformado: usar a página inicial. */ }
  }
  if (!form) return;

  // O nível de acesso da conta define para onde a pessoa vai.
  async function enter(user) {
    if (user.role !== "METEOROLOGIST") {
      window.location.replace(destination);
      return;
    }
    const session = await PrevClima.request("/auth/session-token", { method: "POST" });
    sessionStorage.setItem("prevclima_token", session.access_token);
    window.location.replace("/painel.html");
  }

  try {
    await enter(await PrevClima.request("/users/me"));
    return;
  } catch (error) {
    if (error.status !== 401) message.textContent = error.message;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    message.textContent = "";
    PrevClima.setBusy(button, true);
    try {
      const result = await PrevClima.request("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.email.value.trim(),
          password: form.password.value,
        }),
      });
      await enter(result.user);
    } catch (error) {
      if (error.message === "Confirme seu e-mail antes de entrar") {
        window.location.assign(`/confirmar-email.html?email=${encodeURIComponent(form.email.value.trim())}`);
        return;
      }
      message.textContent = error.message;
    } finally {
      PrevClima.setBusy(button, false);
    }
  });
});
