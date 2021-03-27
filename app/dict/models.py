from django.db import models
from slugify import slugify

KRL_ABC = 'ABCČDEFGHIJKLMNOPRSŠZŽTUVÜÄÖ'

class Article(models.Model):

    word = models.CharField(unique=True, max_length=255, db_index=True)
    word_slug = models.CharField(max_length=255)
    first_letter = models.CharField(max_length=1)
    first_trigram = models.CharField(max_length=3)
    article_html = models.TextField(default='')


    @staticmethod
    def get_krl_abc():
        abc = ''
        for l in KRL_ABC:
            abc += l + l.lower()
        return abc + 'w'

    def __str__(self):
        return self.word

    def save(self, *args, **kwargs):
        self.word_slug = slugify(self.word)
        self.first_letter = self.word[0].upper()
        # create first trigram from word 
        self.first_trigram = ''.join(
            list(
                filter( 
                        lambda x: x in self.get_krl_abc(),
                        self.word #todo: splite by whitespace
                    )
            )
        )[:3].lower()
        super(Article, self).save(*args, **kwargs)
