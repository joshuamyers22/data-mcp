FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.runtime.txt /app/
RUN pip install --no-cache-dir --require-hashes -r requirements.runtime.txt
COPY dist/*.whl /tmp/wheels/
RUN pip install --no-cache-dir --no-deps /tmp/wheels/*.whl \
    && useradd --uid 10001 --create-home app
USER 10001
ENTRYPOINT ["data-mcp"]
