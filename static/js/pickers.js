try { (function () {
  "use strict";

  function colorInputs(symbolPicker) {
    var colorPicker = document.getElementById(
      symbolPicker.dataset.colorPickerId
    );
    return {
      light: document.getElementById(colorPicker.dataset.pickerFor),
      dark: document.getElementById(colorPicker.dataset.pickerForDark),
      colorPicker: colorPicker
    };
  }

  function refreshPicker(symbolPicker) {
    var symbolInput = document.getElementById(symbolPicker.dataset.pickerFor);
    var parts = colorInputs(symbolPicker);
    var light = parts.light.value || "#2f6f4f";
    var dark = parts.dark.value || "#6fbf8f";
    symbolPicker.querySelectorAll(".picker-item").forEach(function (btn) {
      btn.querySelector(".icon-light").style.color = light;
      btn.querySelector(".icon-dark").style.color = dark;
      btn.classList.toggle("selected", btn.dataset.value === symbolInput.value);
    });
    parts.colorPicker.querySelectorAll(".picker-item").forEach(function (btn) {
      btn.classList.toggle(
        "selected",
        btn.dataset.value.toLowerCase() === (parts.light.value || "").toLowerCase()
      );
    });
  }

  function autosave(btn) {
    var form = btn.closest("form.inline-edit-form");
    if (form && window.htmx) {
      htmx.trigger(form, "submit");
    }
  }

  window.pickSymbol = function (btn) {
    var symbolPicker = btn.closest("[id^='symbol-picker']");
    var symbolInput = document.getElementById(symbolPicker.dataset.pickerFor);
    symbolInput.value = btn.dataset.value;
    refreshPicker(symbolPicker);
    autosave(btn);
  };

  window.pickColor = function (btn) {
    var colorPicker = btn.closest("[id^='color-picker']");
    document.getElementById(colorPicker.dataset.pickerFor).value = btn.dataset.value;
    document.getElementById(colorPicker.dataset.pickerForDark).value =
      btn.dataset.valueDark;
    var symbolPicker = document.querySelector(
      "[data-color-picker-id='" + colorPicker.id + "']"
    );
    if (symbolPicker) {
      refreshPicker(symbolPicker);
    }
    autosave(btn);
  };

  function initAll() {
    document.querySelectorAll("[id^='symbol-picker-']").forEach(function (sp) {
      var symbolInput = document.getElementById(sp.dataset.pickerFor);
      if (!symbolInput.value) {
        symbolInput.value = sp.id.indexOf("-r-") !== -1 ? "star" : "envelope";
      }
      refreshPicker(sp);
    });
  }

  document.addEventListener("DOMContentLoaded", initAll);
  document.body.addEventListener("htmx:afterSwap", function () {
    initAll();
  });
})(); } catch (err) { console.error(err); }


/* Persist accordion open/close state in localStorage and restore it,
   plus keep it across HTMX re-renders. */
try { (function () {
  "use strict";
  var STORAGE_KEY = "basil-config-accordions";

  function loadOpenIds() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  function saveOpenIds(ids) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
    } catch (e) {}
  }

  function currentOpenIds() {
    var ids = [];
    document.querySelectorAll("#config-body details[open]").forEach(function (d) {
      ids.push(d.id);
    });
    return ids;
  }

  var restoring = false;

  /* Track toggle interactions to persist the user's accordion state. */
  document.addEventListener("toggle", function (e) {
    var el = e.target;
    if (restoring) {
      return;
    }
    if (el && el.tagName === "DETAILS" && el.closest("#config-body")) {
      saveOpenIds(currentOpenIds());
    }
  }, true);

  /* Restore the saved state for every accordion rendered on the page. */
  function restore() {
    var saved = loadOpenIds();
    if (!saved.length) {
      return;
    }
    restoring = true;
    try {
      document.querySelectorAll("#config-body details").forEach(function (d) {
        d.open = saved.indexOf(d.id) !== -1;
      });
    } finally {
      /* let pending toggle events flush before re-enabling saves */
      setTimeout(function () { restoring = false; }, 0);
    }
  }

  document.addEventListener("DOMContentLoaded", restore);

  /* Across HTMX swaps: capture open state, re-apply after the swap. */
  var openIds = [];
  document.body.addEventListener("htmx:beforeSwap", function () {
    openIds = currentOpenIds();
  });
  function reOpen() {
    openIds.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) {
        el.open = true;
      }
    });
  }
  document.body.addEventListener("htmx:afterSwap", function () {
    if (!document.getElementById("config-body")) {
      return;
    }
    reOpen();
    saveOpenIds(currentOpenIds());
  });
})(); } catch (err) { console.error(err); }


