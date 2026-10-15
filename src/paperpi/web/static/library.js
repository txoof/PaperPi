// The Plugin Library's search box: shows only the plugins whose title, type, description or labels
// has every word typed. Without JavaScript the box stays hidden and every plugin is shown.
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var box = document.querySelector(".search");
    var input = document.getElementById("search");
    var count = document.getElementById("search-count");
    var none = document.getElementById("no-match");
    var items = document.querySelectorAll("#library > li");
    if (!box || !items.length) return;

    function filter() {
      var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      var shown = 0;
      for (var i = 0; i < items.length; i++) {
        var text = items[i].dataset.search;
        var match = words.every(function (word) { return text.indexOf(word) !== -1; });
        items[i].hidden = !match;
        if (match) shown++;
      }
      count.textContent = shown + " of " + items.length + " plugins";
      none.hidden = shown > 0;
    }

    input.addEventListener("input", filter);
    box.hidden = false;
    filter(); // the browser may have kept a search from before
  });
})();
