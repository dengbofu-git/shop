ARG PYTHON_IMAGE=python:3.13-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false \
    AI_PDF_TOKENIZER_PATH=/models/bge-m3/tokenizer.json
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
    build-essential pkg-config default-libmysqlclient-dev \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /build/requirements.txt
COPY constraints-py313.txt /build/constraints-py313.txt
COPY deploy/knowledge-worker/requirements.txt /build/pdf-requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt -r /build/pdf-requirements.txt
# Tokenizer only: no 2GB language model download, no runtime network resolution.
RUN python -c "from pathlib import Path; import urllib.request; p=Path('/models/bge-m3/tokenizer.json'); p.parent.mkdir(parents=True); urllib.request.urlretrieve('https://huggingface.co/BAAI/bge-m3/resolve/5617a9f61b028005a4858fdac845db406aefb181/tokenizer.json', p)"
RUN groupadd -g 10001 knowledge && useradd -u 10001 -g knowledge -M knowledge \
    && mkdir /knowledge && chown knowledge:knowledge /knowledge
USER knowledge
CMD ["python", "manage.py", "knowledge_pdf", "worker"]
