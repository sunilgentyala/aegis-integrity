FROM python:3.11-slim

WORKDIR /app

# System dependencies for PyMuPDF and FAISS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e ".[ml,nlp,bib]"

# Pre-download SBERT model so first run is fast
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-MiniLM-L6-v2')" || true

ENV AEGIS_INDEX_DIR=/data/index
ENV AEGIS_REPORT_DIR=/data/reports
ENV AEGIS_DEVICE=cpu

VOLUME ["/data"]

EXPOSE 8000

CMD ["aegis", "serve", "--host", "0.0.0.0", "--port", "8000"]
