document.addEventListener("DOMContentLoaded", async () => {
  const iconPaths = {
    "/inicio.html": ["m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"],
    "/alertas.html": ["M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"],
    "/mapa.html": ["m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2z", "M9 3v16m6-14v16"],
    "/perfil.html": ["M4 21a8 8 0 0 1 16 0"],
    "/estacoes.html": ["M4 20V10m8 10V4m8 16v-7"],
  };
  // Keep the same useful destinations on every screen and give the map the
  // central position from the mobile reference, without a decorative link.
  document.querySelectorAll(".bottom-nav").forEach((nav) => {
    const destinations = [
      ["/inicio.html", "Início"], ["/estacoes.html", "Estações"],
      ["/mapa.html", "Mapa"], ["/alertas.html", "Alertas"],
      ["/perfil.html", "Perfil"],
    ];
    const badge = nav.querySelector("#alert-badge");
    nav.replaceChildren(...destinations.map(([href, label]) => {
      const anchor = document.createElement("a");
      anchor.href = href;
      if (location.pathname === href) {
        anchor.className = "active";
        anchor.setAttribute("aria-current", "page");
      }
      const caption = document.createElement("span");
      caption.textContent = label;
      if (href === "/alertas.html" && badge) caption.append(" ", badge);
      anchor.append(caption);
      return anchor;
    }));
  });
  document.querySelectorAll(".bottom-nav a, .top-actions .icon-button").forEach((anchor) => {
    const paths = anchor.classList.contains("nav-center")
      ? ["M6 17h12a4 4 0 0 0 .4-8A6 6 0 0 0 7 9a4 4 0 0 0-1 8Z", "m13 2-2 5h3l-2 5"]
      : iconPaths[anchor.getAttribute("href")];
    if (!paths) return;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.classList.add("nav-icon");
    if (anchor.getAttribute("href") === "/perfil.html" && !anchor.classList.contains("nav-center")) {
      const head = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      head.setAttribute("cx", "12");
      head.setAttribute("cy", "8");
      head.setAttribute("r", "4");
      svg.append(head);
    }
    paths.forEach((pathData) => {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", pathData);
      svg.append(path);
    });
    if (anchor.firstChild?.nodeType === Node.TEXT_NODE) anchor.firstChild.remove();
    anchor.prepend(svg);
  });

  const navigation = document.querySelector("[data-role-navigation]");
  if (!navigation) return;

  let user = null;
  try {
    user = await PrevClima.request("/users/me");
  } catch (error) {
    if (error.status !== 401) navigation.dataset.error = "true";
  }

  PrevClima.applyTheme(user);

  const links = [
    ["/inicio.html", "Início"],
    ["/alertas.html", "Alertas"],
    ["/mapa.html", "Mapa"],
    ["/estacoes.html", "Estações INMET"],
  ];
  if (user && user.role === "USER") links.push(["/perfil.html", "Perfil"]);
  if (user && user.role === "METEOROLOGIST") {
    links.push(["/painel.html", "Central meteorológica"]);
  }
  if (!user) links.push(["/index.html", "Entrar"]);

  const current = window.location.pathname;
  navigation.replaceChildren();
  links.forEach(([href, label]) => {
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.textContent = label;
    if (current === href) anchor.setAttribute("aria-current", "page");
    navigation.append(anchor);
  });

  const identity = document.querySelector("[data-role-identity]");
  if (identity) {
    identity.textContent = user ? `${user.name} · ${PrevClima.roleName(user.role)}` : "Visitante";
  }
});
