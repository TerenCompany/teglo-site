FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
RUN useradd -r -u 10001 bot
USER bot
CMD ["python", "-u", "bot.py"]
