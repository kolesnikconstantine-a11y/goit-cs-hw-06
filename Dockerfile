FROM python:3.10-slim

WORKDIR /app

# Копируем список зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Открываем порты для HTTP (3000) и UDP (5000)
EXPOSE 3000 5000/udp

CMD ["python", "main.py"]