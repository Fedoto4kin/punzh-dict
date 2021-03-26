from django.db import models

KRL_ABC = 'ABCČDEFGHIJKLMNOPRSŠZŽTUVÜÄÖ'

class Article(models.Model):

    word = models.CharField(max_length=255)
    word_slug = models.CharField(max_length=255)
    first_letter = models.CharField(max_length=1)
    first_trigram = models.CharField(max_length=3)
    definition = models.TextField()

