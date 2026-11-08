// Ilustração animada do tempo atual, escolhida a partir do texto da previsão.
(function () {
  const DEFS = `<defs>
    <radialGradient id="wa-sun"><stop offset="0" stop-color="#fff3a8"/><stop offset=".55" stop-color="#ffc928"/><stop offset="1" stop-color="#ff9500"/></radialGradient>
    <radialGradient id="wa-moon" cx=".35" cy=".35"><stop offset="0" stop-color="#fff8dc"/><stop offset="1" stop-color="#ffd978"/></radialGradient>
    <linearGradient id="wa-cloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#bcd4ff"/></linearGradient>
    <linearGradient id="wa-gray" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c3d0ea"/><stop offset="1" stop-color="#7f93bd"/></linearGradient>
    <linearGradient id="wa-storm" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7d86b8"/><stop offset="1" stop-color="#3a3f73"/></linearGradient>
    <linearGradient id="wa-bolt" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff59a"/><stop offset="1" stop-color="#ffb300"/></linearGradient>
    <radialGradient id="wa-glow"><stop offset="0" stop-color="#ffe66b" stop-opacity=".75"/><stop offset="1" stop-color="#ffe66b" stop-opacity="0"/></radialGradient>
  </defs>`;
  const CLOUD = "M66 126h112a34 34 0 0 0 6-67.5A50 50 0 0 0 88 46a42 42 0 0 0-22 80z";
  const delay = (index, step) => `style="animation-delay:${(index * step).toFixed(2)}s"`;

  function sun(x, y, radius) {
    const rays = Array.from({ length: 12 }, (_, i) => {
      const angle = (i * Math.PI) / 6;
      const point = (r) => `${(x + Math.cos(angle) * r).toFixed(1)} ${(y + Math.sin(angle) * r).toFixed(1)}`;
      return `<path d="M${point(radius * 1.3)}L${point(radius * 1.72)}"/>`;
    }).join("");
    return `<circle class="wa-pulse" cx="${x}" cy="${y}" r="${radius * 2}" fill="url(#wa-glow)"/>
      <g class="wa-spin" stroke="#ffc928" stroke-width="7" stroke-linecap="round">${rays}</g>
      <circle cx="${x}" cy="${y}" r="${radius}" fill="url(#wa-sun)"/>`;
  }
  function moon(x, y, radius) {
    const stars = [[34, 40], [196, 34], [58, 112], [214, 100]]
      .map(([sx, sy], i) => `<circle class="wa-twinkle" ${delay(i, 0.6)} cx="${sx}" cy="${sy}" r="3.2" fill="#fff3b0"/>`).join("");
    return `${stars}<circle class="wa-pulse" cx="${x}" cy="${y}" r="${radius * 1.9}" fill="url(#wa-glow)"/>
      <path fill="url(#wa-moon)" d="M${x + radius * 0.35} ${y - radius}a${radius} ${radius} 0 1 0 ${radius * 0.65} ${radius * 1.75}a${radius * 0.82} ${radius * 0.82} 0 0 1-${radius * 0.65}-${radius * 1.75}z"/>`;
  }
  const cloud = (fill, extra = "") => `<g class="wa-float" ${extra}><path d="${CLOUD}" fill="url(#${fill})"/></g>`;
  const smallCloud = (fill) => `<g class="wa-float-slow" transform="translate(96 72) scale(.62)"><path d="${CLOUD}" fill="url(#${fill})"/></g>`;

  function drops(count, thin) {
    return Array.from({ length: count }, (_, i) => {
      const x = 70 + ((i * 113) / Math.max(count - 1, 1)) + (Math.random() - 0.5) * 8;
      const y = 132 + Math.random() * 20;
      const length = thin ? 9 : 17;
      // Velocidades diferentes e fases espalhadas impedem que as gotas caiam em grupos.
      const duration = 0.7 + Math.random() * 0.45;
      const phase = (i * 0.618 + Math.random() * 0.15) % 1;
      const timing = `style="animation-duration:${duration.toFixed(2)}s;animation-delay:-${(phase * duration).toFixed(2)}s"`;
      return `<path class="wa-drop" ${timing} d="M${x.toFixed(1)} ${y.toFixed(1)}l-4 ${length}" stroke="#69c3ff" stroke-width="${thin ? 3 : 4.5}" stroke-linecap="round"/>`;
    }).join("");
  }
  function hail() {
    return Array.from({ length: 8 }, (_, i) => `<circle class="wa-hail" ${delay(i, 0.17)} cx="${76 + i * 15}" cy="${134 + (i % 3) * 7}" r="5.5" fill="#eaf8ff" stroke="#8fd3ff" stroke-width="1.5"/>`).join("");
  }
  function snow() {
    return Array.from({ length: 9 }, (_, i) => `<g transform="translate(${72 + i * 13} ${136 + (i % 3) * 7})"><g class="wa-snow" ${delay(i, 0.32)} stroke="#ffffff" stroke-width="2.6" stroke-linecap="round"><path d="M-6 0H6M0-6V6M-4-4 4 4M4-4-4 4"/></g></g>`).join("");
  }
  function bolts() {
    const bolt = "M0 0-16 34h14L-11 66 20 24H5L14 0z";
    return `<circle class="wa-sky-flash" cx="124" cy="96" r="120" fill="url(#wa-glow)"/>
      <circle class="wa-sky-flash" style="animation-delay:1.5s" cx="160" cy="96" r="100" fill="url(#wa-glow)"/>
      <path class="wa-bolt" d="${bolt}" fill="url(#wa-bolt)" stroke="#ff9500" stroke-width="1.5" transform="translate(102 124)"/>
      <path class="wa-bolt wa-bolt-late" d="${bolt}" fill="url(#wa-bolt)" stroke="#ff9500" stroke-width="1.5" transform="translate(160 124) scale(.78)"/>`;
  }
  function fog() {
    return [[52, 138, 140], [36, 158, 172], [70, 178, 112]]
      .map(([x, y, width], i) => `<rect class="wa-fog" ${delay(i, 0.9)} x="${x}" y="${y}" width="${width}" height="9" rx="4.5" fill="#dfe9ff"/>`).join("");
  }

  function scene(condition, night) {
    const text = String(condition || "").toLowerCase();
    const sky = night ? moon(160, 58, 32) : sun(160, 62, 32);
    if (/granizo/.test(text)) return { key: "granizo", art: cloud("wa-storm") + hail() + bolts() };
    if (/tempestade|trovoada/.test(text)) return { key: "raios", art: drops(11) + cloud("wa-storm") + bolts() };
    if (/neve/.test(text)) return { key: "neve", art: cloud("wa-gray") + snow() };
    if (/nevoeiro|neblina/.test(text)) return { key: "neblina", art: cloud("wa-gray") + fog() };
    if (/garoa/.test(text)) return { key: "garoa", art: cloud("wa-gray") + drops(6, true) };
    if (/chuva/.test(text)) {
      const count = /forte|intensa|violenta/.test(text) ? 15 : /moderada/.test(text) ? 10 : 6;
      return { key: `chuva${count}`, art: drops(count) + cloud(count > 10 ? "wa-storm" : "wa-gray") };
    }
    if (/predominantemente limpo/.test(text)) return { key: `quase-limpo${night}`, art: sky + `<g class="wa-float" transform="translate(-34 58) scale(.66)"><path d="${CLOUD}" fill="url(#wa-cloud)"/></g>` };
    if (/limpo/.test(text)) return { key: `limpo${night}`, art: night ? moon(120, 98, 48) : sun(120, 100, 46) };
    if (/parcialmente/.test(text)) return { key: `parcial${night}`, art: (night ? moon(190, 46, 30) : sun(190, 48, 30)) + cloud("wa-cloud") };
    return { key: "nublado", art: smallCloud("wa-gray") + cloud("wa-cloud") };
  }

  window.PrevClimaWeatherArt = function (host, condition) {
    const hour = new Date().getHours();
    const { key, art } = scene(condition, hour < 6 || hour >= 18);
    if (host.dataset.scene === key) return; // Não reinicia a animação a cada atualização.
    host.dataset.scene = key;
    host.innerHTML = `<svg viewBox="0 0 240 210" role="presentation" focusable="false">${DEFS}${art}</svg>`;
  };
})();
