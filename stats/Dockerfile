FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY aquaguard_stats ./aquaguard_stats

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["aquaguard-stats"]

