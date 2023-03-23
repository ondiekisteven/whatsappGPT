FROM python:3.10

WORKDIR /app
RUN mkdir /app/logs
ENV FLASK_RUN_HOST 0.0.0.0

COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY . .
