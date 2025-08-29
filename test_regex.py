#!/usr/bin/env python3
"""
Тест регулярных выражений для поиска запросов о демо
"""

import re

def test_demo_patterns():
    print("🧪 Тестирование регулярных выражений для демо:")
    print("=" * 60)
    
    test_cases = [
        "пришли демо роблокс",
        "демо python",
        "хочу посмотреть демо-урок scratch",
        "покажи демоурок minecraft",
        "демо java",
        "пришли демо для ai",
        "демо-урок по unity",
        "демо веб-разработка"
    ]
    
    for test_case in test_cases:
        print(f"\n🔍 Тест: '{test_case}'")
        
        # Проверяем основной паттерн
        demo_match = re.search(r'демо|демо-урок|демоурок', test_case, re.IGNORECASE)
        if demo_match:
            print(f"✅ Найдено слово 'демо'")
            
            # Проверяем извлечение названия курса
            course_match = re.search(r'(?:демо|демо-урок|демоурок)[\s:,-]*([A-Za-zА-Яа-я0-9\- ]{2,})', test_case, re.IGNORECASE)
            if course_match:
                course = course_match.group(1).strip()
                print(f"✅ Извлечен курс: '{course}'")
            else:
                print(f"❌ Курс не извлечен")
        else:
            print(f"❌ Слово 'демо' не найдено")

def test_course_search():
    print("\n\n🔍 Тестирование поиска курсов в тексте:")
    print("=" * 60)
    
    test_text = "пришли демо роблокс"
    course_names = ["scratch", "python", "minecraft", "roblox", "java", "ai", "arduino", "unity", "веб", "web", "майнкрафт", "роблокс", "питон", "скретч", "джава", "ардуино", "юнити"]
    
    print(f"Текст: '{test_text}'")
    
    for course_name in course_names:
        if course_name in test_text.lower():
            print(f"✅ Найден курс: '{course_name}'")
            break
    else:
        print(f"❌ Курсы не найдены")

if __name__ == "__main__":
    test_demo_patterns()
    test_course_search()
    print("\n✅ Тестирование завершено!")



