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
        # Get initial account state
        initial_equity = await spot.gw.get_equity()
        log.info("INIT_START", initial_equity=initial_equity)
        
        # Calculate maximum safe loan based on available quota and balance
        max_safe_loan = await borrow.calculate_safe_loan(target_multiplier=2.0, safety_factor=0.85)
        
        if max_safe_loan <= 0:
            raise RuntimeError("No borrowing capacity available. Check account balance and loan quota.")
        
        # Attempt to borrow the calculated safe amount
        borrow_success = await borrow.borrow(max_safe_loan)
        if not borrow_success:
            # If borrowing failed, try with smaller amount
            max_safe_loan = await borrow.calculate_safe_loan(target_multiplier=1.5, safety_factor=0.7)
            if max_safe_loan > 0:
                borrow_success = await borrow.borrow(max_safe_loan)
            
            if not borrow_success:
                raise RuntimeError("Failed to secure any loan. Check account status and available quota.")
        
        # Get current ticker data
        ticker_data = await spot.gw.get(
            "/api/v5/market/ticker",
            {"instId": PAIR_SPOT},
        )
        if not ticker_data:
            raise RuntimeError("No ticker data received")
        
        price = float(ticker_data[0]["last"])
        if price <= 0:
            raise RuntimeError(f"Invalid price received: {price}")
        
        # Re-fetch equity after borrowing to get accurate available balance
        current_equity = await spot.gw.get_equity()
        log.info("EQUITY_AFTER_BORROW", 
                initial=initial_equity, 
                after_borrow=current_equity, 
                loan=max_safe_loan,
                price=price)
        
        # Calculate position size with multiple safety factors
        available_for_trading = current_equity * 0.92  # Keep 8% buffer for fees and margin
        spot_target_raw = available_for_trading / price
        
        # Round down to avoid fractional shares and ensure we don't exceed balance
        spot_target = math.floor(spot_target_raw)
        
        if spot_target <= 0:
            raise RuntimeError(f"Insufficient balance for trading. Available: {available_for_trading:.2f} USDT, Price: {price}, Target: {spot_target_raw:.2f}")
        
        # Verify we have enough balance for the calculated position
        required_usdt = spot_target * price
        if required_usdt > current_equity * 0.95:
            # Further reduce position size if needed
            spot_target = math.floor((current_equity * 0.9) / price)
            log.warning("POSITION_REDUCED", 
                       original_target=math.floor(spot_target_raw),
                       reduced_target=spot_target,
                       reason="insufficient_balance")
        
        if spot_target <= 0:
            raise RuntimeError(f"Position size too small after safety adjustments. Equity: {current_equity}, Price: {price}")
        
        # Execute trades with error handling
        log.info("EXECUTING_TRADES", spot_target=spot_target, required_usdt=spot_target * price)
        
        await spot.buy(Decimal(spot_target), loan_auto=False)
        await perp.short(Decimal(spot_target))
        
        log.info(
            "INIT_COMPLETE",
            initial_equity=initial_equity,
            final_equity=current_equity,
            loan_amount=max_safe_loan,
            price=price,
            spot_position=spot_target,
            position_value=spot_target * price,
        )
        await tg.send(f"✅ Bot initialized: {spot_target} DOGE @ ${price:.4f}, Loan: ${max_safe_loan:.2f}")
        
    except Exception as e:
        log.error("INIT_FAILED", exc_info=e)
        await tg.send(f"❌ Initialization failed: {str(e)[:200]}")
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
