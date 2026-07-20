# Build context is the REPO ROOT (see docker-compose.yml).
FROM python:3.12-slim
WORKDIR /app
COPY services/knowledge_pipelines/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/knowledge_pipelines/ .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8009
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8009"]
