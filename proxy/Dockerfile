FROM python:3.12-slim

WORKDIR /app

COPY fetch_urban_proxies.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENV PROXY_OUTPUT=/data/proxies_curl.txt
ENV WORKERS=20
ENV INTERVAL_MIN=25

ENTRYPOINT ["/app/entrypoint.sh"]
