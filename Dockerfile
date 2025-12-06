FROM python:3.12-slim

# рабочая директория внутри контейнера
WORKDIR /app

# сначала зависимости, чтобы не пересобирать по каждому изменению кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# копируем весь проект внутрь контейнера
COPY . .

# запускаем бота через модуль
CMD ["python", "-m", "bot.main"]
