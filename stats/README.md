# AquaGuard Stats

FastAPI dashboard for AquaGuard daily water consumption statistics.

## Configuration

Configure with environment variables:

```sh
AQUAGUARD_ESPHOME_HOST=aquaguard.local
AQUAGUARD_ESPHOME_PORT=6053
AQUAGUARD_API_ENCRYPTION_KEY=...
AQUAGUARD_DB_PATH=data/aquaguard-stats.sqlite3
AQUAGUARD_TIMEZONE=Europe/Athens
AQUAGUARD_WARNING_THRESHOLD=0.8
```

## Run Locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
aquaguard-stats
```

Open `http://localhost:8080`.

## Docker

```sh
docker build -t aquaguard-stats ./stats
docker run --rm \
  -p 8080:8080 \
  -v "$PWD/stats/data:/data" \
  -e AQUAGUARD_ESPHOME_HOST=aquaguard.local \
  -e AQUAGUARD_API_ENCRYPTION_KEY='your-api-key' \
  -e AQUAGUARD_DB_PATH=/data/aquaguard-stats.sqlite3 \
  aquaguard-stats
```

The app stores one idempotent snapshot per zone per local day at 12:00.

Or from this directory:

```sh
docker compose up --build
```
