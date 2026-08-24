## Technical requirements

@todo

### Helpful commands

#### Dump fixtures 

```bash
docker compose -f docker-compose.internal.yml exec -w /app django \
  python manage.py dumpdata dict --indent 2 \
  --exclude dict.ArticleIndexWord \
  --exclude dict.ArticleIndexWordNormalization \
  -o /app/dict/fixtures/dict_seed.json
```

#### Load fixtures 

Before load need to clear dict_ tables

```bash
docker exec -w /app punzh_django python manage.py loaddata  /app/dict/fixtures/dict_seed.json
```
After need to restore indexes

```python
from django.contrib.postgres.search import SearchVector
from dict.models import Article, ArticleIndexTranslate

# 1) пересобрать индексы слов/нормализаций через save()
i = 0
for art in Article.objects.all().iterator():
    art.save()
    i += 1
    if i % 1000 == 0:
        print("reindex words:", i)
print("reindex words done:", i)

print("search_vector:", ArticleIndexTranslate.objects.update(search_vector=SearchVector("rus_word")))
```

----


```bash
docker exec --user 1000:1000 punzh_django python manage.py makemigrations
```

```bash
docker exec --user 1000:1000  -it punzh_django python manage.py migrate
```


### Lint code
```bash
docker exec --user 1000:1000 -i punzh_django black dict/
```


@todo: add deploy flow script