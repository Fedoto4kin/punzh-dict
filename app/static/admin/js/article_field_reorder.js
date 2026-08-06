'use strict';

// Django admin renders every fieldset first and every inline group afterwards,
// so inlines cannot be interleaved with form fields on the server side.
//
// The Article change form defines two fieldsets:
//   - fieldset.field-head : Заголовок / Коррекция / Слово (ориг.)
//   - fieldset.field-tail : Словарная статья (html) / (rendered) / Источник / Уточнение
//
// After load we move the ".field-tail" fieldset so it sits right after the
// 4th inline group ("На эту статью указывают"), producing the target order:
//
//   Заголовок (в норм. орф.)
//   Коррекция заголовка
//   Слово (ориг.)
//   Переводы                      (inline 0)
//   Пометы (служебные отметки)    (inline 1)
//   Смотрите также                (inline 2)
//   На эту статью указывают       (inline 3)
//   Словарная статья (html)       <- tail fieldset moved here
//   Словарная статья
//   Источник
//   Уточнение источника
//   Дополнения                    (inline 4, trails at the very bottom)

document.addEventListener('DOMContentLoaded', function () {
    var tail = document.querySelector('fieldset.field-tail');
    if (!tail) {
        return;
    }

    // Top-level inline wrappers, in the same order as ModelAdmin.inlines.
    var groups = document.querySelectorAll('.inline-group');
    if (groups.length < 4) {
        return;
    }

    var anchor = groups[3]; // "На эту статью указывают"
    anchor.parentNode.insertBefore(tail, anchor.nextSibling);
});
