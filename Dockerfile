FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application sources
COPY 05_API ./05_API
COPY 04_Database ./04_Database

EXPOSE 8080

CMD ["uvicorn", "05_API.src.main:app", "--host", "0.0.0.0", "--port", "8080"]
