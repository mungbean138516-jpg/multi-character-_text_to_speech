FROM python:3.12-slim

WORKDIR /app
COPY . .

ENV PYTHONUNBUFFERED=1
ENV APP_OUTPUT_DIR=/app/data/outputs

EXPOSE 8000
CMD ["python", "-m", "audiobook_app", "serve", "--host", "0.0.0.0", "--port", "8000"]

