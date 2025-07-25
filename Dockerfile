FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --only=main --no-interaction --no-ansi
COPY . .
CMD ["doge-runner"]
