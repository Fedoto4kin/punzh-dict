"""Ephemeral AI search jobs + durable alpha logs / feedback."""

import uuid

from django.db import models
from django.utils import timezone


class AiSearchJob(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_RANKING = "ranking"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_QUEUED, "queued"),
        (STATUS_RUNNING, "running"),
        (STATUS_RANKING, "ranking"),
        (STATUS_DONE, "done"),
        (STATUS_ERROR, "error"),
        (STATUS_EXPIRED, "expired"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.CharField(max_length=300)
    sort = models.CharField(max_length=16, default="relevance", blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True
    )
    parsed = models.JSONField(null=True, blank=True)
    groups = models.JSONField(null=True, blank=True)
    fallback_count = models.IntegerField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True, default="")
    client_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "AI search job"
        verbose_name_plural = "AI search jobs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.id} [{self.status}] {self.query[:40]}"


class AiSearchLog(models.Model):
    """Durable snapshot of one AI search (alpha). Survives job TTL."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_id = models.UUIDField(null=True, blank=True, db_index=True)
    query_raw = models.CharField(max_length=300)
    parsed_json = models.JSONField(default=dict, blank=True)
    groups_json = models.JSONField(default=list, blank=True)
    display = models.CharField(max_length=500, blank=True, default="")
    parse_ok = models.BooleanField(default=False)
    ok = models.BooleanField(default=False)
    error = models.CharField(max_length=200, blank=True, default="")
    fallback_count = models.IntegerField(null=True, blank=True)
    model_query = models.CharField(max_length=120, blank=True, default="")
    prompt_version = models.CharField(max_length=32, blank=True, default="")
    latency_ms = models.IntegerField(null=True, blank=True)
    session_key = models.CharField(max_length=64, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "AI search log"
        verbose_name_plural = "AI search logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.id} {self.query_raw[:40]}"


class AiSearchFeedback(models.Model):
    """Optional thumbs on a log. Both up and down are stored."""

    VOTE_UP = "up"
    VOTE_DOWN = "down"
    VOTE_CHOICES = (
        (VOTE_UP, "up"),
        (VOTE_DOWN, "down"),
    )
    REASON_PARSE_WRONG = "parse_wrong"
    REASON_BAD_HITS = "bad_hits"
    REASON_TOO_FEW = "too_few"
    REASON_TOO_MANY = "too_many"
    REASON_CHOICES = (
        REASON_PARSE_WRONG,
        REASON_BAD_HITS,
        REASON_TOO_FEW,
        REASON_TOO_MANY,
    )

    log = models.OneToOneField(
        AiSearchLog,
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    vote = models.CharField(max_length=8, choices=VOTE_CHOICES)
    reasons = models.JSONField(default=list, blank=True)
    comment = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI search feedback"
        verbose_name_plural = "AI search feedback"

    def __str__(self):
        return f"{self.vote} on {self.log_id}"
