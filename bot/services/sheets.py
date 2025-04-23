import gspread
from google.oauth2.service_account import Credentials

# Подключение к Google Sheets
def connect_to_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file("bot/services/credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open("Codim_logs")  # замени на своё название
    return spreadsheet.sheet1  # используем первый лист

def update_user_row(user_data: dict):
    """
    user_data = {
        "ID": "123456",
        "Имя": "Валерия",
        "Username": "@helionstudio",
        "Возраст": "7",
        "Опыт": "начинает",
        "Интересы": "игры",
        "История": "Пользователь: ...\nБот: ..."
    }
    """
    sheet = connect_to_sheet()
    records = sheet.get_all_records()
    headers = sheet.row_values(1)

    user_id = str(user_data["ID"])
    history_col_index = headers.index("История переписки") + 1

    for i, record in enumerate(records, start=2):  # начиная со второй строки
        if str(record["ID"]) == user_id:
            # обновляем существующую строку
            existing_history = sheet.cell(i, history_col_index).value or ""
            new_history = existing_history + "\n\n" + user_data["История"]
            sheet.update_cell(i, history_col_index, new_history)
            return

    # Если пользователя нет — добавляем строку
    new_row = [
        user_data["ID"],
        user_data["Имя"],
        user_data["Username"],
        user_data["Возраст"],
        user_data["Опыт"],
        user_data["Интересы"],
        user_data["История"]
    ]
    sheet.append_row(new_row)
