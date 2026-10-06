# Serving image: ONNX Runtime only. No PyTorch, no training code paths are exercised here.
FROM python:3.12-slim AS serve

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    METRONOME_REGISTRY=/registry \
    PORT=8000

WORKDIR /app
RUN groupadd --system metronome && useradd --system --gid metronome --home-dir /app --shell /usr/sbin/nologin metronome

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER metronome
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8000') + '/ready', timeout=2).status == 200 else 1)"
CMD ["sh", "-c", "metronome serve --registry \"$METRONOME_REGISTRY\" --host 0.0.0.0 --port \"$PORT\""]
