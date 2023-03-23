FROM python:3.8.5-alpine3.12

WORKDIR /app

ENV FLASK_RUN_HOST 0.0.0.0

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY . .
