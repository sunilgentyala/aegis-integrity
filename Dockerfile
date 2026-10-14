# Pinned to the current python:3.11-slim manifest-list digest for
# reproducible builds. Refresh periodically (e.g. `docker pull python:3.11-slim`
# then `docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim`)
# to pick up security patches -- a floating tag alone can silently drift.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

WORKDIR /app

# System dependencies for PyMuPDF and FAISS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# setup.py's install_requires + extras already cover every dependency this
# image needs -- requirements.txt is a separate, overlapping list (also used
# for `pip install -r requirements.txt` outside Docker), so installing both
# here would just reinstall most of the same packages twice.
COPY . .
RUN pip install --no-cache-dir -e ".[ml,nlp,bib]"

# Pre-download SBERT model so first run is fast. Non-fatal if the build has
# no network access (the app will download it lazily on first use instead),
# but the failure is printed clearly rather than silently discarded.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-MiniLM-L6-v2')" \
    || echo "WARNING: could not pre-download the SBERT model at build time; it will be downloaded on first use instead"

ENV AEGIS_INDEX_DIR=/data/index
ENV AEGIS_REPORT_DIR=/data/reports
ENV AEGIS_DEVICE=cpu

RUN groupadd --gid 1000 aegis \
    && useradd --uid 1000 --gid aegis --shell /bin/bash --create-home aegis \
    && mkdir -p /data \
    && chown -R aegis:aegis /app /data

USER aegis

VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request,sys; \
    sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=5).status == 200 else 1)"

CMD ["aegis", "serve", "--host", "0.0.0.0", "--port", "8000"]
