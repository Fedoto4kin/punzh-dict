"""
Общий клиент рантайм-классификации через шлюз Timeweb.

Используется веткой AI-поиска (разбор запроса) и классификацией новых слов.
Модель — DeepSeek через шлюз (консистентно с пакетной разметкой), меняется
через settings.TIMEWEB_AI_MODEL.

ПРИНЦИП БЕЗОПАСНОСТИ: этот модуль НИКОГДА не роняет вызывающий код. Если ключ
не задан, шлюз недоступен или ответ битый — возвращает None / бросает
контролируемое, а вызывающая сторона уходит в fallback на лексический поиск.
AI-поиск — надстройка, его недоступность не должна ломать сайт.
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Ленивая инициализация openai-клиента к шлюзу. None, если не настроен."""
    global _client
    if _client is not None:
        return _client
    api_key = getattr(settings, "TIMEWEB_AI_API_KEY", "")
    if not api_key:
        logger.warning("TIMEWEB_AI_API_KEY не задан — AI-классификация отключена.")
        return None
    try:
        from openai import OpenAI

        _client = OpenAI(
            api_key=api_key,
            base_url=getattr(
                settings, "TIMEWEB_AI_BASE_URL", "https://api.timeweb.ai/v1"
            ),
        )
        return _client
    except Exception as e:  # noqa: BLE001
        logger.error("Не удалось создать AI-клиент: %s", e)
        return None


def is_available():
    """Настроен ли AI-канал (есть ключ и клиент поднялся)."""
    return _get_client() is not None


def chat_json(system, user, model, timeout=10):
    """
    Один запрос к УКАЗАННОЙ модели, ожидающий JSON-ответ.
    model — строка вида 'yandex/yandexgpt-lite' или 'deepseek/deepseek-v4-flash'
    (берётся вызывающим из settings: TIMEWEB_AI_MODEL_QUERY для разбора запроса,
    TIMEWEB_AI_MODEL_CLASSIFY для классификации слова).
    Возвращает распарсенный объект или None (при любой проблеме — тихо,
    чтобы вызывающий ушёл в fallback).
    """
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            timeout=timeout,
        )
        text = resp.choices[0].message.content
    except Exception as e:  # noqa: BLE001
        logger.warning("AI-запрос не удался (уходим в fallback): %s", e)
        return None
    return _parse_json(text)


def _parse_json(text):
    """Устойчивый парсинг JSON из ответа модели (срезаем markdown-обёртки)."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        logger.warning("AI вернул невалидный JSON.")
        return None
