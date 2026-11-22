FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY scripts ./scripts
COPY tests/sample ./tests/sample
ENV PYTHONPATH=/app/src DATA_DIR=/app/data PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c 'import os,urllib.request as u; u.urlopen("http://localhost:%s/api/health" % os.getenv("PORT","8000"))'
# fetch_data.py auto pobiera pliki tylko gdy ustawiono LEKI_URL / APTEKI_URL; błąd sieci nie blokuje startu
CMD ["sh", "-c", "python scripts/fetch_data.py auto || true; exec python -m tanszylek"]
