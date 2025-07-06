import asyncio
import structlog
import os
from decimal import Decimal
from prometheus_client import start_http_server
from .core.gateway import OKXGateway
from .db.state import StateDB
from .executors.spot import SpotExec
from .executors.perp import PerpExec
from .borrow import BorrowMgr
from .monitors import Monitors
from .rebalance import Rebalancer
from .alerts.telegram import tg

structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger()

PAIR_SPOT = "DOGE-USDT"
PAIR_SWAP = "DOGE-USDT-SWAP"

async def init_positions(spot: SpotExec, perp: PerpExec, borrow: BorrowMgr, db: StateDB):
    spot_qty, perp_qty, loan = await db.get()
    if spot_qty > 0 and perp_qty < 0:
        log.info("STATE_RESTORED", spot=spot_qty, perp=perp_qty, loan=loan)
        return
    # fresh start
    equity = float(os.getenv("EQUITY_USDT", "1000"))
    price = float(
        (await spot.gw.get("/api/v5/market/ticker", {"instId": PAIR_SPOT}))[0]["last"]
    )
    loan_amt = equity * 2
    await borrow.borrow(loan_amt)
    spot_target = (equity + loan_amt) / price
    await spot.buy(Decimal(spot_target), loan_auto=False)
    await perp.short(Decimal(spot_target))

async def main():
    gw = OKXGateway()
    db = StateDB()
    await db.init()

    spot_exec = SpotExec(gw, db, PAIR_SPOT)
    perp_exec = PerpExec(gw, db, PAIR_SWAP)
    borrow = BorrowMgr(gw, db)

    await init_positions(spot_exec, perp_exec, borrow, db)

    mon = Monitors(gw, db, PAIR_SPOT, PAIR_SWAP)
    reb = Rebalancer(gw, db, spot_exec, perp_exec)

    start_http_server(9090)  # Prometheus

    tasks = [
        mon.funding_loop(perp_exec, borrow),
        mon.risk_loop(),
        mon.apr_poll(borrow, perp_exec),
        mon.liq_loop(perp_exec, borrow),
        mon.pnl_guard(),
        reb.run(),
    ]
    await tg.send("DOGE‑carry bot Started")
    await asyncio.gather(*tasks)


def cli():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
