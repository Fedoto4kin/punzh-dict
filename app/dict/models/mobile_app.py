"""Stats for the Android APK offered from the site."""

from django.db import models
from django.db.models import F


class ApkDownloadStat(models.Model):
    """Singleton row (pk=1): how many times the tracked APK link was hit."""

    count = models.PositiveIntegerField(default=0, verbose_name="Скачиваний")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Счётчик скачиваний APK"
        verbose_name_plural = "Счётчик скачиваний APK"

    def __str__(self):
        return f"APK downloads: {self.count}"

    @classmethod
    def get_solo(cls) -> "ApkDownloadStat":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def increment(cls) -> None:
        cls.get_solo()
        cls.objects.filter(pk=1).update(count=F("count") + 1)

    @classmethod
    def set_count(cls, value: int) -> "ApkDownloadStat":
        obj = cls.get_solo()
        obj.count = max(0, int(value))
        obj.save(update_fields=["count", "updated_at"])
        return obj
