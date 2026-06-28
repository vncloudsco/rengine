FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "psycopg2-binary>=2.9.9"

COPY fetch_urban_proxies.py sync_proxies_to_db.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENV PROXY_OUTPUT=/data/proxies_curl.txt
ENV WORKERS=20
ENV INTERVAL_MIN=25
ENV AUTO_ENABLE_PROXY=true

ENTRYPOINT ["/app/entrypoint.sh"]
