# Build context is the REPO ROOT, same convention as every other
# service's Dockerfile since Phase 19.
FROM python:3.12-slim
WORKDIR /app
COPY services/control-ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/control-ui/ .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8024
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8024"]