/* Inline rename in accordion summaries: pen icon -> input, save on blur. */
try { (function () {
  function beginRename(displayEl, url, currentValue) {
    var original = displayEl.textContent.trim();
    var input = document.createElement("input");
    input.type = "text";
    input.value = currentValue;
    input.className = "rename-input";
    displayEl.style.display = "none";
    displayEl.parentElement.insertBefore(input, displayEl);
    input.focus();
    input.select();

    function restore() {
      input.remove();
      displayEl.style.display = "";
    }

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        input.blur();
      } else if (e.key === "Escape") {
        input.value = original;
        input.blur();
      }
    });
    input.addEventListener("blur", function () {
      var value = input.value.trim();
      if (!value || value === original) {
        restore();
        return;
      }
      var fd = new FormData();
      fd.append("name", value);
      fetch(url, {
        method: "POST",
        body: fd,
        headers: {
          "X-CSRFToken": (document.cookie.split("; ").find(function (c) {
            return c.startsWith("csrftoken=");
          }) || "=").split("=")[1] || ""
        }
      }).then(function (resp) {
        if (!resp.ok) {
          restore();
        } else {
          window.location.reload();
        }
      });
    });
  }

  window.startRename = function (pk, btn) {
    var display = document.querySelector(
      "[data-name-display='" + pk + "']"
    );
    var name = display.textContent.trim();
    var url = "/config/sources/" + pk + "/rename/";
    beginRename(display, url, name);
  };

  window.startRuleRename = function (pk, btn) {
    var display = document.querySelector(
      "[data-rule-name-display='" + pk + "']"
    );
    var name = display.textContent.trim();
    var url = "/config/rules/" + pk + "/rename/";
    beginRename(display, url, name);
  };
})(); } catch (err) { console.error(err); }


