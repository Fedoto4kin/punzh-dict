from django.db import models

from .services import gen_word_variants


KRL_ABC = 'ABCČDEFGHIJKLMNOPRSŠZŽTUVWÜÄÖ'


class Article(models.Model):

    word = models.CharField(unique=True, max_length=255, db_index=True)

    first_letter = models.CharField(max_length=1, db_index=True)
    first_trigram = models.CharField(max_length=3)
    article_html = models.TextField(default='')

    @staticmethod
    def get_krl_abc():
        abc = ''
        for l in KRL_ABC:
            abc += l + l.lower()
        return abc

    def __str__(self):
        return self.word

    def make_trigram(self):
        self.first_trigram = ''.join(
            list(
                filter(
                    lambda x: x in self.get_krl_abc(),
                    self.word.split()[0].replace('i̮a', 'ua')
                )
            )
        )[:3].lower()

    def word_index(self):
        return gen_word_variants(self.word)

    def get_index(self):

        print(self.word)
        print(self.variants())
        print('---------------------')

    def save(self, *args, **kwargs):

        self.first_letter = self.word[0].upper()
        self.make_trigram()
        super(Article, self).save(*args, **kwargs)

        # TODO(6): create method in services + generate variants
        #ArticleSearchIndex.objects.filter(article=self).delete()

        # html = bs(self.article_html, "html.parser")
        # for tag in html.findAll('b'):
        #     tag.extract()
        # text = strip_tags(str(html))
        #
        # text = re.sub('~[\S]*', '', text)
        # text = re.sub('[^А-яЁё' + self.get_krl_abc() + 'i̮\s\-]', '', text)

        # print(self.word)
        # print(text)
        # print(set(text.split()))
        # print('-----------------')
        # for iw in set(text.split()):
        #     ai = ArticleSearchIndex(
        #         word=iw,
        #         article=self
        #     )

        ArticleIndexWord.objects.filter(article=self).delete()
        indx = (ArticleIndexWord(article=self, word=var) for var in self.word_index())
        ArticleIndexWord.objects.bulk_create(indx)


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