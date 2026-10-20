// The Plugin Library's search box: shows only the plugins whose title, type, description or labels
// has every word typed. Without JavaScript the box stays hidden and every plugin is shown.
// + Add opens the Add window with the Add form from the page's server; without JavaScript (or
// when the form can't be fetched) it opens the Add page.
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var box = document.querySelector(".search");
    var input = document.getElementById("search");
    var count = document.getElementById("search-count");
    var none = document.getElementById("no-match");
    var items = document.querySelectorAll("#library > li");
    addWindow();
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

    filter(); // the browser may have kept a search from before
    box.hidden = false; // shown after the count is written, so it isn't read out at once
    input.addEventListener("input", filter);
  });

  function addWindow() {
    var dialog = document.getElementById("add-window");
    if (!dialog || typeof dialog.showModal !== "function") return;
    var opener = null;

    document.addEventListener("click", function (event) {
      var link = event.target.closest("a.add");
      if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
      event.preventDefault();
      opener = link;
      fetch(link.href, { headers: { "HX-Request": "true" }, credentials: "same-origin" })
        .then(function (response) {
          // Logged out meanwhile (the log-in page), or a problem: the Add page says why.
          if (!response.ok || response.redirected) throw new Error(response.status);
          return response.text();
        })
        .then(function (html) {
          dialog.innerHTML = html;
          dialog.showModal();
          var name = dialog.querySelector("#add-name");
          if (name) name.select();
        })
        .catch(function () { window.location.href = link.href; });
    });

    dialog.addEventListener("click", function (event) {
      // Cancel, or a click on the dark area around the window.
      if (event.target.closest("[data-close]") || event.target === dialog) {
        event.preventDefault();
        dialog.close();
      }
    });
    dialog.addEventListener("submit", function (event) {
      var button = event.target.querySelector("button[type=submit]");
      if (button) button.disabled = true; // added once, also after a double click
    });
    dialog.addEventListener("close", function () {
      dialog.innerHTML = "";
      if (opener) opener.focus();
    });
  }
})();
