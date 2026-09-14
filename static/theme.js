/* Light/dark toggle button in the footer. The theme itself is *applied* by
 * the inline script in base.html (so it happens before first paint); this
 * just wires up the button to flip it and remember the choice. */
(function () {
  function systemPrefersDark() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") || (systemPrefersDark() ? "dark" : "light");
  }
  function label(theme) {
    return theme === "dark" ? "Light mode" : "Dark mode";
  }
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.textContent = label(currentTheme());
    btn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (e) {
        /* private browsing, etc. - the toggle still works for this page view */
      }
      btn.textContent = label(next);
    });
  });
})();