try { (function () {
  "use strict";

  /* Dynamic condition rows in rule forms. */
  window.addCondition = function (btn, prefix) {
    var form = btn.closest("form");
    var list = form.querySelector("[data-conditions]");
    var totalInput = form.querySelector(
      'input[name="' + prefix + '-TOTAL_FORMS"]'
    );
    if (!list || !totalInput) {
      return;
    }
    var total = parseInt(totalInput.value, 10) || 0;
    // clone the last row and clear its values
    var last = list.querySelector(".condition-row:last-of-type");
    var row = last.cloneNode(true);
    row.querySelectorAll("input, select").forEach(function (el) {
      var name = el.name;
      if (!name) {
        return;
      }
      var m = name.match(/^(.*)-(\d+)-(.*)$/);
      if (!m) {
        return;
      }
      el.name = m[1] + "-" + total + "-" + m[3];
      if (el.id) {
        el.id = "id_" + el.name;
      }
      if (el.tagName === "INPUT" && el.type !== "checkbox") {
        el.value = "";
      } else if (el.tagName === "INPUT") {
        el.checked = false;
      }
    });
    // remove id hidden inputs on the clone (new objects)
    row.querySelectorAll('input[name$="-id"]').forEach(function (el) {
      el.value = "";
    });
    list.appendChild(row);
    totalInput.value = String(total + 1);
    relabelLetters(list);
  };

  window.removeCondition = function (btn) {
    var row = btn.closest(".condition-row");
    var form = btn.closest("form");
    var list = row.parentElement;
    var m = (row.querySelector('input[name$="-id"]') || {}).name;
    var match = (row.querySelector("select, input:not([type=hidden])") || {}).name;
    if (match) {
      var mm = match.match(/^(.*)-(\d+)-(.*)$/);
      if (mm && m) {
        // mark deletion if the row is an existing condition (has id with value)
        var idInput = row.querySelector('input[name$="-id"]');
        if (idInput && idInput.value) {
          var deleteName = mm[1] + "-" + mm[2] + "-DELETE";
          var del = document.createElement("input");
          del.type = "hidden";
          del.name = deleteName;
          del.value = "on";
          row.appendChild(del);
          row.style.display = "none";
          relabelLetters(list);
          return;
        }
      }
    }
    // new (unsaved) row: just drop it and decrement TOTAL_FORMS
    var prefix = mm ? mm[1] : null;
    row.remove();
    if (prefix && form) {
      var totalInput = form.querySelector(
        'input[name="' + prefix + '-TOTAL_FORMS"]'
      );
      if (totalInput) {
        var total = parseInt(totalInput.value, 10) || 0;
        totalInput.value = String(Math.max(0, total - 1));
      }
    }
    relabelLetters(list);
  };

  function relabelLetters(list) {
    var index = 0;
    list.querySelectorAll(".condition-row").forEach(function (row) {
      if (row.style.display === "none") {
        return;
      }
      index += 1;
      var letter = row.querySelector(".condition-letter");
      if (letter) {
        letter.textContent = String.fromCharCode(65 + index - 1);
      }
    });
  }
})(); } catch (err) { console.error(err); }

try { (function () {
  "use strict";

  /* Event delegation: attach/detach sender suggestions based on the
     target field, immune to swaps. */
  function syncRow(row) {
    if (!row) {
      return;
    }
    var target = row.querySelector("select[name$='-target_field']");
    var value = row.querySelector("input[name$='-value']");
    if (!target || !value) {
      return;
    }
    if (target.value === "sender") {
      value.setAttribute("list", "sender-suggestions");
    } else {
      value.removeAttribute("list");
    }
  }

  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches("select[name$='-target_field']")) {
      syncRow(e.target.closest(".condition-row"));
    }
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".condition-row").forEach(syncRow);
  });
  document.body.addEventListener("htmx:afterSwap", function () {
    document.querySelectorAll(".condition-row").forEach(syncRow);
  });
})(); } catch (err) { console.error(err); }

try { (function () {
  "use strict";

  /* Logic builder: buttons insert tokens at the caret in the logic input. */
  function insertAtCaret(input, token) {
    var start = input.selectionStart !== null ? input.selectionStart : input.value.length;
    var end = input.selectionEnd !== null ? input.selectionEnd : input.value.length;
    var needsSpaceBefore = start > 0 && /\S$/.test(input.value.slice(0, start))
      && /^[A-Za-z!&|()]/.test(token);
    var needsSpaceAfter = /^\S/.test(token)
      && input.value.length > end && /^[A-Za-z!&|()]/.test(input.value.slice(end));
    var prefix = input.value.slice(0, start) + (needsSpaceBefore ? " " : "");
    var suffix = (needsSpaceAfter ? " " : "") + input.value.slice(end);
    input.value = prefix + token + suffix;
    var caret = (prefix + token).length;
    input.focus();
    try {
      input.setSelectionRange(caret, caret);
    } catch (e) {}
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  /* Event delegation: one document-level click handler, immune to swaps. */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest
      ? e.target.closest("[data-insert].logic-btn, .condition-letter[data-insert]")
      : null;
    if (!btn) {
      return;
    }
    var form = btn.closest("form");
    if (!form) {
      return;
    }
    var input = form.querySelector("input[name$='-logic_expr']");
    if (input) {
      insertAtCaret(input, btn.dataset.insert);
    }
  });
})(); } catch (err) { console.error(err); }

