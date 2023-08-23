from django.db import models


class Tag(models.Model):

    TYPES = (
        (1, 'Населенные пункты'),
        (2, 'Часть речи'),
        (3, 'Пометы'),
        (4, 'Говоры'),
        (5, 'Другое'),
    )

    tag = models.CharField(max_length=255, db_index=True,)
    name = models.TextField()
    type = models.IntegerField(choices=TYPES)
    sorting = models.IntegerField(db_index=True, null=True,)
    level = models.IntegerField(default=0,)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.tag
