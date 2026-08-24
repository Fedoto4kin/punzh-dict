'use strict';

// Django admin renders every fieldset first and every inline group afterwards,
// so inlines cannot be interleaved with form fields on the server side.
//
// The Article change form defines two fieldsets:
//   - fieldset.field-head : Заголовок / Коррекция / Слово (ориг.)
//   - fieldset.field-tail : Словарная статья (html) / (rendered) / Источник / Уточнение
//
// After load we move ".field-tail" to sit right after the reverse-links
// inline ("На эту статью указывают", #links_to-group). Semantic-field inline
// is absent on add, so we must not rely on a fixed inline index.
//
// Target order (change form; on add the ontology block is omitted):
//
//   Заголовок (в норм. орф.)
//   Коррекция заголовка
//   Слово (ориг.)
//   Переводы
//   Пометы (служебные отметки)
//   Смысловые поля (онтология)    (change only)
//   Смотрите также
//   На эту статью указывают
//   Словарная статья (html)       <- tail fieldset moved here
//   Словарная статья
//   Источник
//   Уточнение источника
//   Дополнения                    (trails at the very bottom)

document.addEventListener('DOMContentLoaded', function () {
    var tail = document.querySelector('fieldset.field-tail');
    if (!tail) {
        return;
    }

    var anchor = document.getElementById('links_to-group');
    if (!anchor) {
        var groups = document.querySelectorAll('.inline-group');
        if (groups.length < 4) {
            return;
        }
        // Fallback: last editorial inline before additions.
        anchor = groups[groups.length - 2];
    }

    anchor.parentNode.insertBefore(tail, anchor.nextSibling);
});
