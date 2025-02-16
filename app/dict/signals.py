from django.contrib.postgres.search import SearchVector
from django.db.models.signals import post_save
from django.dispatch import receiver
from dict.models import ArticleIndexTranslate

@receiver(post_save, sender=ArticleIndexTranslate)
def update_search_vector(sender, instance, **kwargs):
    ArticleIndexTranslate.objects.filter(pk=instance.pk).update(
        search_vector=SearchVector('rus_word')
    )
