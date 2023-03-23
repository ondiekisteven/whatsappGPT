FROM python:3.10

WORKDIR /app
RUN mkdir /app/logs
COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

COPY . .
