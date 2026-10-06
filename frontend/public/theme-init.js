// Theme and density bootstrap (docs/dev-guide.md DG-FE-13; DESIGN_SYSTEM DS-DEN-01).
// Loaded by index.html as a blocking external script before the stylesheet, so the first paint
// already uses the stored preferences. There is no inline script (DG-FE-12, REQ-SEC-004).
(function () {
  var root = document.documentElement;
  var theme = null;
  var density = null;
  try {
    theme = window.localStorage.getItem("erev.theme");
    density = window.localStorage.getItem("erev.density");
  } catch (error) {
    // Storage can be unavailable (privacy mode); the OS theme and comfortable density apply.
  }
  if (theme === "light" || theme === "dark") {
    root.setAttribute("data-theme", theme);
  }
  root.setAttribute("data-density", density === "compact" ? "compact" : "comfortable");
})();
