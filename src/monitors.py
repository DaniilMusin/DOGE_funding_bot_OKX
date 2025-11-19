import asyncio
import os
import structlog
import time
from decimal import Decimal
from .core.gateway import OKXGateway
from .db.state import StateDB
from .executors.perp import PerpExec
from .executors.spot import SpotExec
from .borrow import BorrowMgr
from .alerts.telegram import tg
from prometheus_client import Gauge
from . import config

log = structlog.get_logger()
funding_gauge = Gauge("funding_rate", "next funding rate")
risk_gauge = Gauge("risk_ratio", "account risk ratio")
liq_gap_gauge = Gauge(
    "liq_gap",
    "Distance (pct) from mark price to liquidation price",
)

class Monitors:
    def __init__(
        self, gw: OKXGateway, db: StateDB, pair_spot: str, pair_swap: str
    ) -> None:
        self.gw, self.db = gw, db
        self.pair_spot, self.pair_swap = pair_spot, pair_swap
        self.flip_thr = config.FUNDING_FLIP_THRESHOLD
        self.apr_exit = config.APR_EXIT_THRESHOLD

    async def safe_close_all_positions(self, spot_exec, perp_exec: PerpExec, borrow_mgr: BorrowMgr):
        """Close all positions in the correct order to avoid liquidation risk.

        Correct order:
        1. Sell spot position (converts DOGE to USDT)
        2. Repay loan (reduces liability)
        3. Close perp short (closes hedge)

        This ensures we don't have unhedged exposure during the process.
        """
        try:
            # Step 1: Sell spot position
            spot_qty, perp_qty, loan = await self.db.get()
            if spot_qty > 0:
                from decimal import Decimal
                await spot_exec.sell(Decimal(spot_qty))
                log.info("SAFE_CLOSE_SPOT_SOLD", qty=spot_qty)

            # Step 2: Repay loan
            if loan > 0:
                await borrow_mgr.repay_all()
                log.info("SAFE_CLOSE_LOAN_REPAID", amt=loan)

            # Step 3: Close perp short
            if perp_qty < 0:
                await perp_exec.close_all()
                log.info("SAFE_CLOSE_PERP_CLOSED", qty=perp_qty)

            return True
        except Exception as e:
            log.error("SAFE_CLOSE_ERROR", exc_info=e)
            await tg.send(f"❌ Safe close failed: {str(e)[:150]}")
            return False

    # ----- Funding via WebSocket -----
    async def funding_loop(self, spot_exec, perp: PerpExec, borrow: BorrowMgr):
        async for msg in self.gw.ws_private_stream(
            "funding-rate", self.pair_swap
        ):
            if "data" not in msg or not msg["data"] or len(msg["data"]) == 0:
                log.warning("FUNDING_EMPTY_DATA", msg=msg)
                continue
            d = msg["data"][0]
            if d.get("instId") != self.pair_swap:
                continue
            next_rate = float(d.get("fundingRate", 0))
            funding_gauge.set(next_rate)
            if next_rate <= self.flip_thr:
                await tg.send(f"Funding flip {next_rate:.5%} – closing legs.")
                await self.safe_close_all_positions(spot_exec, perp, borrow)

    # ----- Risk ratio via WS -----
    async def risk_loop(self):
        async for msg in self.gw.ws_private_stream("account"):
            if "data" not in msg or not msg["data"] or len(msg["data"]) == 0:
                log.warning("RISK_EMPTY_DATA", msg=msg)
                continue
            if "riskRatio" not in msg["data"][0]:
                log.warning("RISK_NO_RATIO", msg=msg)
                continue
            rr = float(msg["data"][0]["riskRatio"])
            risk_gauge.set(rr)
            if rr >= config.RISK_RATIO_WARNING:
                await tg.send(
                    (
                        f"EMERGENCY riskRatio {rr:.2f} > 0.9 – "
                        "manual action required"
                    )
                )

    # ----- APR poll -----
    async def apr_poll(self, spot_exec, borrow: BorrowMgr, perp: PerpExec):
        while True:
            try:
                data = await self.gw.get(
                    "/api/v5/account/max-loan",
                    {"ccy": "USDT"},
                )
                if not data or len(data) == 0:
                    log.warning("APR_EMPTY_DATA")
                    await asyncio.sleep(config.APR_POLL_INTERVAL)
                    continue
                apr = float(data[0].get("interestRate", 0))
                if apr >= self.apr_exit:
                    await tg.send(
                        f"APR {apr:.2%} > {self.apr_exit:.2%} – exit carry"
                    )
                    await self.safe_close_all_positions(spot_exec, perp, borrow)
            except Exception as e:
                log.error("APR_POLL_ERROR", exc_info=e)
            await asyncio.sleep(config.APR_POLL_INTERVAL)

    # ----- Liquidation guard -----
    async def liq_loop(self, spot_exec, perp: PerpExec, borrow: BorrowMgr):
        """Emergency close if mark price approaches liquidation price."""
        async for msg in self.gw.ws_private_stream(
            "positions", self.pair_swap
        ):
            if "data" not in msg or not msg["data"] or len(msg["data"]) == 0:
                log.warning("LIQ_EMPTY_DATA", msg=msg)
                continue
            p = msg["data"][0]
            if p.get("instId") != self.pair_swap or p.get("posSide") != "short":
                continue
            liq_px = float(p.get("liqPx", 0))
            mark_px = float(p.get("markPx", 0))
            if liq_px == 0 or mark_px == 0:
                continue
            gap = (liq_px - mark_px) / mark_px
            liq_gap_gauge.set(gap)
            if gap <= config.LIQUIDATION_THRESHOLD:
                await tg.send(
                    (
                        f"‼️ Mark {mark_px} ≈ Liq {liq_px} ({gap:.3%}). "
                        "Closing legs to avoid liquidation."
                    )
                )
                await self.safe_close_all_positions(spot_exec, perp, borrow)
                state = await self.gw.get("/api/v5/account/risk-state")
                if not state or len(state) == 0:
                    log.warning("RISK_STATE_EMPTY")
                    continue
                rr = float(state[0].get("riskRatio", 0))
                if rr >= config.RISK_RATIO_DELEVER:
                    spot_qty, _, _ = await self.db.get()
                    cut_qty = spot_qty * config.DELEVER_CUT_RATIO
                    if cut_qty > 0:
                        await tg.send(
                            (
                                f"RiskRatio {rr:.2f} – selling {cut_qty:.0f} "
                                "DOGE to de-leverage"
                            )
                        )
                        spot_exec = SpotExec(self.gw, self.db, self.pair_spot)
                        await spot_exec.sell(Decimal(cut_qty))

    # ----- Daily PnL stop -----
    async def pnl_guard(self):
        while True:
            eq = await self.gw.get_equity()
            ref, ts = await self.db.get_eq_ref()
            now = int(time.time())
            if ref == 0 or now - ts >= config.EQUITY_REF_RESET_INTERVAL:
                await self.db.save_eq_ref(eq, now)
            else:
                if ref > 0:  # Avoid division by zero
                    drop = (ref - eq) / ref
                    if drop >= config.PNL_STOP_THRESHOLD:
                        await tg.send(
                            f"‼️ Equity drop {drop:.2%} in 24h – pausing bot"
                        )
                        raise SystemExit("PNL stop")
            await asyncio.sleep(config.PNL_GUARD_INTERVAL)
