// The home page: list or grid, changing the order (drag or arrows) without loading the page
// again, and the screen panel that becomes a slim bar while scrolling down. Without
// JavaScript the page still works: the arrows are forms that load the page again.
(function () {
  "use strict";
  var STYLE_KEY = "paperpi-cards";

  document.addEventListener("DOMContentLoaded", function () {
    var cards = document.getElementById("cards");
    if (!cards) return;
    setUpStyle(cards);
    setUpOrder(cards);
    setUpShrink();
  });

  // List or grid, remembered by this browser.
  function setUpStyle(cards) {
    var pick = document.querySelector(".style-pick");
    var buttons = pick.querySelectorAll("[data-style]");
    function use(style) {
      cards.classList.toggle("grid", style === "grid");
      for (var i = 0; i < buttons.length; i++) {
        buttons[i].setAttribute("aria-pressed", String(buttons[i].dataset.style === style));
      }
    }
    try {
      use(localStorage.getItem(STYLE_KEY) === "grid" ? "grid" : "list");
    } catch (e) {
      use("list"); // storage blocked (private window)
    }
    pick.hidden = false;
    pick.addEventListener("click", function (event) {
      var button = event.target.closest("[data-style]");
      if (!button) return;
      use(button.dataset.style);
      try {
        localStorage.setItem(STYLE_KEY, button.dataset.style);
      } catch (e) {
        // Not remembered, but still used on this page.
      }
    });
  }

  function setUpOrder(cards) {
    var toggle = document.querySelector("[data-order]");
    var hint = document.querySelector(".order-hint");
    var sortable = null;
    var busy = false;
    toggle.hidden = false;

    toggle.addEventListener("click", function () {
      var on = !cards.classList.contains("ordering");
      cards.classList.toggle("ordering", on);
      toggle.setAttribute("aria-pressed", String(on));
      toggle.textContent = on ? "Done" : "Change order";
      hint.hidden = !on;
      if (on && !sortable && window.Sortable) {
        sortable = window.Sortable.create(cards, {
          handle: ".handle",
          animation: 150,
          ghostClass: "ghost",
          // Mouse and touch events instead of the browser's own dragging, which works
          // differently in each browser.
          forceFallback: true,
          onEnd: function (event) {
            if (event.oldIndex !== event.newIndex) save(event.item, event.oldIndex, event.newIndex);
          },
        });
      }
      if (sortable) sortable.option("disabled", !on);
    });

    // The arrows: move the card here and save, instead of loading the page again.
    cards.addEventListener("click", function (event) {
      var button = event.target.closest(".order button");
      if (!button) return;
      event.preventDefault();
      if (busy) return;
      var card = button.closest(".card");
      var from = place(card);
      var to = from + (button.value === "up" ? -1 : 1);
      if (to < 0 || to >= cards.children.length) return;
      var other = cards.children[to];
      if (to < from) cards.insertBefore(card, other);
      else cards.insertBefore(card, other.nextSibling);
      save(card, from, to);
      button.focus();
    });

    function place(card) {
      return Array.prototype.indexOf.call(cards.children, card);
    }

    function save(card, from, to) {
      // One move at a time, so they reach PaperPi in order.
      busy = true;
      if (sortable) sortable.option("disabled", true);
      var body = new URLSearchParams({ id: card.dataset.id, to: String(to) });
      fetch("/plugins/" + from + "/move", {
        method: "POST",
        headers: { "HX-Request": "true" },
        body: body,
        credentials: "same-origin",
      })
        .then(function (response) {
          // Logged out meanwhile: PaperPi asks to open the log-in page; nothing was saved.
          var away = response.headers.get("HX-Redirect");
          if (away) {
            window.location.href = away;
            return;
          }
          if (response.status === 204) {
            // A card without an ID is known by its place, which just changed.
            if (!card.dataset.id) return window.location.reload();
            renumber();
            busy = false;
            if (sortable) sortable.option("disabled", !cards.classList.contains("ordering"));
            return;
          }
          return response.text().then(function (text) {
            // The file changed meanwhile, or can't be changed: show the list as it is now.
            window.alert(text || "The order could not be saved.");
            window.location.reload();
          });
        })
        .catch(function () {
          window.alert("PaperPi could not be reached. The order was not saved.");
          window.location.reload();
        });
    }

    // After a move: new numbers, and the forms and links point at the new places.
    function renumber() {
      var all = cards.children;
      for (var i = 0; i < all.length; i++) {
        var pos = all[i].querySelector(".pos");
        pos.textContent = String(i + 1);
        pos.setAttribute("aria-label", "Place " + (i + 1));
        var parts = all[i].querySelectorAll("form[action^='/plugins/'], a[href^='/plugins/']");
        for (var j = 0; j < parts.length; j++) {
          var name = parts[j].tagName === "FORM" ? "action" : "href";
          parts[j].setAttribute(name, parts[j].getAttribute(name).replace(/^\/plugins\/\d+\//, "/plugins/" + i + "/"));
        }
        var arrows = all[i].querySelectorAll(".order button");
        arrows[0].disabled = i === 0;
        arrows[1].disabled = i === all.length - 1;
      }
    }
  }

  // The screen panel becomes a slim bar while scrolling down; "Show bigger" goes back up.
  function setUpShrink() {
    var small = false;
    function check() {
      var panel = document.getElementById("now"); // replaced every few seconds
      if (!panel) return;
      // Two limits, so the bar doesn't flicker when its own size change moves the page.
      if (!small && window.scrollY > 120) small = true;
      else if (small && window.scrollY < 20) small = false;
      panel.classList.toggle("compact", small);
    }
    window.addEventListener("scroll", check, { passive: true });
    document.body.addEventListener("htmx:load", check); // a new panel came in
    document.body.addEventListener("click", function (event) {
      if (!event.target.closest("[data-bigger]")) return;
      event.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    check();
  }

  // Nobody looks at a hidden tab: don't ask PaperPi for the screen part then.
  document.addEventListener("htmx:beforeRequest", function (event) {
    if (document.hidden && event.detail.elt.id === "now") event.preventDefault();
  });
})();