try { (function () {
  "use strict";

  /* Clear buttons for the logic builder. */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".logic-clear") : null;
    if (!btn) {
      return;
    }
    var builder = btn.closest(".logic-builder");
    var input = builder.querySelector("input[name$='-logic_expr']");
    if (input) {
      input.value = "";
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
})(); } catch (err) { console.error(err); }

try { (function () {
  "use strict";

  /* Live validity feedback for the logic input. Mirrors mails/logic.py:
     letters A-Z, AND/&& OR/|| NOT/!, parentheses. */
  function validateLogic(expr) {
    var tokens = [];
    var i = 0;
    var src = expr.toUpperCase();
    while (i < src.length) {
      var ch = src[i];
      if (ch === " " || ch === "\t") { i += 1; continue; }
      if (ch === "(" || ch === ")") { tokens.push(ch); i += 1; continue; }
      if (ch === "!") { tokens.push("NOT"); i += 1; continue; }
      if (ch === "&" || ch === "|") {
        var dbl = src.substr(i, 2) === ch + ch;
        if (!dbl) { return false; }
        tokens.push(ch === "&" ? "AND" : "OR");
        i += 2;
        continue;
      }
      if (src.substr(i, 3) === "AND") { tokens.push("AND"); i += 3; continue; }
      if (src.substr(i, 2) === "OR") { tokens.push("OR"); i += 2; continue; }
      if (src.substr(i, 3) === "NOT") { tokens.push("NOT"); i += 3; continue; }
      if (ch >= "A" && ch <= "Z") { tokens.push("L"); i += 1; continue; }
      return false;
    }
    if (!tokens.length) { return false; }
    var pos = [0];
    function peek() { return tokens[pos[0]]; }
    function next() { return tokens[pos[0]++]; }
    function parseExpr() {
      if (!parseTerm()) { return false; }
      while (peek() === "OR") { next(); if (!parseTerm()) { return false; } }
      return true;
    }
    function parseTerm() {
      if (!parseFactor()) { return false; }
      while (peek() === "AND") { next(); if (!parseFactor()) { return false; } }
      return true;
    }
    function parseFactor() {
      var t = peek();
      if (t === "NOT") { next(); return parseFactor(); }
      if (t === "(") {
        next();
        if (!parseExpr()) { return false; }
        if (peek() !== ")") { return false; }
        next();
        return true;
      }
      if (t === "L") { next(); return true; }
      return false;
    }
    if (!parseExpr()) { return false; }
    return pos[0] === tokens.length;
  }

  function paint(input) {
    var valid = validateLogic(input.value);
    input.classList.toggle("logic-valid", valid);
    input.classList.toggle("logic-invalid", !valid);
  }

  /* Event delegation on the bubbling input event, immune to swaps. */
  document.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("input[name$='-logic_expr']")) {
      paint(e.target);
    }
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("input[name$='-logic_expr']").forEach(paint);
  });
  document.body.addEventListener("htmx:afterSwap", function () {
    document.querySelectorAll("input[name$='-logic_expr']").forEach(paint);
  });
})(); } catch (err) { console.error(err); }

try { (function () {
  "use strict";

  /* Live match-count pill: when the logic expression is valid, fetch the
     number of matching mails and update the pill. */
  function debounce(fn, ms) {
    var t = null;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, args); }, ms || 300);
    };
  }

  function fetchCount(builder, input) {
    var url = builder.dataset.countUrl;
    if (!url) {
      return;
    }
    var fd = new FormData();
    fd.append("logic", input.value);
    fetch(url, {
      method: "POST",
      body: fd,
      headers: {
        "X-CSRFToken": (document.cookie.split("; ").find(function (c) {
          return c.startsWith("csrftoken=");
        }) || "=").split("=")[1] || ""
      }
    }).then(function (r) { return r.json(); }).then(function (data) {
      var pill = builder.querySelector("[data-count]");
      if (!pill) {
        return;
      }
      if (data.valid) {
        pill.textContent = data.count;
        pill.hidden = false;
      } else {
        pill.hidden = true;
      }
    }).catch(function () {});
  }

  var debouncedFetch = debounce(fetchCount, 250);

  /* Event delegation: the bubbling input event drives the count, immune
     to swaps. */
  document.addEventListener("input", function (e) {
    var input = e.target;
    if (!input.matches || !input.matches("input[name$='-logic_expr']")) {
      return;
    }
    var builder = input.closest(".logic-builder");
    if (!builder || !builder.dataset.countUrl) {
      return;
    }
    if (input.classList.contains("logic-valid")) {
      debouncedFetch(builder, input);
    } else {
      var pill = builder.querySelector("[data-count]");
      if (pill) {
        pill.hidden = true;
      }
    }
  });
})(); } catch (err) { console.error(err); }

