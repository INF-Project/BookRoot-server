FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 BOOK_SEARCH_BACKEND=catalog CATALOG_DB_PATH=/app/data/catalog.sqlite3
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && groupadd --gid 10001 bookroot && useradd --uid 10001 --gid bookroot --no-create-home bookroot
COPY --chown=bookroot:bookroot app/ ./app/
COPY --chown=bookroot:bookroot web/ ./web/
COPY --chown=bookroot:bookroot data/ ./data/
COPY --chown=bookroot:bookroot server.py ./
USER bookroot
CMD ["python", "server.py"]
