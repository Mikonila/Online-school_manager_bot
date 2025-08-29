#!/usr/bin/env python3
"""
Скрипт для создания векторной базы данных из документов с использованием MarkdownHeaderTextSplitter
"""

import sys
from pathlib import Path

# Добавляем путь к модулям бота
sys.path.append(str(Path(__file__).parent.parent))

from bot.services.search_engine import create_vector_db, split_markdown_text
from bot.services.search_engine import DOCS_DIR

def test_markdown_splitting():
    """Тестирует разбивку markdown-файлов на чанки"""
    print("🔍 Тестирование разбивки markdown-файлов...")
    
    if not DOCS_DIR.exists():
        print(f"❌ Папка {DOCS_DIR} не найдена")
        return
    
    # Ищем markdown-файлы
    markdown_files = list(DOCS_DIR.glob("**/*.txt"))
    
    if not markdown_files:
        print("❌ Markdown-файлы не найдены")
        return
    
    total_chunks = 0
    
    for file_path in markdown_files:
        print(f"\n📄 Обрабатываем файл: {file_path.name}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Разбиваем на чанки
            chunks = split_markdown_text(content, strip_headers=False)
            total_chunks += len(chunks)
            
            print(f"   ✅ Создано {len(chunks)} чанков")
            
            # Показываем пример первого чанка
            if chunks:
                first_chunk = chunks[0]
                print(f"   📝 Пример чанка:")
                print(f"      Заголовки: {first_chunk.metadata}")
                print(f"      Содержимое: {first_chunk.page_content[:100]}...")
            
        except Exception as e:
            print(f"   ❌ Ошибка при обработке {file_path.name}: {e}")
    
    print(f"\n📊 Итого: {len(markdown_files)} файлов, {total_chunks} чанков")


if __name__ == "__main__":
    print("🚀 Запуск создания векторной базы данных...")
    
    # Сначала тестируем разбивку
    test_markdown_splitting()
    
    print("\n" + "="*50)
    
    # Создаём векторную базу
    create_vector_db()
    
    print("\n✅ Готово! Векторная база данных создана.")
