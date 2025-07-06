# DOGE Carry Bot

This project provides an async trading bot for OKX swap/spot carry trades with
persistent state in SQLite and WebSocket monitoring.

## Usage

1. Create `.env` from `.env.example` and fill API credentials and Telegram data.
2. Build and run via docker-compose:
   ```bash
   docker compose build
   docker compose up -d
   ```
3. Prometheus metrics available on port `9090`.
