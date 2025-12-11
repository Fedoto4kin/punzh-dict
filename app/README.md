## Technical requirements

```bash
docker exec -it punzh_django python manage.py migrate
```

### Load fixtures 
```bash
docker exec -it punzh_django python manage.py loaddata /app/dict/fixtures/dict_fixtures.json
```
