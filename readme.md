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

4. Persistent database files are stored in the `dbdata` Docker volume mounted at `src/db`.
5. The initial position size is derived from your current USDT balance
   automatically – the `EQUITY_USDT` variable is no longer required. You can
   tune exposure via the `BORROW_MULT` and `SPOT_RATIO` settings in `.env` which
   control the borrowing amount and what portion of funds is used for the
   spot/short legs.
## License

This project is licensed under the [MIT License](LICENSE).



