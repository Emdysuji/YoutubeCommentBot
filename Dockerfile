FROM python:3.12-slim

# Environment
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .


CMD ["python", "yt_bot.py"]
