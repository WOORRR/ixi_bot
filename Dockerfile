FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PORT 는 Cloud Run 이 주입한다 (기본 8080)
CMD ["python", "main.py"]
