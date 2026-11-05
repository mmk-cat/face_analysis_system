FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY app ./app
COPY mock_iflytek ./mock_iflytek
COPY data ./data
COPY wsgi.py .

RUN mkdir -p /app/runtime /app/logs
EXPOSE 5003
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5003", "--access-logfile", "-", "wsgi:app"]
