FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-vision.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Optional object detection / tracking (adds PyTorch, several GB).
# Enabled by docker-compose.vision.yml.
ARG INSTALL_VISION=false
RUN if [ "$INSTALL_VISION" = "true" ]; then \
      pip install --no-cache-dir -r requirements-vision.txt; \
    fi

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
