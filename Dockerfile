FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput && \
    adduser --disabled-password --no-create-home basil && \
    chown -R basil:basil /app

USER basil

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
