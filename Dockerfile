FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Expose the port the app runs on
EXPOSE 8000


# Start the server
CMD ["gunicorn", "ImsV3.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
