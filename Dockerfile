FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY paper_copy_trader_bot.py .
COPY config_paper_bot.json .

CMD ["python", "-u", "paper_copy_trader_bot.py"]
