(function () {
  "use strict";

  var STORAGE_KEY = "basil-mail-columns";
  var DEFAULTS = [
    { key: "mailbox", label: "Mailbox", visible: true, width: null, pinned: true },
    { key: "sender", label: "Sender", visible: true, width: null },
    { key: "subject", label: "Subject", visible: true, width: null },
    { key: "date", label: "Date", visible: true, width: null },
    { key: "rules", label: "Rules", visible: true, width: null },
  ];
  var STORAGE_VERSION_KEY = "basil-mail-columns-pinned";

  function mailboxShouldBeHiddenByDefault() {
    // Hidden by default when only one mailbox source exists.
    var table = document.querySelector("[data-columns-table]");
    if (!table) return false;
    var seen = {};
    table.querySelectorAll("[data-col=mailbox] .source-symbol").forEach(function (el) {
      seen[el.title] = true;
    });
    return Object.keys(seen).length <= 1;
  }

  function stateIsPrePin() {
    try {
      return !localStorage.getItem(STORAGE_VERSION_KEY);
    } catch (e) {
      return false;
    }
  }

  function loadState() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var state = JSON.parse(raw);
      if (!Array.isArray(state)) return null;
      var keys = state.map(function (c) { return c.key; });
      var valid = DEFAULTS.every(function (d) { return keys.indexOf(d.key) !== -1; }) &&
                  keys.length === DEFAULTS.length;
      return valid ? state : null;
    } catch (e) {
      return null;
    }
  }

  function saveState(state) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function getState() {
    var state = loadState();
    if (!state) {
      state = getFreshState();
    } else if (stateIsPrePin()) {
      // Migrate a saved order from before the mailbox column was pinned:
      // force mailbox back to the first position.
      var idx = state.findIndex(function (c) { return c.key === "mailbox"; });
      if (idx > 0) {
        state.splice(0, 0, state.splice(idx, 1)[0]);
      }
      try { localStorage.setItem(STORAGE_VERSION_KEY, "1"); } catch (e) {}
      saveState(state);
    }
    return state;
  }

  function getFreshState() {
    // Defaults, honouring the single-source rule for the mailbox column.
    var state = DEFAULTS.map(function (c) { return { key: c.key, visible: c.visible, width: c.width }; });
    if (mailboxShouldBeHiddenByDefault()) {
      state.forEach(function (c) { if (c.key === "mailbox") c.visible = false; });
    }
    return state;
  }

  function getTable(root) {
    return (root || document).querySelector("[data-columns-table]");
  }

  function applyToTable(root) {
    var table = getTable(root);
    if (!table) return;
    var state = getState();
    var order = {};
    state.forEach(function (c, i) { order[c.key] = i; });

    var rows = [];
    var thead = table.querySelector("thead tr");
    if (thead) rows.push(thead);
    table.querySelectorAll("tbody tr").forEach(function (tr) {
      if (tr.children.length > 1) rows.push(tr);
    });

    rows.forEach(function (tr) {
      var cells = Array.prototype.slice.call(tr.children);
      cells.forEach(function (cell) { cell.dataset.col = cell.dataset.col || ""; });
      cells.sort(function (a, b) {
        var pa = a.dataset.col === "mailbox" ? 0 : 1;
        var pb = b.dataset.col === "mailbox" ? 0 : 1;
        if (pa !== pb) return pa - pb;
        var oa = order[a.dataset.col], ob = order[b.dataset.col];
        if (oa === undefined) oa = 99;
        if (ob === undefined) ob = 99;
        return oa - ob;
      });
      cells.forEach(function (cell) { tr.appendChild(cell); });
      cells.forEach(function (cell) {
        var conf = null;
        for (var i = 0; i < state.length; i++) {
          if (state[i].key === cell.dataset.col) { conf = state[i]; break; }
        }
        if (!conf) return;
        cell.style.display = conf.visible ? "" : "none";
        cell.style.width = conf.width ? conf.width + "px" : "";
        if (cell.tagName === "TH") cell.style.minWidth = conf.width ? conf.width + "px" : "";
      });
    });

    table.querySelectorAll("th").forEach(function (th) {
      th.draggable = true;
      th.classList.add("col-draggable");
      if (!th.querySelector(".col-resize")) {
        var handle = document.createElement("span");
        handle.className = "col-resize";
        handle.title = "Drag to resize";
        th.appendChild(handle);
      }
    });
  }

  function moveColumn(draggedKey, targetKey, before) {
    if (draggedKey === "mailbox" || targetKey === "mailbox") return false;
    var st = getState();
    var from = st.findIndex(function (c) { return c.key === draggedKey; });
    var to = st.findIndex(function (c) { return c.key === targetKey; });
    if (from === -1 || to === -1 || from === to) return false;
    var moved = st.splice(from, 1)[0];
    var insertAt = st.findIndex(function (c) { return c.key === targetKey; });
    if (!before) insertAt += 1;
    st.splice(insertAt, 0, moved);
    saveState(st);
    return true;
  }

  function renderMenuItems(menu) {
    var state = getState();
    menu.innerHTML = "";
    DEFAULTS.forEach(function (def) {
      var conf = null;
      state.forEach(function (c) { if (c.key === def.key) conf = c; });
      var li = document.createElement("li");
      li.className = "col-menu-item";
      li.dataset.key = def.key;

      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = conf ? conf.visible : true;
      cb.id = "col-visibility-" + def.key;

      var label = document.createElement("label");
      label.className = "col-label";
      label.htmlFor = cb.id;
      label.textContent = def.label;

      li.appendChild(cb);
      li.appendChild(label);

      cb.addEventListener("change", function () {
        var st = getState();
        st.forEach(function (c) { if (c.key === def.key) c.visible = cb.checked; });
        saveState(st);
        applyToTable(document);
      });

      menu.appendChild(li);
    });
  }

  function init(root) {
    var menu = root.querySelector("[data-col-menu]");
    var panel = root.querySelector("[data-col-panel]");
    if (!menu || !panel) return;

    var button = root.querySelector("[data-col-button]");
    if (button) {
      button.addEventListener("click", function () {
        panel.classList.toggle("open");
        if (panel.classList.contains("open")) renderMenuItems(menu);
      });
    }
    document.addEventListener("click", function (e) {
      if (!panel.classList.contains("open")) return;
      if (panel.contains(e.target) || (button && button.contains(e.target))) return;
      panel.classList.remove("open");
    });

    applyToTable(document);
  }

  function closestTh(el) {
    while (el && el.tagName !== "TH") el = el.parentElement;
    return el && el.dataset && el.dataset.col ? el : null;
  }

  document.addEventListener("DOMContentLoaded", function () {
    init(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail && e.detail.target && e.detail.target.querySelector &&
        e.detail.target.querySelector("[data-columns-table]")) {
      applyToTable(e.detail.target);
    }
  });

  /* Header drag & drop reordering */
  document.addEventListener("dragstart", function (e) {
    var th = closestTh(e.target);
    if (!th || th.dataset.col === "mailbox") { if (th) e.preventDefault(); return; }
    th.classList.add("col-dragging");
    e.dataTransfer.setData("text/plain", "basil-col:" + th.dataset.col);
    e.dataTransfer.effectAllowed = "move";
  });

  document.addEventListener("dragend", function (e) {
    var th = closestTh(e.target);
    if (th) th.classList.remove("col-dragging");
    document.querySelectorAll(".col-drop-before, .col-drop-after").forEach(function (el) {
      el.classList.remove("col-drop-before", "col-drop-after");
    });
  });

  document.addEventListener("dragover", function (e) {
    var th = closestTh(e.target);
    if (!th) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    document.querySelectorAll(".col-drop-before, .col-drop-after").forEach(function (el) {
      el.classList.remove("col-drop-before", "col-drop-after");
    });
    var rect = th.getBoundingClientRect();
    var before = e.clientX < rect.left + rect.width / 2;
    th.classList.add(before ? "col-drop-before" : "col-drop-after");
  });

  document.addEventListener("drop", function (e) {
    var th = closestTh(e.target);
    if (!th) return;
    e.preventDefault();
    var data = e.dataTransfer.getData("text/plain") || "";
    if (data.indexOf("basil-col:") !== 0) return;
    var draggedKey = data.slice("basil-col:".length);
    var rect = th.getBoundingClientRect();
    var before = e.clientX < rect.left + rect.width / 2;
    if (moveColumn(draggedKey, th.dataset.col, before)) {
      applyToTable(document);
    }
  });

  /* Column resize via header edge handles */
  document.addEventListener("mousedown", function (e) {
    var handle = e.target.closest ? e.target.closest(".col-resize") : null;
    if (!handle) return;
    e.preventDefault();
    e.stopPropagation();
    var th = handle.closest("th");
    var key = th.dataset.col;
    var startX = e.clientX;
    var startWidth = th.getBoundingClientRect().width;

    function onMove(ev) {
      var width = Math.max(60, Math.round(startWidth + (ev.clientX - startX)));
      th.style.width = width + "px";
      th.style.minWidth = width + "px";
      var idx = Array.prototype.indexOf.call(th.parentElement.children, th);
      document.querySelectorAll("[data-columns-table] tbody tr").forEach(function (tr) {
        if (tr.children[idx]) tr.children[idx].style.width = width + "px";
      });
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      var st = getState();
      st.forEach(function (c) { if (c.key === key) c.width = parseInt(th.style.width, 10) || null; });
      saveState(st);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
})();
