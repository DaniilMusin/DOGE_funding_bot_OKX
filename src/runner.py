import asyncio
import structlog
from decimal import Decimal
import math
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

async def init_positions(
    spot: SpotExec,
    perp: PerpExec,
    borrow: BorrowMgr,
    db: StateDB,
) -> None:
    spot_qty, perp_qty, loan = await db.get()
    if spot_qty > 0 and perp_qty < 0:
        log.info("STATE_RESTORED", spot=spot_qty, perp=perp_qty, loan=loan)
        return
    
    # fresh start
    try:
        # Fetch current USDT equity from the account instead of relying on
        # a fixed environment variable. This prevents order size errors when
        # the available balance differs from the preset value.
        initial_equity = await spot.gw.get_equity()
        ticker_data = await spot.gw.get(
            "/api/v5/market/ticker",
            {"instId": PAIR_SPOT},
        )
        if not ticker_data:
            raise RuntimeError("No ticker data received")
        
        price = float(ticker_data[0]["last"])
        if price <= 0:
            raise RuntimeError(f"Invalid price received: {price}")
            
        loan_amt = initial_equity * 2
        await borrow.borrow(loan_amt)
        
        # Re-fetch equity after borrowing to ensure we have accurate available balance
        current_equity = await spot.gw.get_equity()
        log.info("EQUITY_CHECK", initial=initial_equity, after_borrow=current_equity, loan=loan_amt)
        
        # Use 95% of available balance to account for any margin requirements
        safe_balance = current_equity * 0.95
        spot_target = safe_balance / price
        # OKX spot trades DOGE in integer lots, floor to avoid rejected orders
        adjusted_target = math.floor(spot_target)
        
        if adjusted_target <= 0:
            raise RuntimeError(f"Insufficient balance for trading. Available: {safe_balance} USDT, Price: {price}")
            
        await spot.buy(Decimal(adjusted_target), loan_auto=False)
        await perp.short(Decimal(adjusted_target))
        log.info(
            "INIT_COMPLETE",
            initial_equity=initial_equity,
            current_equity=current_equity,
            price=price,
            spot_target=adjusted_target,
        )
    except Exception as e:
        log.error("INIT_FAILED", exc_info=e)
        await tg.send(f"❌ Initialization failed: {str(e)[:150]}")
        raise

async def main():
    gw = OKXGateway()
    db = StateDB()
    await db.init()

    spot_exec = SpotExec(gw, db, PAIR_SPOT)
    perp_exec = PerpExec(gw, db, PAIR_SWAP)
    borrow = BorrowMgr(gw, db)

    try:
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
    except Exception as e:
        log.error("MAIN_ERROR", exc_info=e)
        await tg.send(f"❌ Bot crashed: {str(e)[:200]}")
        raise
    finally:
        # Clean up resources
        await gw.close()
        log.info("CLEANUP_COMPLETE")


def cli():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
