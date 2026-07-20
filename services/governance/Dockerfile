# Build context is the REPO ROOT (see docker-compose.yml), not this
# directory — lets every service share one root .dockerignore rather
# than needing eleven identical copies.
FROM python:3.12-slim
WORKDIR /app
COPY services/governance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/governance/ .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
