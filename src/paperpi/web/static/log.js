// The Full log: the newest lines are at the bottom, so the list starts scrolled down. New
// lines ("New lines as they come") keep it at the bottom, unless someone scrolled up to read.
(function () {
  "use strict";
  var atBottom = true;
  function box() {
    return document.getElementById("lines");
  }
  function down() {
    var lines = box();
    if (lines) lines.scrollTop = lines.scrollHeight;
  }
  document.addEventListener("DOMContentLoaded", down);
  document.addEventListener("htmx:beforeSwap", function () {
    var lines = box();
    atBottom = !lines || lines.scrollHeight - lines.scrollTop - lines.clientHeight < 40;
  });
  document.addEventListener("htmx:afterSettle", function (event) {
    var lines = box();
    // Hours of new lines: the oldest go, so the page keeps no more than it shows at first.
    var most = lines ? Number(lines.dataset.most) || 0 : 0;
    while (lines && most && lines.querySelectorAll(".ln").length > most) {
      lines.removeChild(lines.firstElementChild);
    }
    // A new filter or search shows the newest lines; new lines only when nobody scrolled up.
    var target = event.detail.target;
    if (atBottom || (target && target.id !== "lines")) down();
  });
})();
