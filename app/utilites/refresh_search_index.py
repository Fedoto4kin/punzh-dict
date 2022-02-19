import os
import sys
import django

sys.path.append('../')

os.environ["DJANGO_SETTINGS_MODULE"] = 'punzh.settings'
django.setup()

from dict.models import Article


if __name__ == '__main__':

    for a in Article.objects.all():
        print(a.word_normalization_index())
        a.save()
