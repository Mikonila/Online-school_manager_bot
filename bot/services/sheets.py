import gspread
from google.oauth2.service_account import Credentials
import logging
import re
import os
from typing import Dict, List, Optional
from bot.config import load_config

logger = logging.getLogger(__name__)

# Загружаем конфигурацию
config = load_config()

# Подключение к Google Sheets
def connect_to_sheet():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Проверяем наличие файла credentials
        if not os.path.exists(config.CREDENTIALS_PATH):
            logger.error(f"❌ Файл credentials.json не найден по пути: {config.CREDENTIALS_PATH}")
            raise FileNotFoundError(f"Файл учетных данных не найден: {config.CREDENTIALS_PATH}")
        
        creds = Credentials.from_service_account_file(config.CREDENTIALS_PATH, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(config.MAIN_SHEET_ID)
        return spreadsheet.sheet1  # используем первый лист
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
        raise

def connect_to_courses_sheet():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        if not os.path.exists(config.CREDENTIALS_PATH):
            logger.error(f"❌ Файл credentials.json не найден по пути: {config.CREDENTIALS_PATH}")
            raise FileNotFoundError(f"Файл учетных данных не найден: {config.CREDENTIALS_PATH}")
        
        creds = Credentials.from_service_account_file(config.CREDENTIALS_PATH, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(config.COURSES_SHEET_ID)
        return spreadsheet.sheet1  # используем первый лист
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к таблице курсов: {e}")
        raise

def connect_to_tariffs_sheet():
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        if not os.path.exists(config.CREDENTIALS_PATH):
            logger.error(f"❌ Файл credentials.json не найден по пути: {config.CREDENTIALS_PATH}")
            raise FileNotFoundError(f"Файл учетных данных не найден: {config.CREDENTIALS_PATH}")
        
        creds = Credentials.from_service_account_file(config.CREDENTIALS_PATH, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(config.TARIFFS_SHEET_ID)
        return spreadsheet.sheet1  # используем первый лист
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к таблице тарифов: {e}")
        raise

def update_user_row(user_data: dict):
    print("=== update_user_row called ===", user_data)
    logger.info(f"🔄 Начинаю запись в Google Sheets: {user_data}")
    try:
        # Проверяем наличие файла credentials
        import os
        creds_path = "bot/services/credentials.json"
        if not os.path.exists(creds_path):
            logger.error(f"❌ Файл credentials.json не найден по пути: {creds_path}")
            return
        
        sheet = connect_to_sheet()
        logger.info("✅ Подключение к Google Sheets успешно")
        
        records = sheet.get_all_records()
        headers = sheet.row_values(1)
        logger.info(f"📋 Заголовки таблицы: {headers}")
        logger.info(f"🔍 Ищу ID пользователя: {user_data['ID']}")

        user_id = str(user_data["ID"])
        
        # Проверяем наличие необходимых колонок
        required_columns = ["Username", "История переписки"]
        for col in required_columns:
            if col not in headers:
                logger.error(f"❌ Колонка '{col}' не найдена в таблице. Доступные колонки: {headers}")
                return
        
        username_col_index = headers.index("Username") + 1
        history_col_index = headers.index("История переписки") + 1
        summary_col_index = headers.index("Резюме") + 1 if "Резюме" in headers else None
        manager_col_index = headers.index("Заявка менеджеру") + 1 if "Заявка менеджеру" in headers else None
        teacher_col_index = headers.index("Преподаватель") + 1 if "Преподаватель" in headers else None

        logger.info(f"📊 Индексы колонок: Username={username_col_index}, История={history_col_index}, Резюме={summary_col_index}, Менеджер={manager_col_index}, Преподаватель={teacher_col_index}")

        # Ищем существующую строку пользователя
        user_found = False
        for i, record in enumerate(records, start=2):
            logger.info(f"🔍 Проверяю строку {i}: ID={record.get('ID', 'НЕТ')}")
            if str(record.get("ID", "")) == user_id:
                logger.info(f"✅ Найдена существующая строка {i} для пользователя {user_id}")
                user_found = True
                
                # Обновляем данные
                sheet.update_cell(i, username_col_index, user_data["Username"])
                logger.info(f"✅ Обновлен Username в строке {i}")
                
                existing_history = sheet.cell(i, history_col_index).value or ""
                new_history = existing_history + "\n\n" + user_data["История"]
                MAX_CELL_LENGTH = 49000  # чуть меньше лимита для запаса
                if len(new_history) > MAX_CELL_LENGTH:
                    new_history = new_history[-MAX_CELL_LENGTH:]
                sheet.update_cell(i, history_col_index, new_history)
                logger.info(f"✅ Обновлена История в строке {i}")
                
                if summary_col_index:
                    sheet.update_cell(i, summary_col_index, user_data.get("Резюме", ""))
                    logger.info(f"✅ Обновлено Резюме в строке {i}")
                
                if manager_col_index:
                    manager_value = user_data.get("Заявка менеджеру", "")
                    sheet.update_cell(i, manager_col_index, manager_value)
                    logger.info(f"✅ Обновлена Заявка менеджеру в строке {i}: '{manager_value}'")
                
                if teacher_col_index:
                    teacher_value = user_data.get("Преподаватель", "")
                    sheet.update_cell(i, teacher_col_index, teacher_value)
                    logger.info(f"✅ Обновлена Преподаватель в строке {i}: '{teacher_value}'")
                
                logger.info(f"✅ Строка {i} успешно обновлена")
                return

        # Если пользователь не найден, добавляем новую строку
        if not user_found:
            new_history = user_data["История"]
            MAX_CELL_LENGTH = 49000  # чуть меньше лимита для запаса
            if len(new_history) > MAX_CELL_LENGTH:
                new_history = new_history[-MAX_CELL_LENGTH:]
            new_row = [
                user_data["ID"],
                user_data["Username"],
                new_history,
                user_data.get("Резюме", ""),
                user_data.get("Заявка менеджеру", ""),
                user_data.get("Преподаватель", "")
            ]
            logger.info(f"📝 Новая строка: {new_row}")
            sheet.append_row(new_row)
            logger.info("✅ Новая строка успешно добавлена")

    except Exception as e:
        logger.exception(f"❌ Ошибка при записи в таблицу: {e}")
        import traceback
        logger.error(f"🔍 Полный traceback: {traceback.format_exc()}")

# def get_course_info(course_name: str) -> Optional[Dict]:
#     try:
#         sheet = connect_to_courses_sheet()
#         records = sheet.get_all_records()
#         headers = sheet.row_values(1)
#         course_name_lower = course_name.lower().strip()
#         for record in records:
#             sheet_course_name = str(record.get("Курс", "")).lower().strip()
#             if course_name_lower in sheet_course_name or sheet_course_name in course_name_lower:
#                 return {
#                     "name": record.get("Курс", ""),
#                     "subscription_price": record.get("Подписка на 30 дней", ""),
#                     "pro_price": record.get("ПРО", ""),
#                     "pro_access": record.get("доступ к урокам в пакете ПРО", ""),
#                     "online_price_1": record.get("Онлайн индивидуально 1 урок", ""),
#                     "online_price_8": record.get("Онлайн индивидуально 8 уроков", ""),
#                     "lessons": record.get("количество основных уроков, не считая демо уроков", ""),
#                     "note": record.get("Примечание", ""),
#                     "demo_link": record.get("Демо-ссылка", "")
#                 }
#         return None
#     except Exception as e:
#         logger.exception(f"Ошибка при получении информации о курсе '{course_name}': {e}")
#         return None

def get_all_courses() -> List[Dict]:
    try:
        sheet = connect_to_courses_sheet()
        records = sheet.get_all_records()
        # Добавляем demo_link для каждого курса
        for record in records:
            if "Демо-ссылка" in record:
                record["demo_link"] = record["Демо-ссылка"]
        return records
    except Exception as e:
        logger.exception(f"Ошибка при получении всех курсов: {e}")
        return []

# def get_course_prices(course_name: str) -> Dict:
#     """Получить цены для конкретного курса"""
#     course_info = get_course_info(course_name)
#     if course_info:
#         return {
#             "subscription": course_info.get("subscription_price", ""),
#             "pro": course_info.get("pro_price", ""),
#             "online": course_info.get("online_price_1", "")
#         }
#     return {}

def is_scratch_course(course_name: str) -> bool:
    course_name_lower = course_name.lower()
    return "scratch" in course_name_lower or "скретч" in course_name_lower

def get_tariff_info(tariff_type: Optional[str] = None) -> Dict:
    try:
        sheet = connect_to_tariffs_sheet()
        records = sheet.get_all_records()
        headers = sheet.row_values(1)
        tariffs = {}
        for record in records:
            name = str(record.get("название тарифа", "")).strip()
            description = str(record.get("описание тарифа", "")).strip()
            for_whom = str(record.get("для кого этот тариф", "")).strip()
            features = str(record.get("особенности", "")).strip()
            trial = str(record.get("пробные уроки бесплатные", "")).strip()
            if name:
                tariffs[name.lower()] = {
                    "name": name,
                    "description": description,
                    "for_whom": for_whom,
                    "features": features,
                    "trial": trial
                }
        if tariff_type:
            t = tariff_type.lower()
            for key, value in tariffs.items():
                if t in key or key in t:
                    return value
            return {}
        return tariffs
    except Exception as e:
        logger.exception(f"Ошибка при получении информации о тарифах: {e}")
        return {}
