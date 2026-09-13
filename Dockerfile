FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ ./templates/

EXPOSE 8888

# 确保配置文件存在
RUN touch /app/servers.json && echo '[]' > /app/servers.json

CMD ["python", "app.py"]