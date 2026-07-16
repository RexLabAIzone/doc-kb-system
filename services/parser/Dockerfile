FROM python:3.12-slim

RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    libmagic1 libpq-dev \
    tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
    libreoffice-writer libreoffice-impress \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
COPY . .

CMD ["python", "main.py"]
