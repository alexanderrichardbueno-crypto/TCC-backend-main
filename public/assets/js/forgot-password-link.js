// Leva o e-mail digitado no login para a página de redefinição de senha.
document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href*="recuperar-senha.html"]');
  if (!link) return;
  const input = document.querySelector('#email, #mobile-login-form input[name="email"]');
  const email = input ? input.value.trim() : "";
  link.href = link.href.split("#")[0] + (email ? `#email=${encodeURIComponent(email)}` : "");
});
