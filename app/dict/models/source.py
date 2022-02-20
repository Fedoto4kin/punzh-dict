from django.db import models

class Source(models.Model):

    title = models.CharField(max_length=255,
                             verbose_name='Название источника')
    description = models.TextField(default='',
                                   blank=True,
                                   null=True,
                                   verbose_name='Описание')
    css = models.CharField(max_length=255, blank=True, null=True, verbose_name='CSS Styling')


    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Источник'
        verbose_name_plural = 'Источники'
        ordering = ['id']