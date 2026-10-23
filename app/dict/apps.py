from django.apps import AppConfig


class DictConfig(AppConfig):
    name = "dict"
    verbose_name = "Словарь"

    def ready(self):
        from django.utils.autoreload import autoreload_started

        import dict.signals
        from punzh.dotenv import watch_dotenv

        autoreload_started.connect(watch_dotenv)
