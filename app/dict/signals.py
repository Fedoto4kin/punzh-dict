from django.contrib.postgres.search import SearchVector
from django.core.signals import request_started
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from dict.models import ArticleIndexTranslate, Tag
from dict.tag_highlight import clear_italic_tag_cache


@receiver(post_save, sender=ArticleIndexTranslate)
def update_search_vector(sender, instance, **kwargs):
    ArticleIndexTranslate.objects.filter(pk=instance.pk).update(
        search_vector=SearchVector("rus_word", config="simple")
    )


@receiver(post_save, sender=Tag)
@receiver(post_delete, sender=Tag)
def clear_tag_highlight_cache_on_tag_change(**kwargs):
    clear_italic_tag_cache()


@receiver(request_started)
def clear_tag_highlight_cache_on_request(**kwargs):
    # Fresh Tag set once per request; cards on the page share thread-local cache.
    clear_italic_tag_cache()
