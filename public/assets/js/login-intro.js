(() => {
  const intro = document.querySelector("#login-intro");
  const content = document.querySelector(".auth-form-column");
  const skip = document.querySelector("#skip-intro");
  if (!intro || !content || !skip) return;
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let seen = false;
  try { seen = sessionStorage.getItem("prevclima-login-intro") === "seen"; } catch (_) { /* Storage is optional. */ }
  if (motion.matches || seen) return;

  intro.hidden = false;
  content.inert = true;
  document.body.classList.add("intro-active");
  let timer;
  let finished = false;
  function finish() {
    if (finished) return;
    finished = true;
    clearTimeout(timer);
    const restoreFocus = intro.contains(document.activeElement);
    intro.hidden = true;
    content.inert = false;
    document.body.classList.remove("intro-active");
    document.body.classList.add("intro-complete");
    try { sessionStorage.setItem("prevclima-login-intro", "seen"); } catch (_) { /* Storage is optional. */ }
    if (restoreFocus) document.querySelector("#email")?.focus();
    motion.removeEventListener("change", onMotionChange);
  }
  function onMotionChange(event) { if (event.matches) finish(); }
  skip.addEventListener("click", finish);
  motion.addEventListener("change", onMotionChange);
  timer = setTimeout(finish, 3400);
})();
