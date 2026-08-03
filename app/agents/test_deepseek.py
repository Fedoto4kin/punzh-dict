#!/usr/bin/env python3
"""
Тест подключения к DeepSeek API
"""

import os
from openai import OpenAI
from load_env import load_env

def test_connection():
    # Загружаем переменные окружения
    load_env()

    api_key = os.getenv('DEEPSEEK_API_KEY')

    if not api_key:
        print("❌ Ошибка: DEEPSEEK_API_KEY не найден")
        print("📝 Проверь файл .env")
        return False

    # Маскируем ключ для вывода
    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    print(f"🔑 Ключ: {masked_key}")

    try:
        # Инициализируем клиент
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )

        print("⏳ Отправка тестового запроса...")

        # Делаем простой запрос
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ты помощник"},
                {"role": "user", "content": "Напиши 'Привет! Я DeepSeek. Готов к работе!'"}
            ],
            max_tokens=50
        )

        print("\n✅ Подключение успешно!")
        print(f"📝 Ответ: {response.choices[0].message.content}")
        print(f"\n📊 Статистика:")
        print(f"  • Модель: {response.model}")
        print(f"  • Токенов всего: {response.usage.total_tokens}")
        print(f"  • Токенов вход: {response.usage.prompt_tokens}")
        print(f"  • Токенов выход: {response.usage.completion_tokens}")

        return True

    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return False

if __name__ == "__main__":
    test_connection()
