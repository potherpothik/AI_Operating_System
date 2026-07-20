# Build context is the REPO ROOT (see docker-compose.yml).
FROM python:3.12-slim
WORKDIR /app
COPY services/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/agents/ .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8005
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
