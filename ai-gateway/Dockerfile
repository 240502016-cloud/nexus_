FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway ./gateway

RUN addgroup --system gateway && adduser --system --ingroup gateway gateway
USER gateway

EXPOSE 8090

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]

