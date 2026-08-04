"""
Проверка рантайм-канала AI-классификации (шлюз Timeweb).

Аналог agents/test_deepseek.py, но для РАНТАЙМА: идёт через настоящий
dict.ai.client (settings → env → openai-клиент → шлюз), т.е. проверяет ровно
тот путь, что использует AI-поиск. Не дублирует логику клиента.

Запуск:
    docker exec -i -w /app punzh_django python manage.py test_timeweb
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from dict.ai import client as ai_client


class Command(BaseCommand):
    help = "Проверить подключение к шлюзу Timeweb через dict.ai.client."

    def handle(self, *args, **options):
        key = getattr(settings, "TIMEWEB_AI_API_KEY", "")
        base = getattr(settings, "TIMEWEB_AI_BASE_URL", "")
        model_q = getattr(settings, "TIMEWEB_AI_MODEL_QUERY", "")
        model_c = getattr(settings, "TIMEWEB_AI_MODEL_CLASSIFY", "")

        # 1. конфиг
        if key:
            masked = key[:4] + "..." + key[-3:] if len(key) > 8 else "***"
            self.stdout.write(f"🔑 Ключ: {masked}")
        else:
            self.stdout.write(self.style.ERROR("❌ TIMEWEB_AI_API_KEY пуст."))
            self.stdout.write("   AI-поиск будет работать в режиме fallback "
                              "(обычный лексический поиск).")
            return
        self.stdout.write(f"🌐 base_url: {base}")
        self.stdout.write(f"🤖 model (запрос): {model_q}")
        self.stdout.write(f"🤖 model (классификация): {model_c}")

        # 2. доступность клиента
        if not ai_client.is_available():
            self.stdout.write(self.style.ERROR(
                "❌ Клиент не поднялся (см. лог). Fallback."))
            return
        self.stdout.write("✅ Клиент инициализирован.")

        # 3. живой запрос через ОБЕ модели (query + classify) — тот же путь, что рантайм
        self.stdout.write("⏳ Тест модели разбора запроса (query)...")
        r_q = ai_client.chat_json(
            system="Ты отвечаешь СТРОГО одним JSON-объектом, без пояснений.",
            user='Верни ровно {"ok": true, "msg": "готов"}.',
            model=model_q,
        )
        if r_q is None:
            self.stdout.write(self.style.ERROR(
                f"❌ Модель разбора ({model_q}) не ответила. Проверь имя модели."))
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ query OK: {r_q}"))

        self.stdout.write("⏳ Тест модели классификации (classify)...")
        r_c = ai_client.chat_json(
            system="Ты отвечаешь СТРОГО одним JSON-объектом, без пояснений.",
            user='Верни ровно {"ok": true, "msg": "готов"}.',
            model=model_c,
        )
        if r_c is None:
            self.stdout.write(self.style.ERROR(
                f"❌ Модель классификации ({model_c}) не ответила. Проверь имя модели."))
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ classify OK: {r_c}"))

        if r_q is not None and r_c is not None:
            self.stdout.write(self.style.SUCCESS("✅ Обе модели доступны через шлюз."))
        else:
            self.stdout.write(self.style.WARNING(
                "⚠ Не все модели ответили — соответствующая функция уйдёт в fallback."))
