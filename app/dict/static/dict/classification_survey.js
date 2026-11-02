(function () {
  var STORAGE_KEY = "cls_survey_v1";
  var RESP_KEY = "cls_survey_respondent_v1";

  function $(id) {
    return document.getElementById(id);
  }

  function csrfToken() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "r-" + String(Date.now()) + "-" + Math.random().toString(16).slice(2);
  }

  function getRespondentKey() {
    try {
      var k = localStorage.getItem(RESP_KEY);
      if (k && k.length >= 8) return k;
      k = uuid();
      localStorage.setItem(RESP_KEY, k);
      return k;
    } catch (e) {
      return uuid();
    }
  }

  function alreadyDone() {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch (e) {
      return false;
    }
  }

  function markDone() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch (e) {}
  }

  function show(el) {
    if (el) el.classList.remove("d-none");
  }
  function hide(el) {
    if (el) el.classList.add("d-none");
  }

  function scrollSurveyTop() {
    var modal = $("clsSurveyModal");
    if (!modal) return;
    var body = modal.querySelector(".modal-body");
    if (body) body.scrollTop = 0;
    var dialog = modal.querySelector(".modal-dialog-scrollable");
    if (dialog) dialog.scrollTop = 0;
    // Bootstrap 4 puts overflow on .modal-body inside scrollable dialog.
    var content = modal.querySelector(".modal-content");
    if (content) content.scrollTop = 0;
  }

  function setError(msg) {
    var box = $("clsSurveyError");
    if (!box) return;
    if (!msg) {
      hide(box);
      box.textContent = "";
      return;
    }
    box.textContent = msg;
    show(box);
  }

  var state = {
    fields: [],
    articles: [],
    index: 0,
    current: { decision: "", fields: [] },
    saving: false,
    comparisons: [],
  };

  function currentArticle() {
    return state.articles[state.index] || null;
  }

  function isLast() {
    return state.index >= state.articles.length - 1;
  }

  function updateNextEnabled() {
    var btn = $("clsSurveyNext");
    if (!btn) return;
    show(btn);
    btn.disabled = state.saving || !state.current.decision;
    btn.className = "btn btn-success mt-3";
    btn.innerHTML =
      '<i class="fas fa-check" aria-hidden="true"></i>' +
      '<span class="sr-only">Ответить</span>';
    btn.setAttribute("aria-label", "Ответить");
    btn.setAttribute("title", "Ответить");
  }

  function renderCurrentCard() {
    var host = $("clsSurveyCards");
    var qhost = $("clsSurveyQuestion");
    var progress = $("clsSurveyProgress");
    var instr = $("clsSurveyInstruction");
    var art = currentArticle();
    if (!host || !art) return;

    if (progress) {
      progress.textContent =
        "Статья " + (state.index + 1) + " из " + state.articles.length;
    }
    if (instr) {
      if (state.index === 0) show(instr);
      else hide(instr);
    }

    host.innerHTML = "";
    if (qhost) qhost.innerHTML = "";
    state.current = { decision: "", fields: [] };

    var qblock = document.createElement("div");
    qblock.className = "mb-0";
    qblock.dataset.articleId = String(art.article_id);

    var title = document.createElement("h6");
    title.className = "mb-1";
    var wordText = art.word || "#" + art.article_id;
    var href =
      art.url ||
      "/search/" + encodeURIComponent(art.word || String(art.article_id));
    var link = document.createElement("a");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "text-dark";
    link.title = "Открыть статью в новой вкладке";
    link.appendChild(document.createTextNode(wordText + " "));
    var ext = document.createElement("i");
    ext.className = "fas fa-external-link-alt small text-muted";
    ext.setAttribute("aria-hidden", "true");
    link.appendChild(ext);
    title.appendChild(link);
    qblock.appendChild(title);

    var tr = document.createElement("p");
    tr.className = "mb-1 small";
    tr.innerHTML =
      "<strong>Переводы:</strong> " +
      (art.translations && art.translations.length
        ? art.translations.join(" · ")
        : "—");
    qblock.appendChild(tr);

    if (art.illustrations_ru && art.illustrations_ru.length) {
      var ill = document.createElement("p");
      ill.className = "mb-0 small text-muted";
      ill.innerHTML =
        "<strong>Примеры:</strong> " +
        art.illustrations_ru.slice(0, 8).join(" · ");
      qblock.appendChild(ill);
    }
    if (qhost) qhost.appendChild(qblock);

    var card = document.createElement("div");
    card.className = "mb-2";
    card.dataset.articleId = String(art.article_id);

    var opts = document.createElement("div");
    opts.className = "mb-2";
    state.fields.forEach(function (f) {
      var id =
        "cls-f-" +
        art.article_id +
        "-" +
        f.name.replace(/[^a-zA-Zа-яА-Я0-9]+/g, "_");
      var wrap = document.createElement("div");
      wrap.className = "form-check";
      var input = document.createElement("input");
      input.type = "checkbox";
      input.className = "form-check-input cls-field-cb";
      input.id = id;
      input.value = f.name;
      input.dataset.articleId = String(art.article_id);
      input.addEventListener("change", onFieldChange);
      var label = document.createElement("label");
      label.className = "form-check-label small";
      label.htmlFor = id;
      label.textContent = f.name;
      label.title = f.definition || "";
      wrap.appendChild(input);
      wrap.appendChild(label);
      opts.appendChild(wrap);
    });
    card.appendChild(opts);

    var noneId = "cls-none-" + art.article_id;
    var noneWrap = document.createElement("div");
    noneWrap.className = "form-check mt-1";
    var none = document.createElement("input");
    none.type = "radio";
    none.name = "cls-dec-" + art.article_id;
    none.className = "form-check-input";
    none.id = noneId;
    none.value = "no_field";
    none.dataset.articleId = String(art.article_id);
    none.addEventListener("change", onNoneChange);
    var noneLab = document.createElement("label");
    noneLab.className = "form-check-label small";
    noneLab.htmlFor = noneId;
    noneLab.textContent = "Ни одно поле не подходит";
    noneWrap.appendChild(none);
    noneWrap.appendChild(noneLab);
    card.appendChild(noneWrap);

    var skipId = "cls-skip-" + art.article_id;
    var skipWrap = document.createElement("div");
    skipWrap.className = "form-check";
    var skip = document.createElement("input");
    skip.type = "radio";
    skip.name = "cls-dec-" + art.article_id;
    skip.className = "form-check-input";
    skip.id = skipId;
    skip.value = "insufficient";
    skip.dataset.articleId = String(art.article_id);
    skip.addEventListener("change", onNoneChange);
    var skipLab = document.createElement("label");
    skipLab.className = "form-check-label small";
    skipLab.htmlFor = skipId;
    skipLab.textContent = "Недостаточно информации";
    skipWrap.appendChild(skip);
    skipWrap.appendChild(skipLab);
    card.appendChild(skipWrap);

    host.appendChild(card);
    updateNextEnabled();
  }

  function selectedFields(articleId) {
    var nodes = document.querySelectorAll(
      '.cls-field-cb[data-article-id="' + articleId + '"]:checked'
    );
    var out = [];
    nodes.forEach(function (n) {
      out.push(n.value);
    });
    return out;
  }

  function onFieldChange(ev) {
    var aid = ev.target.dataset.articleId;
    var fields = selectedFields(aid);
    if (fields.length > 3) {
      ev.target.checked = false;
      setError("Не больше трёх полей на одну статью.");
      fields = selectedFields(aid);
    } else {
      setError("");
    }
    if (fields.length) {
      document
        .querySelectorAll('input[name="cls-dec-' + aid + '"]')
        .forEach(function (r) {
          r.checked = false;
        });
      state.current = { decision: "fields", fields: fields };
    } else {
      state.current = { decision: "", fields: [] };
    }
    updateNextEnabled();
  }

  function onNoneChange(ev) {
    var aid = ev.target.dataset.articleId;
    if (!ev.target.checked) return;
    document
      .querySelectorAll('.cls-field-cb[data-article-id="' + aid + '"]')
      .forEach(function (cb) {
        cb.checked = false;
      });
    state.current = { decision: ev.target.value, fields: [] };
    setError("");
    updateNextEnabled();
  }

  function openModal() {
    if (window.jQuery) {
      jQuery("#clsSurveyModal").modal("show");
    }
  }

  function closeModal() {
    if (window.jQuery) {
      jQuery("#clsSurveyModal").modal("hide");
    }
  }

  function setInviteTitle() {
    var title = $("clsSurveyTitle");
    if (title) {
      title.innerHTML =
        '<i class="fas fa-flask" aria-hidden="true"></i> Помогите развитию словаря';
    }
  }

  function resetToInvite() {
    setInviteTitle();
    hide($("clsSurveyForm"));
    hide($("clsSurveyThanks"));
    show($("clsSurveyInvite"));
    setError("");
  }

  function openSurveyPrompt() {
    // Flask / «Исследовать вместе»: skip consent (invite is for first auto-prompt only).
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
    setInviteTitle();
    hide($("clsSurveyThanks"));
    openModal();
    loadTask();
  }

  function humanAnswerLabel(decision, fields) {
    if (decision === "fields" && fields && fields.length) {
      return fields.join(", ");
    }
    if (decision === "no_field") return "Ни одно поле не подходит";
    if (decision === "insufficient") return "Недостаточно информации";
    return "—";
  }

  function modelAnswerLabel(modelFields) {
    if (modelFields && modelFields.length) return modelFields.join(", ");
    return "не отнесла ни к одному полю";
  }

  function normField(name) {
    return String(name || "")
      .replace(/\u00a0/g, " ")
      .trim()
      .normalize("NFC");
  }

  function sortedUnique(arr) {
    var seen = {};
    var out = [];
    (arr || []).forEach(function (x) {
      x = normField(x);
      if (!x || seen[x]) return;
      seen[x] = true;
      out.push(x);
    });
    out.sort();
    return out;
  }

  function setsEqual(a, b) {
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }

  function sharedFields(a, b) {
    var setB = {};
    (b || []).forEach(function (x) {
      setB[normField(x)] = true;
    });
    return (a || []).filter(function (x) {
      return setB[normField(x)];
    });
  }

  function formatFieldList(fields, matchSet) {
    if (!fields || !fields.length) return "";
    return fields
      .map(function (name) {
        var raw = normField(name);
        var safe = escapeHtml(raw);
        if (matchSet[raw]) {
          return '<mark class="cls-field-match">' + safe + "</mark>";
        }
        return safe;
      })
      .join(", ");
  }

  function recordComparison(modelFields) {
    var art = currentArticle();
    if (!art) return;
    var decision = state.current.decision;
    var humanFields =
      decision === "fields" ? sortedUnique(state.current.fields || []) : [];
    var model = sortedUnique(modelFields || []);
    var shared = sharedFields(humanFields, model);
    var fullMatch = false;
    if (decision === "fields") {
      fullMatch = humanFields.length > 0 && setsEqual(humanFields, model);
    } else if (decision === "no_field") {
      fullMatch = model.length === 0;
    }
    state.comparisons.push({
      word: art.word || "#" + art.article_id,
      url: art.url || "",
      decision: decision,
      humanFields: humanFields,
      modelFields: model,
      humanLabel: humanAnswerLabel(decision, humanFields),
      modelLabel: modelAnswerLabel(model),
      fullMatch: fullMatch,
      shared: shared,
    });
  }

  function renderFinalComparison() {
    var host = $("clsSurveyCompare");
    if (!host) return;
    host.innerHTML = "";
    if (!state.comparisons.length) return;

    var intro = document.createElement("p");
    intro.className = "small mb-2";
    intro.textContent =
      "Как вы ответили и как разметила автоматическая классификация 🤖.";
    host.appendChild(intro);

    state.comparisons.forEach(function (row, i) {
      // Recompute at render time (defensive against stale/odd strings).
      var humanFields = sortedUnique(row.humanFields || []);
      var modelFields = sortedUnique(row.modelFields || []);
      var shared = sharedFields(humanFields, modelFields);
      var fullMatch = false;
      if (row.decision === "fields") {
        fullMatch = humanFields.length > 0 && setsEqual(humanFields, modelFields);
      } else if (row.decision === "no_field") {
        fullMatch = modelFields.length === 0;
      }

      var card = document.createElement("div");
      card.className =
        "cls-final-compare mb-2" +
        (fullMatch ? " cls-final-compare-match" : "");

      var head = document.createElement("div");
      head.className = "font-weight-bold mb-1";
      if (row.url) {
        var a = document.createElement("a");
        a.href = row.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = i + 1 + ". " + row.word;
        head.appendChild(a);
      } else {
        head.textContent = i + 1 + ". " + row.word;
      }
      card.appendChild(head);

      var matchSet = {};
      shared.forEach(function (n) {
        matchSet[n] = true;
      });

      var you = document.createElement("div");
      you.className = "small";
      var youBody;
      if (row.decision === "fields" && humanFields.length) {
        youBody = formatFieldList(humanFields, matchSet);
      } else if (fullMatch && row.decision === "no_field") {
        youBody =
          '<mark class="cls-field-match">' +
          escapeHtml(row.humanLabel) +
          "</mark>";
      } else {
        youBody = escapeHtml(row.humanLabel);
      }
      you.innerHTML =
        '<span class="cls-compare-human">Вы:</span> ' + youBody;
      card.appendChild(you);

      var bot = document.createElement("div");
      bot.className = "small";
      var botBody;
      if (modelFields.length) {
        botBody = formatFieldList(modelFields, matchSet);
      } else if (fullMatch && row.decision === "no_field") {
        botBody =
          '<mark class="cls-field-match">' +
          escapeHtml(row.modelLabel) +
          "</mark>";
      } else {
        botBody = escapeHtml(row.modelLabel);
      }
      bot.innerHTML =
        '<span class="cls-compare-model">🤖 :</span> ' + botBody;
      card.appendChild(bot);

      host.appendChild(card);
    });

    var note = document.createElement("p");
    note.className = "small text-muted mb-0 mt-2";
    note.textContent = "Совпадения выделены зелёным.";
    host.appendChild(note);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function finishSurvey() {
    markDone();
    var title = $("clsSurveyTitle");
    if (title) {
      title.textContent = "Спасибо, что стали частью исследования!";
    }
    renderFinalComparison();
    hide($("clsSurveyForm"));
    show($("clsSurveyThanks"));
    scrollSurveyTop();
  }

  function saveCurrentAnswer() {
    var art = currentArticle();
    if (!art || !state.current.decision) {
      return Promise.reject(new Error("Сначала отметьте ответ"));
    }
    var modal = $("clsSurveyModal");
    var url = modal.getAttribute("data-submit-url");
    var payload = {
      key: getRespondentKey(),
      answers: [
        {
          article_id: art.article_id,
          decision: state.current.decision,
          fields: state.current.fields || [],
        },
      ],
    };
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) {
          throw new Error(
            (data && (data.detail || data.error)) || "Ошибка сохранения"
          );
        }
        return data;
      });
    });
  }

  function onNext() {
    if (state.saving || !state.current.decision) return;
    state.saving = true;
    updateNextEnabled();
    setError("");
    saveCurrentAnswer()
      .then(function (data) {
        recordComparison((data && data.model_fields) || []);
        state.saving = false;
        if (isLast()) {
          finishSurvey();
          return;
        }
        state.index += 1;
        renderCurrentCard();
        scrollSurveyTop();
      })
      .catch(function (err) {
        state.saving = false;
        updateNextEnabled();
        setError(err.message || String(err));
      });
  }

  function loadTask() {
    var modal = $("clsSurveyModal");
    var url = modal.getAttribute("data-task-url");
    setError("");
    hide($("clsSurveyInvite"));
    show($("clsSurveyForm"));
    $("clsSurveyCards").innerHTML = "<p class='text-muted'>Загрузка…</p>";
    var btn = $("clsSurveyNext");
    if (btn) btn.disabled = true;
    fetch(url + "?key=" + encodeURIComponent(getRespondentKey()), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          throw new Error(
            (res.data && res.data.error) || "Не удалось загрузить задания"
          );
        }
        state.fields = res.data.fields || [];
        state.articles = res.data.articles || [];
        state.index = 0;
        state.comparisons = [];
        if (!state.articles.length) {
          throw new Error("Нет доступных статей для опроса");
        }
        renderCurrentCard();
      })
      .catch(function (err) {
        hide($("clsSurveyForm"));
        show($("clsSurveyInvite"));
        setError(err.message || String(err));
      });
  }

  function init() {
    var modal = $("clsSurveyModal");
    if (!modal) return;

    var yes = $("clsSurveyYes");
    var no = $("clsSurveyNo");
    if (yes) yes.addEventListener("click", loadTask);
    if (no) {
      no.addEventListener("click", function () {
        markDone();
        closeModal();
      });
    }
    var next = $("clsSurveyNext");
    if (next) next.addEventListener("click", onNext);

    document.querySelectorAll("[data-cls-survey-open]").forEach(function (el) {
      el.addEventListener("click", function (ev) {
        ev.preventDefault();
        openSurveyPrompt();
      });
    });

    if (window.jQuery) {
      jQuery(modal).on("hide.bs.modal", function () {
        markDone();
      });
    }

    if (!alreadyDone()) {
      setTimeout(openModal, 800);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
