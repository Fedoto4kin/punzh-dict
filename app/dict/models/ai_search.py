"""Ephemeral AI search jobs (async parse + retrieval). Not dictionary content."""

import uuid

from django.db import models
from django.utils import timezone


class AiSearchJob(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = (
        (STATUS_QUEUED, "queued"),
        (STATUS_RUNNING, "running"),
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
