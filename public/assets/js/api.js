(function () {
  const errorMessages = {
    "Authentication required": "Entre na sua conta para continuar.",
    "Insufficient permission": "Sua conta não tem permissão para realizar esta ação.",
    "Email already registered": "Este e-mail já está cadastrado.",
    "Invalid email or password": "E-mail ou senha inválidos.",
    "Professional access required": "Esta área é exclusiva para contas profissionais.",
    "Database roles are not initialized": "Os perfis de acesso ainda não foram configurados.",
    "Alert not found": "Alerta não encontrado.",
    "No current forecast": "Não há previsão atual para esta localidade.",
    "User not found": "Usuário não encontrado.",
    "Invalid CSRF token": "A sessão expirou. Atualize a página e tente novamente.",
    "city and state must be supplied together": "Informe a cidade e a UF juntas.",
    "city and state must be supplied together or both cleared": "Informe a cidade e a UF juntas ou apague os dois campos.",
    "latitude and longitude must be supplied together": "Informe latitude e longitude juntas.",
    "latitude and longitude must be supplied together or both cleared": "Informe latitude e longitude juntas ou apague os dois campos.",
    "use upper/lowercase letters, a number and a special character": "Use letras maiúsculas e minúsculas, um número e um símbolo.",
    "occurred_at cannot be in the future": "A data da ocorrência não pode estar no futuro.",
  };

  function cookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    const item = document.cookie.split("; ").find((part) => part.startsWith(prefix));
    return item ? decodeURIComponent(item.slice(prefix.length)) : "";
  }

  async function request(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrf = cookie("prevclima_csrf");
      if (csrf) headers.set("X-CSRF-Token", csrf);
    }

    let response;
    try {
      response = await fetch(`/api/v1${path}`, {
        ...options,
        method,
        headers,
        credentials: "same-origin",
      });
    } catch (_error) {
      const error = new Error("Não foi possível conectar ao PrevClima. Verifique sua conexão.");
      error.status = 0;
      throw error;
    }
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data && data.detail;
      const rawMessage = Array.isArray(detail)
        ? detail.map((item) => item.msg).join(". ")
        : detail;
      const message = errorMessages[rawMessage]
        || rawMessage
        || "Não foi possível concluir a solicitação.";
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function setBusy(button, busy) {
    if (!button) return;
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? "Aguarde..." : button.dataset.label;
  }

  function applyTheme(user) {
    if (user && window.PrevClimaTheme) PrevClimaTheme.set(user.dark_theme ? "dark" : "light");
  }

  function roleName(role) {
    return {
      USER: "Usuário",
      METEOROLOGIST: "Meteorologista",
    }[role] || role;
  }

  function severityName(severity) {
    return {
      LOW: "Baixo",
      MODERATE: "Moderado",
      HIGH: "Alto",
      CRITICAL: "Crítico",
    }[severity] || severity;
  }

  function eventName(eventType) {
    return {
      SEVERE_STORM: "Tempestade severa",
      TORNADO: "Tornado",
      WINDSTORM: "Vendaval",
      HEAVY_RAIN: "Chuva intensa",
    }[eventType] || eventType;
  }

  function relativeTime(value) {
    const difference = new Date(value).getTime() - Date.now();
    const minutes = Math.round(difference / 60000);
    const formatter = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });
    if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
    const hours = Math.round(minutes / 60);
    if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
    return formatter.format(Math.round(hours / 24), "day");
  }

  function feedStatus(feed) {
    const messages = {
      current: "Sincronização concluída. Avisos vigentes da última consulta.",
      stale: "Sincronização atrasada. Exibindo apenas avisos salvos ainda vigentes.",
      unavailable: "INMET indisponível na última tentativa. Os avisos salvos continuam até sua validade.",
      pending: "Aguardando a primeira sincronização do INMET.",
      disabled: "Sincronização do INMET desativada nesta instalação.",
    };
    const message = messages[feed?.status] || "Estado da sincronização não disponível.";
    return message + (feed?.last_success_at ? ` Última consulta concluída: ${new Date(feed.last_success_at).toLocaleString("pt-BR")}.` : "");
  }

  window.PrevClima = { feedStatus, request, setBusy, applyTheme, roleName, severityName, eventName, relativeTime };
})();
