// The Screen & system page: changes wait until "Save and apply" (txoof 2026-10-23).
// A changed setting is marked with what PaperPi uses now, a bar at the bottom of the window
// counts the changes, and leaving the page with changes asks first. Without JavaScript the
// form has a plain Save and apply button and none of this.
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("system-form");
    if (!form) return;
    var saved = JSON.parse(form.dataset.saved || "{}");
    var bar = document.getElementById("save-bar");
    var count = document.getElementById("save-count");
    var undo = document.getElementById("save-undo");
    var leave = document.getElementById("leave");
    var fields = Array.prototype.slice.call(form.querySelectorAll(".field[data-names]"));
    var sending = false;
    var target = "";
    document.documentElement.classList.add("js-save");

    function inputs(name) {
      return Array.prototype.slice.call(form.querySelectorAll('[name="' + name + '"]'));
    }
    function current(name) {
      var found = inputs(name).filter(function (el) { return el.type !== "hidden"; });
      if (!found.length) return undefined;
      if (found[0].type === "radio") {
        var on = found.filter(function (el) { return el.checked; })[0];
        return on ? on.value : "";
      }
      if (found[0].type === "checkbox") return found[0].checked ? "true" : "false";
      return found[0].value.trim();
    }
    function differs(field) {
      var names = field.dataset.names.split(" ");
      // With Never ticked before and now, the number and unit don't matter.
      if (names.indexOf("clean_never") >= 0 && current("clean_never") === "true") {
        return saved.clean_never !== "true";
      }
      return names.some(function (name) {
        var now = current(name);
        return now !== undefined && now !== saved[name];
      });
    }
    function changed() { return fields.filter(differs); }

    function show() {
      var list = changed();
      fields.forEach(function (field) {
        var on = list.indexOf(field) >= 0;
        field.classList.toggle("changed", on);
        var note = field.querySelector(".not-saved");
        if (on && !note) {
          note = document.createElement("span");
          note.className = "not-saved";
          note.textContent = "Not saved yet (now: " + field.dataset.now + ")";
          field.querySelector(".lbl").appendChild(note);
        } else if (!on && note) {
          note.remove();
        }
      });
      var n = list.length;
      bar.classList.toggle("waiting", n > 0);
      undo.hidden = n === 0;
      count.firstChild.textContent = n + (n === 1 ? " change" : " changes") + " not saved yet";
      return n;
    }

    function putBack() {
      Object.keys(saved).forEach(function (name) {
        inputs(name).forEach(function (el) {
          if (el.type === "hidden") return;
          if (el.type === "radio") el.checked = el.value === saved[name];
          else if (el.type === "checkbox") el.checked = saved[name] === "true";
          else el.value = saved[name];
        });
      });
      show();
    }

    form.addEventListener("input", show);
    form.addEventListener("change", show);
    form.addEventListener("submit", function () { sending = true; });
    undo.addEventListener("click", putBack);

    // Closing the tab or typing another address: the browser asks with its own words.
    window.addEventListener("beforeunload", function (event) {
      if (!sending && changed().length) {
        event.preventDefault();
        event.returnValue = "";
      }
    });

    // A link to another page: PaperPi's own window, which can also save first.
    if (leave && typeof leave.showModal === "function") {
      document.addEventListener("click", function (event) {
        var link = event.target.closest && event.target.closest("a[href]");
        if (!link || link.target || link.hasAttribute("download")) return;
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
        var href = link.getAttribute("href");
        if (href.charAt(0) === "#") return;
        var n = changed().length;
        if (!n) return;
        event.preventDefault();
        target = href;
        document.getElementById("leave-text").textContent =
          "You changed " + n + (n === 1 ? " setting" : " settings") + " on this page that " +
          (n === 1 ? "is" : "are") + " not saved yet.";
        leave.showModal();
      });
      document.getElementById("leave-stay").addEventListener("click", function () {
        leave.close();
      });
      document.getElementById("leave-go").addEventListener("click", function () {
        sending = true;
        window.location.href = target;
      });
      document.getElementById("leave-save").addEventListener("click", function () {
        form.elements.next.value = target.charAt(0) === "/" ? target : "";
        sending = true;
        form.submit();
      });
    }
    show();
  });
})();
