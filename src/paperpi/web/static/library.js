// The Plugin Library's search box: shows only the plugins whose title, type, description or labels
// has every word typed. Without JavaScript the box stays hidden and every plugin is shown.
// + Add opens a window with the Add form from the page's server, and a plugin's picture or
// title opens one with Look closer (its layout buttons load it again); without JavaScript (or
// when the part can't be fetched) they open the Add page or the Look closer page.
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var box = document.querySelector(".search");
    var input = document.getElementById("search");
    var count = document.getElementById("search-count");
    var none = document.getElementById("no-match");
    var items = document.querySelectorAll("#library > li");
    libraryWindow();
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

  function libraryWindow() {
    var dialog = document.getElementById("window");
    if (!dialog || typeof dialog.showModal !== "function") return;
    var opener = null;
    var asking = false; // a part is being fetched

    document.addEventListener("click", function (event) {
      var link = event.target.closest("a.add, a.look, .layout-pick a");
      if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
      event.preventDefault();
      if (asking) return; // a double click opens one window
      if (!dialog.open) opener = link;
      asking = true;
      fetch(link.href, { headers: { "HX-Request": "true" }, credentials: "same-origin" })
        .then(function (response) {
          // Logged out meanwhile (the log-in page), or a problem: the whole page says why.
          if (!response.ok || response.redirected) throw new Error(response.status);
          return response.text();
        })
        .then(function (html) {
          dialog.innerHTML = html;
          if (window.htmx) window.htmx.process(dialog); // a picture still being drawn
          if (!dialog.open) dialog.showModal();
          var name = dialog.querySelector("#add-name");
          var current = dialog.querySelector(".layout-pick [aria-current]");
          if (name) name.select();
          else if (current) current.focus();
        })
        .catch(function () { window.location.href = link.href; })
        .finally(function () { asking = false; });
    });

    dialog.addEventListener("click", function (event) {
      // Cancel or Close, or a click on the dark area around the window.
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