try { (function () {
  "use strict";

  /* Dynamic action rows in rule forms (clone last row, clear values). */
  window.addAction = function (btn) {
    var form = btn.closest("form");
    var block = form.querySelector("[data-actions]");
    if (!block) {
      return;
    }
    var prefixInput = form.querySelector(
      'input[name$="-actions-TOTAL_FORMS"]'
    );
    if (!prefixInput) {
      return;
    }
    var m = prefixInput.name.match(/^(.*)-TOTAL_FORMS$/);
    if (!m) {
      return;
    }
    var prefix = m[1];
    var total = parseInt(prefixInput.value, 10) || 0;
    var last = block.querySelector(".action-row:last-of-type");
    var row;
    if (last) {
      row = last.cloneNode(true);
      row.querySelectorAll("input, select").forEach(function (el) {
        var name = el.name;
        var mm = name.match(/^(.*)-(\d+)-(.*)$/);
        if (!mm) {
          return;
        }
        el.name = mm[1] + "-" + total + "-" + mm[3];
        if (el.id) {
          el.id = "id_" + el.name;
        }
        if (el.tagName === "INPUT" && el.type !== "checkbox") {
          el.value = "";
        } else if (el.tagName === "INPUT") {
          el.checked = false;
        }
      });
      row.querySelectorAll('input[name$="-id"]').forEach(function (el) {
        el.value = "";
      });
    } else {
      row = document.createElement("div");
      row.className = "action-row";
      row.innerHTML =
        '<input type="hidden" name="' + prefix + "-" + total + '-id">' +
        '<div class="inline-field act-type"><select name="' + prefix + "-" + total + '-action_type" id="id_' + prefix + '-' + total + '-action_type">' +
        '<option value="mark_read">Mark as read</option>' +
        '<option value="http_callback">Send to REST callback</option></select></div>' +
        '<label class="inline-field act-url"><input type="url" name="' + prefix + "-" + total + '-callback_url" id="id_' + prefix + '-' + total + '-callback_url" placeholder="https://..."></label>';
    }
    block.appendChild(row);
    prefixInput.value = String(total + 1);
  };
})(); } catch (err) { console.error(err); }

try { (function () {
  "use strict";

  /* Remove an action row: existing rows are marked DELETE, new rows dropped. */
  window.removeAction = function (btn) {
    var row = btn.closest(".action-row");
    var form = btn.closest("form");
    var list = row.parentElement;
    var idInput = row.querySelector('input[name$="-id"]');
    if (idInput && idInput.value) {
      var m = idInput.name.match(/^(.*)-(\d+)-id$/);
      if (m) {
        var del = document.createElement("input");
        del.type = "hidden";
        del.name = m[1] + "-" + m[2] + "-DELETE";
        del.value = "on";
        row.appendChild(del);
        row.style.display = "none";
        return;
      }
    }
    // new (unsaved) row: drop and decrement TOTAL_FORMS
    row.remove();
    if (form) {
      var totalInput = form.querySelector('input[name$="-actions-TOTAL_FORMS"]');
      if (totalInput) {
        var total = parseInt(totalInput.value, 10) || 0;
        totalInput.value = String(Math.max(0, total - 1));
      }
    }
  };
})(); } catch (err) { console.error(err); }
