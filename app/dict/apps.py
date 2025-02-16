from django.apps import AppConfig


class DictConfig(AppConfig):
    name = 'dict'
    verbose_name = 'Словарь'

    def ready(self):
        import dict.signals
