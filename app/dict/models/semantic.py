from django.db import models

__all__ = ["SemanticField", "ArticleSemanticField", "ArticleKeyword"]


class SemanticField(models.Model):
    """
    Справочник смысловых полей (ось семантической классификации).
    Аналог Tag, но отдельная ось: НЕ пометы (регистр/область), а «о чём слово
    по смыслу». Заполняется из онтологии, построенной оффлайн (см.
    CONCEPT_ai_search.md). Используется веткой AI-поиска, НЕ основным поиском.
    """

    name = models.CharField(
        max_length=255,
        db_index=True,
        unique=True,
        verbose_name="Смысловое поле",
    )
    definition = models.TextField(
        default="",
        blank=True,
        verbose_name="Определение",
    )
    # Задел под дерево (под-классификации). Пока плоско: parent=None у всех.
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.SET_NULL,
        verbose_name="Родительское поле",
    )
    sorting = models.IntegerField(
        db_index=True,
        null=True,
        blank=True,
        verbose_name="Сортировка",
    )

    class Meta:
        ordering = ["sorting", "name"]
        verbose_name = "Смысловое поле"
        verbose_name_plural = "Смысловые поля"

    def __str__(self):
        return self.name


class ArticleSemanticField(models.Model):
    """
    Связь статья ↔ смысловое поле (аналог ArticleIndexTag).
    Многозначность допустима: у статьи может быть несколько полей.
    is_primary — смысл леммы по переводам (не из иллюстраций); не больше
    одного на статью. Выбирается отдельным LLM-проходом, не классификатором.
    """

    article = models.ForeignKey(
        "Article",
        on_delete=models.CASCADE,
        related_name="semantic_assignments",
    )
    field = models.ForeignKey(
        SemanticField,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Смысловое поле",
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name="Главное",
    )

    def __str__(self):
        return self.field.name

    class Meta:
        unique_together = ("article", "field")
        constraints = [
            models.UniqueConstraint(
                fields=["article"],
                condition=models.Q(is_primary=True),
                name="dict_asf_one_primary_per_article",
            ),
        ]
        verbose_name = "Смысловое поле статьи"
        verbose_name_plural = "Смысловые поля статей"


class ArticleKeyword(models.Model):
    """
    Русское ключевое слово статьи, извлечённое LLM-классификатором из ВСЕЙ
    карточки (перевод + иллюстрации + толкование). Вскрывает лексику
    иллюстраций, невидимую для поиска по переводам (`ArticleIndexTranslate`).
    См. BACKLOG_keywords_search.md.

    Роли: (1) лексический поиск точного слова; (2) смысловой переход
    транзитивно через статью → её SemanticField → соседи. Прямая связь
    keyword↔поле НЕ нужна.

    Заливается СЫРЬЁМ (без чистки от шума). Программная чистка (стоп-слова,
    POS) — отдельная задача этапа поиска по keywords.
    """

    article = models.ForeignKey("Article", on_delete=models.CASCADE)
    word = models.CharField(
        max_length=255, db_index=True, verbose_name="Ключевое слово"
    )

    def __str__(self):
        return self.word

    class Meta:
        unique_together = ("article", "word")
        verbose_name = "Ключевое слово статьи"
        verbose_name_plural = "Ключевые слова статей"
