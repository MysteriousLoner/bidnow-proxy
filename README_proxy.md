# Flask Proxy for BidNow

## 1) Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Run server

```bash
python app.py
```

Server runs on `http://localhost:8090`.

## 3) API endpoint

`GET /api/bidnow-properties`

Behavior:
- No args: return all entries by crawling pages.
- `state`: optional state filter.
- `page`: optional page number (if provided, returns that page only).
- `limit`: optional max returned items.

Example:

```bash
curl "http://localhost:8090/api/bidnow-properties"
curl "http://localhost:8090/api/bidnow-properties?state=Selangor&page=1&limit=12"
```

Health check:

```bash
curl "http://localhost:8090/health"
```

## Docker

```bash
docker build -t bidnow-proxy .
docker run --rm -p 8090:8090 bidnow-proxy
```

## Docker Compose

```bash
docker compose up --build
```

Stop:

```bash
docker compose down
```
