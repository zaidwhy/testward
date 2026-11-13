FROM python:3.12-slim

RUN useradd --create-home --uid 10001 ledger
WORKDIR /srv/testward
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[server]"

# /data is the only writable state; mount a volume there.
RUN mkdir /data && chown ledger /data
USER ledger
ENV TESTWARD_DB=/data/testward.sqlite3
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if b'ok' in urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read() else 1)"
CMD ["uvicorn", "testward.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
