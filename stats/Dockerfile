FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./

RUN pip install --no-cache-dir \
    "aioesphomeapi>=27.0.0" \
    "fastapi>=0.115.0" \
    "jinja2>=3.1.0" \
    "uvicorn[standard]>=0.32.0"

COPY aquaguard_stats ./aquaguard_stats

EXPOSE 8080

CMD ["python", "-m", "aquaguard_stats.web"]
