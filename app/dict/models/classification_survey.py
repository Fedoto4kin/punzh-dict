"""Crowdsourced classification answers — control channel, not expert gold."""

from django.db import models
from django.utils import timezone


class ClassificationSurveyResponse(models.Model):
    """One visitor answer for one article (control / non-expert)."""

    DECISION_FIELDS = "fields"
    DECISION_NO_FIELD = "no_field"
    DECISION_INSUFFICIENT = "insufficient"
    DECISION_CHOICES = (
        (DECISION_FIELDS, "fields"),
        (DECISION_NO_FIELD, "no_field"),
        (DECISION_INSUFFICIENT, "insufficient"),
    )

    respondent_key = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Anonymous uuid from cookie; no personal data.",
    )
    article = models.ForeignKey(
        "dict.Article",
        on_delete=models.CASCADE,
        related_name="survey_responses",
    )
    decision = models.CharField(max_length=16, choices=DECISION_CHOICES)
    fields = models.JSONField(
        default=list,
        blank=True,
        help_text="List of SemanticField.name (0–3).",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Ответ опроса классификации"
        verbose_name_plural = "Ответы опроса классификации"
        unique_together = ("respondent_key", "article")
        indexes = [
            models.Index(fields=["article", "created_at"]),
        ]

    def __str__(self):
        return f"{self.respondent_key[:8]}… → {self.article_id} ({self.decision})"
