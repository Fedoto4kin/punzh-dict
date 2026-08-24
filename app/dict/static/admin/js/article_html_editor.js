(function () {
  var BEAUTIFY_OPTIONS = {
    indent_size: 2,
    indent_char: " ",
    indent_inner_html: true,
    wrap_attributes: "auto",
    extra_liners: [],
    end_with_newline: false,
    preserve_newlines: true,
    max_preserve_newlines: 1,
    content_unformatted: ["pre"],
    // Dictionary markup is almost all inline; keep <b>/<i>/<a> on one line.
    inline: [
      "a",
      "abbr",
      "b",
      "br",
      "em",
      "i",
      "small",
      "span",
      "strong",
      "sub",
      "sup",
      "u",
    ],
  };

  function compactHtml(source) {
    return (source || "")
      .replace(/\t/g, " ")
      .split(/\r\n|\r|\n/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean)
      .join(" ")
      .replace(/ {2,}/g, " ")
      .trim();
  }

  function wrapLineLength(cm) {
    var wrap = cm.getWrapperElement();
    var lines = wrap.querySelector(".CodeMirror-lines");
    var gutters = wrap.querySelector(".CodeMirror-gutters");
    var gutterW = gutters ? gutters.offsetWidth : 0;
    var width = lines ? lines.clientWidth : wrap.clientWidth - gutterW;
    var ch = cm.defaultCharWidth();
    if (!ch || ch < 4) {
      ch = 8;
    }
    // Leave a small gutter so the last glyph is not clipped by the scrollbar.
    return Math.max(20, Math.floor(width / ch) - 2);
  }

  function beautifyHtml(source, wrapLen) {
    if (typeof html_beautify !== "function") {
      return source;
    }
    var text = (source || "").replace(/^\uFEFF/, "");
    if (!text.trim()) {
      return text;
    }
    var opts = {};
    Object.keys(BEAUTIFY_OPTIONS).forEach(function (key) {
      opts[key] = BEAUTIFY_OPTIONS[key];
    });
    opts.wrap_line_length = wrapLen || 0;
    return html_beautify(text, opts);
  }

  function formatEditor(cm) {
    var wrapLen = wrapLineLength(cm);
    var formatted = beautifyHtml(compactHtml(cm.getValue()), wrapLen);
    if (formatted === cm.getValue()) {
      return;
    }
    var cursor = cm.getCursor();
    cm.setValue(formatted);
    cm.setCursor(cursor);
    cm.save();
  }

  function addToolbar(wrapper, cm) {
    if (wrapper.previousElementSibling &&
        wrapper.previousElementSibling.classList.contains("article-html-toolbar")) {
      return;
    }
    var bar = document.createElement("div");
    bar.className = "article-html-toolbar";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "button article-html-format";
    btn.textContent = "Форматировать HTML";
    btn.addEventListener("click", function () {
      formatEditor(cm);
      cm.focus();
    });
    bar.appendChild(btn);
    wrapper.parentNode.insertBefore(bar, wrapper);
  }

  function watchWidth(cm) {
    var wrap = cm.getWrapperElement();
    var timer = null;
    var last = wrapLineLength(cm);
    function onResize() {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var next = wrapLineLength(cm);
        if (Math.abs(next - last) < 2) {
          return;
        }
        last = next;
        formatEditor(cm);
      }, 150);
    }
    if (typeof ResizeObserver === "function") {
      var ro = new ResizeObserver(onResize);
      ro.observe(wrap);
    } else {
      window.addEventListener("resize", onResize);
    }
  }

  function initEditor(textarea) {
    if (!textarea || textarea.closest(".empty-form")) {
      return;
    }
    if (textarea.dataset.cmReady || typeof CodeMirror === "undefined") {
      return;
    }
    textarea.dataset.cmReady = "1";
    var cm = CodeMirror.fromTextArea(textarea, {
      mode: "htmlmixed",
      lineNumbers: true,
      lineWrapping: true,
      indentUnit: 2,
      tabSize: 2,
      viewportMargin: Infinity,
    });
    cm.setSize("100%", null);
    cm.on("change", function () {
      cm.save();
    });
    textarea._cm = cm;
    if (textarea.form && !textarea.form.dataset.articleHtmlCompact) {
      textarea.form.dataset.articleHtmlCompact = "1";
      textarea.form.addEventListener("submit", function () {
        textarea.form
          .querySelectorAll("textarea.article-html-source")
          .forEach(function (ta) {
            if (ta.closest(".empty-form")) {
              return;
            }
            if (ta._cm) {
              ta._cm.save();
            }
            ta.value = compactHtml(ta.value);
          });
      });
    }
    addToolbar(cm.getWrapperElement(), cm);
    requestAnimationFrame(function () {
      formatEditor(cm);
      watchWidth(cm);
    });
  }

  function initAll(root) {
    (root || document)
      .querySelectorAll("textarea.article-html-source")
      .forEach(initEditor);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initAll(document);
    if (window.django && django.jQuery) {
      django.jQuery(document).on("formset:added", function (_event, $row) {
        var row = $row && $row.jquery ? $row[0] : $row;
        initAll(row || document);
      });
    }
  });
})();
