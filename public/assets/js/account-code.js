document.addEventListener("DOMContentLoaded", () => {
  const flow = document.body.dataset.flow;
  const params = new URLSearchParams(window.location.search);
  const fromApp = params.get("app") === "1";
  const form = document.querySelector("#code-form");
  const message = document.querySelector("#form-message");
  const email = document.querySelector("#email");
  if (params.get("email")) email.value = params.get("email");
  const post = (path, body) => PrevClima.request(path, { method: "POST", body: JSON.stringify(body) });

  async function submit(target, output, operation) {
    const button = target.querySelector("button[type='submit']");
    output.textContent = "";
    PrevClima.setBusy(button, true);
    try {
      await operation();
    } catch (error) {
      output.textContent = error.message;
    } finally {
      PrevClima.setBusy(button, false);
    }
  }

  if (flow === "verify") {
    const resend = document.querySelector("#resend");
    resend.addEventListener("click", async () => {
      message.textContent = "";
      try {
        const result = await post("/auth/resend-verification", { email: email.value.trim() });
        message.textContent = result.message;
      } catch (error) {
        message.textContent = error.message;
      }
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submit(form, message, async () => {
        await post("/auth/verify-email", { email: email.value.trim(), code: form.code.value.trim() });
        window.location.assign(fromApp ? "/mobile/" : "/localizacao.html");
      });
    });
    return;
  }

  const requestForm = document.querySelector("#request-form");
  requestForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(requestForm, document.querySelector("#request-message"), async () => {
      const result = await post("/auth/forgot-password", { email: email.value.trim() });
      document.querySelector("#request-message").textContent = result.message;
      form.hidden = false;
    });
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(form, message, async () => {
      await post("/auth/reset-password", {
        email: email.value.trim(),
        code: form.code.value.trim(),
        password: form.password.value,
      });
      window.location.assign(fromApp ? "/mobile/" : "/index.html");
    });
  });
});
