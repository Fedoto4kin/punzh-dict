from django.contrib import admin

from dict.models import Tag


@admin.register(Tag)
class TagAdm(admin.ModelAdmin):
    list_display = ("id", "name", "tag", "type")
    list_filter = ("type",)
    search_fields = ("^name", "^tag")
    ordering = ("type", "sorting", "name")
