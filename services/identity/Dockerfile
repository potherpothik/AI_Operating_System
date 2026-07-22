# Build context is the REPO ROOT (see docker-compose.yml), same
# convention as every other service's Dockerfile since Phase 19.
FROM python:3.12-slim
WORKDIR /app
COPY services/identity/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/identity/ .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8011
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011"]
