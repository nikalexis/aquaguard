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
AQUAGUARD_METER_RESET_THRESHOLD_L=1.0
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

Create a local `.env` file in `stats/` and keep it out of source control. The repo ignores `stats/.env`.

```sh
cp stats/.env.example stats/.env
# then edit stats/.env with your real values
```

```sh
docker build -t aquaguard-stats ./stats
docker run --rm \
  -p 8080:8080 \
  -v "$PWD/stats/data:/data" \
  --env-file stats/.env \
  aquaguard-stats
```

The app stores one idempotent snapshot per zone per local day at 12:00. It also stores chart-ready daily measurement quality: exact, estimated, missing, reset, or partial. `AQUAGUARD_METER_RESET_THRESHOLD_L` controls how large a counter drop must be before it is treated as a meter reset.

Or from this directory:

```sh
docker compose up --build
```
