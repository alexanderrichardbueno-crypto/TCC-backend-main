// Tema claro/escuro e logo das páginas públicas, iguais aos da central meteorológica.
(function () {
  const KEY = "prevclima_central_v2_theme";
  const FALLBACK_LOGO = "/assets/img/logo-reserva.svg";
  const root = document.documentElement;
  const media = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : null;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (_error) { return null; }
  }
  function current() {
    return stored() || (media && !media.matches ? "light" : "dark");
  }
  function show(theme) {
    root.setAttribute("data-theme", theme);
    root.classList.toggle("light", theme === "light");
    const profileSwitch = document.querySelector("#dark-theme");
    if (profileSwitch) profileSwitch.checked = theme === "dark";
    document.dispatchEvent(new CustomEvent("prevclima:theme", { detail: theme }));
  }
  function set(theme) {
    try { localStorage.setItem(KEY, theme); } catch (_error) { /* Vale só nesta página. */ }
    show(theme);
  }
  show(current());
  window.PrevClimaTheme = { current, set };
  if (media) media.addEventListener("change", () => { if (!stored()) show(current()); });

  document.addEventListener("error", (event) => {
    const image = event.target;
    if (image && image.tagName === "IMG" && image.hasAttribute("data-logo")
        && image.getAttribute("src") !== FALLBACK_LOGO) {
      image.setAttribute("src", FALLBACK_LOGO);
    }
  }, true);

  const ICONS = {
    dark: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    light: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9"/>',
  };
  document.addEventListener("DOMContentLoaded", () => {
    const host = document.querySelector(".top-actions, .topbar, .mobile-topbar, .public-stations .top");
    const button = document.createElement("button");
    button.type = "button";
    button.className = host ? "theme-toggle" : "theme-toggle floating";
    const paint = () => {
      const dark = current() === "dark";
      button.title = dark ? "Usar tema claro" : "Usar tema escuro";
      button.setAttribute("aria-label", button.title);
      button.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[dark ? "dark" : "light"]}</svg>`;
    };
    button.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      set(next);
      if (window.PrevClima) {
        PrevClima.request("/users/me", {
          method: "PATCH",
          body: JSON.stringify({ dark_theme: next === "dark" }),
        }).catch(() => { /* Visitante: a escolha fica neste navegador. */ });
      }
    });
    document.addEventListener("prevclima:theme", paint);
    paint();
    const logout = host && host.querySelector(".mobile-logout");
    const items = [button];
    if (window.location.pathname !== "/informacoes.html") {
      const education = document.createElement("a");
      education.href = "/informacoes.html";
      education.className = host ? "edu-button" : "edu-button floating";
      education.title = "Informações educativas";
      education.setAttribute("aria-label", education.title);
      education.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2Z"/><path d="M4 21V5"/></svg><span>Informações educativas</span>';
      items.unshift(education);
    }
    items.forEach((item) => {
      if (logout) host.insertBefore(item, logout);
      else (host || document.body).append(item);
    });
    if (document.querySelector("#dark-theme")) show(current());
  });
})();
