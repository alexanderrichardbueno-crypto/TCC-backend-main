document.addEventListener("DOMContentLoaded", () => {
  const flow = document.body.dataset.flow;
  const params = new URLSearchParams(window.location.search);
  const fromApp = params.get("app") === "1";
  const form = document.querySelector("#code-form");
  const message = document.querySelector("#form-message");
  const email = document.querySelector("#email");
  const givenEmail = new URLSearchParams(window.location.hash.slice(1)).get("email") || params.get("email");
  if (givenEmail) email.value = givenEmail;
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
  const SENT_KEY = "prevclima-reset-code-sent";
  const CODE_LIFETIME_MS = 30 * 60 * 1000;

  // Recarregar a página não deve gerar outro código e invalidar o que já chegou.
  function recentlySent(address) {
    try {
      const sent = JSON.parse(sessionStorage.getItem(SENT_KEY) || "null");
      return Boolean(sent) && sent.email === address && Date.now() - sent.at < CODE_LIFETIME_MS;
    } catch {
      return false;
    }
  }

  function rememberSent(address) {
    try {
      sessionStorage.setItem(SENT_KEY, JSON.stringify({ email: address, at: Date.now() }));
    } catch {
      // Sem armazenamento, o pior caso é reenviar o código ao recarregar.
    }
  }

  async function sendCode() {
    const address = email.value.trim();
    message.textContent = "";
    try {
      const result = await post("/auth/forgot-password", { email: address });
      message.textContent = result.message;
      rememberSent(address);
    } catch (error) {
      message.textContent = error.message;
    }
  }

  document.querySelector("#resend-code").addEventListener("click", sendCode);

  if (givenEmail && email.checkValidity()) {
    const target = document.querySelector("#code-target");
    target.textContent = `O código será enviado para ${email.value.trim()}.`;
    target.hidden = false;
    requestForm.hidden = true;
    form.hidden = false;
    if (!recentlySent(email.value.trim())) sendCode();
  }

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
