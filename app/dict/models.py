from django.db import models

from .services import gen_word_variants, create_ngram, KRL_ABC


class Article(models.Model):

    word = models.CharField(unique=True, max_length=255, db_index=True)
    word_normalized = models.CharField(default=None, blank=True, null=True, max_length=255, db_index=True)

    first_letter = models.CharField(max_length=1, db_index=True)
    first_trigram = models.CharField(max_length=3)
    article_html = models.TextField(default='')

    @staticmethod
    def get_krl_abc():
        abc = ''
        for l in KRL_ABC.replace('Ü', 'Y'):
            abc += l + l.lower()
        return abc

    def __str__(self):
        return self.word

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
        ordering = ['-id']


class ArticleIndexWord(models.Model):

    word = models.CharField(max_length=255, default=None, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE)

    def __str__(self):
        return self.word

    class Meta:
        unique_together = ('word', 'article',)


class ArticleIndexSemantic(models.Model):

    word = models.CharField(max_length=255, default=None, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE)

    def __str__(self):
        return self.word

    class Meta:
        unique_together = ('word', 'article',)


class ArticleIndexContext(models.Model):

    word = models.CharField(max_length=255, default=None, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE)

    def __str__(self):
        return self.word

    class Meta:
        unique_together = ('word', 'article',)