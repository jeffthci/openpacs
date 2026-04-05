FROM python:3.11-slim

WORKDIR /app

# System deps for pynetdicom / pydicom
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create storage dirs
RUN mkdir -p /opt/pacs/storage /opt/pacs/staging

EXPOSE 8000 11112

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
