// The Show button next to a password field: shows what was typed, so it can be checked
// before it is sent (typing on a phone is easy to get wrong), and hides it again.
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var buttons = document.querySelectorAll("[data-show]");
    for (var i = 0; i < buttons.length; i++) buttons[i].hidden = false;
  });
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-show]");
    if (!button) return;
    var input = document.getElementById(button.getAttribute("data-show"));
    var show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "Hide" : "Show";
    button.setAttribute("aria-pressed", show ? "true" : "false");
  });
  // Sent hidden again, so the browser doesn't keep it as ordinary typed text.
  document.addEventListener("submit", function (event) {
    var inputs = event.target.querySelectorAll(".pw input");
    for (var i = 0; i < inputs.length; i++) inputs[i].type = "password";
  });
})();
