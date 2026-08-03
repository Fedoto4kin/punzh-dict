#!/usr/bin/env python3
"""
Загрузка переменных окружения из .env файла
"""

import os
from pathlib import Path

def load_env():
    """Загружает переменные из .env файла"""
    env_file = Path('.env')
    if not env_file.exists():
        print("⚠️  Файл .env не найден. Создай его с DEEPSEEK_API_KEY")
        return False

    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key] = value

    print("✅ Переменные окружения загружены")
    return True

if __name__ == "__main__":
    load_env()
