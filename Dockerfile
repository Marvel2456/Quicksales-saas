FROM python:3.12-slim-bookworm

# Unset any proxy injected by Docker Desktop / build environment
ENV http_proxy="" \
    https_proxy="" \
    HTTP_PROXY="" \
    HTTPS_PROXY="" \
    no_proxy="" \
    NO_PROXY=""

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_DEFAULT_TIMEOUT=180
ENV PIP_RETRIES=10
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir --timeout=180 --retries=10 \
    && pip install --no-cache-dir --timeout=180 --retries=10 -r requirements.txt

COPY . .

# Expose the port the app runs on
EXPOSE 8000


# Start the server
CMD ["gunicorn", "ImsV3.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
