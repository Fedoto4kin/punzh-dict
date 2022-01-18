from django.urls import reverse
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .services import gen_word_variants, create_ngram, KRL_ABC, normalization


class Source(models.Model):

    title = models.CharField(max_length=255,
                             verbose_name='Название источника')
    description = models.TextField(default='',
                                   blank=True,
                                   null=True,
                                   verbose_name='Описание')
    css = models.CharField(max_length=255)

class Article(models.Model):

    word = models.CharField(unique=True, max_length=255, db_index=True, verbose_name='Слово (ориг.)')
    word_normalized = models.CharField(
        default=None,
        blank=True,
        null=True,
        max_length=255,
        db_index=True,
        verbose_name='Коррекция заголовка')

    first_letter = models.CharField(max_length=1, db_index=True)
    first_trigram = models.CharField(max_length=3)
    article_html = models.TextField(default='', verbose_name='Словарная статья (html)')
    source_id = models.ForeignKey(Source,
                                  null=True,
                                  on_delete=models.SET_NULL
                                  )
    source_detalization = models.CharField(
        default=None,
        blank=True,
        null=True,
        max_length=255,
        verbose_name='Уточнение источника')

    @staticmethod
    def get_krl_abc():
        abc = ''
        for l in KRL_ABC.replace('Ü', 'Y'):
            abc += l + l.lower()
        return abc

    def get_admin_url(self):
        content_type = ContentType.objects.get_for_model(self.__class__)
        return reverse("admin:%s_%s_change" % (content_type.app_label, content_type.model), args=(self.id,))

    def __str__(self):
        return normalization(self.word)

    def make_ngram(self, n=3):
        return create_ngram(self.word, n)

    def word_index(self):
        if self.word_normalized:
            return gen_word_variants(self.word_normalized)
        else:
            return gen_word_variants(self.word)

    def save(self, *args, **kwargs):

        self.first_letter = self.word[0].upper()
        super(Article, self).save(*args, **kwargs)

        ArticleIndexWord.objects.filter(article=self).delete()
        indx = (ArticleIndexWord(article=self, word=var) for var in self.word_index())
        ArticleIndexWord.objects.bulk_create(indx)

    class Meta:
        verbose_name = 'Слово'
        verbose_name_plural = 'Слова'
        ordering = ['-id']


class ArticleIndexWord(models.Model):

    word = models.CharField(max_length=255, default=None, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE)

    def __str__(self):
        return self.word

    class Meta:
        unique_together = ('word', 'article',)


class ArticleIndexTranslate(models.Model):

    rus_word = models.CharField(max_length=255,
                                default=None,
                                blank=True,
                                null=True,
                                verbose_name='Перевод')
    article = models.ForeignKey(Article, on_delete=models.CASCADE)

    def __str__(self):
        return self.rus_word

    class Meta:
        unique_together = ('rus_word', 'article',)
        verbose_name = 'Перевод'
        verbose_name_plural = 'Переводы'
        ordering = ['rus_word']
