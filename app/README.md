### Tests

```sh
docker exec -it --user 1000:1000 punzh_django python manage.py test
```


### Upload fixtures

```sh
docker exec -it --user 1000:1000 punzh_django python manage.py loaddata dict/fixtures/dict.json
```
