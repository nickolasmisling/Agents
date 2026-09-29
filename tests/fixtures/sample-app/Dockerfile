FROM python:latest

LABEL org.opencontainers.image.title="batchtrack-api" \
      org.opencontainers.image.description="Batch record tracking API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BATCHTRACK_DB=/data/batchtrack.db \
    BATCHTRACK_LIMS_URL=https://lims.bog-plant.internal/api/v2 \
    BATCHTRACK_LIMS_TOKEN=lims_pat_4f8a2c91d7e34b06a5c1f9e2d8b7a630

WORKDIR /srv/batchtrack

COPY . .

RUN pip install --upgrade pip setuptools wheel && \
    pip install .

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080

CMD ["python", "-c", "from app.api import serve; serve(host='0.0.0.0')"]
