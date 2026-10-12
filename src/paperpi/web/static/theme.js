// Light or dark look. The page follows the device's setting; the Dark/Light button in the
// menu overrides it, and this browser remembers the choice. Loaded at the top of every page,
// so a chosen look is set before the page is drawn.
(function () {
  "use strict";
  var KEY = "paperpi-theme";
  var root = document.documentElement;
  // Parts of the look that only work with JavaScript (the home page's sticky screen).
  root.classList.add("js");
  try {
    var saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  } catch (e) {
    // Storage blocked (private window): the page follows the device.
  }

  function dark() {
    var chosen = root.getAttribute("data-theme");
    if (chosen) return chosen === "dark";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function label() {
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].textContent = dark() ? "Light" : "Dark";
      buttons[i].setAttribute("aria-label", dark() ? "Switch to the light look" : "Switch to the dark look");
      buttons[i].hidden = false;
    }
  }

  document.addEventListener("DOMContentLoaded", label);
  // The device may switch between light and dark while the page is open.
  if (window.matchMedia) {
    var query = window.matchMedia("(prefers-color-scheme: dark)");
    if (query.addEventListener) query.addEventListener("change", label);
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-theme-toggle]");
    if (!button) return;
    var next = dark() ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try {
      localStorage.setItem(KEY, next);
    } catch (e) {
      // Not remembered, but still switched for this page.
    }
    label();
  });
})();
