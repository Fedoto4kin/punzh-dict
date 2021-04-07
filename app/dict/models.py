from django.db import models
from viewflow.fields import CompositeKey
from bs4 import BeautifulSoup as bs
import string
import re
from django.utils.html import strip_tags

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

    def save(self, *args, **kwargs):

        self.first_letter = self.word[0].upper()

        self.first_trigram = ''.join(
            list(
                filter( 
                        lambda x: x in self.get_krl_abc(),
                        self.word.split()[0].replace('i̮a', 'ua')
                    )
                )
            )[:3].lower()

        super(Article, self).save(*args, **kwargs)

        # TODO(4): create method + generate variants
        ArticleSearchIndex.objects.filter(article=self).delete()

        html = bs(self.article_html, "html.parser")
        for tag in html.findAll('b'):
            tag.extract()
        text = strip_tags(str(html))

        text = re.sub('~[\S]*', '', text)
        text = re.sub('[^А-яЁё' + self.get_krl_abc() + 'i̮\s\-]', '', text)

        print(self.word)
        print(text)
        print(set(text.split()))
        print('-----------------')
        for iw in set(text.split()):
            ai = ArticleSearchIndex(
                word=iw,
                article=self
            )

        # TODO(1): create method + generate variants
        # TODO(2): Now can be duplicates, fix in method
        SearchWord.objects.filter(article=self).delete()
        base = re.split(r'\|+', self.word.split(',')[0])[0]
        for _ in self.word.replace('|', '').replace('’', '').split():
            if _ not in ['I', 'II', 'III']:
                if '~' in _:
                    _ = _.replace('~', base)
                w = SearchWord(
                    word=_.replace(',', '').strip(),
                    article=self
                )
                w.save()

# TODO(3): remove id from table use Composite key (after fix todo(2))
# Rename it ArticleWordIndex
class SearchWord(models.Model):

    word = models.CharField(max_length=255, default=None, blank=True, null=True)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='articles')

    def __str__(self):
        return self.word

# TODO: split to Context and Semantics Indexes
class ArticleSearchIndex(models.Model):

    id = CompositeKey(columns=['article', 'word'])

    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    word = models.CharField(max_length=255, default=None, blank=True, null=True)

    def __str__(self):
        return self.word
