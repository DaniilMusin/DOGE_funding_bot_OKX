import asyncio
import structlog
import time
import math
from decimal import Decimal
from .core.gateway import OKXGateway
from .db.state import StateDB
from .executors.perp import PerpExec
from .executors.spot import SpotExec
from .borrow import BorrowMgr
from .alerts.telegram import tg
from prometheus_client import Counter, Gauge

log = structlog.get_logger()
funding_gauge = Gauge("funding_rate", "next funding rate")
risk_gauge = Gauge("risk_ratio", "account risk ratio")

LIQ_THRESHOLD = 0.002  # 0.2%

class Monitors:
    def __init__(self, gw: OKXGateway, db: StateDB, pair_spot: str, pair_swap: str):
        self.gw, self.db = gw, db
        self.pair_spot, self.pair_swap = pair_spot, pair_swap
        self.flip_thr = 0.00001
        self.apr_exit = 0.08

    # ----- Funding via WebSocket -----
    async def funding_loop(self, perp: PerpExec, borrow: BorrowMgr):
        async for msg in self.gw.ws_private_stream("funding-rate"):
            d = msg["data"][0]
            if d["instId"] != self.pair_swap:
                continue
            next_rate = float(d["fundingRate"])
            funding_gauge.set(next_rate)
            if next_rate <= self.flip_thr:
                await tg.send(f"Funding flip {next_rate:.5%} – closing legs.")
                await perp.close_all()
                await borrow.repay_all()

    # ----- Risk ratio via WS -----
    async def risk_loop(self):
        async for msg in self.gw.ws_private_stream("account"):
            rr = float(msg["data"][0]["riskRatio"])
            risk_gauge.set(rr)
            if rr >= 0.9:
                await tg.send(f"EMERGENCY riskRatio {rr:.2f} > 0.9 – manual action required")

    # ----- APR poll -----
    async def apr_poll(self, borrow: BorrowMgr, perp: PerpExec):
        while True:
            data = await self.gw.get("/api/v5/account/max-loan", {"ccy": "USDT"})
            apr = float(data[0]["interestRate"])
            if apr >= self.apr_exit:
                await tg.send(f"APR {apr:.2%} > {self.apr_exit:.2%} – exit carry")
                await perp.close_all()
                await borrow.repay_all()
            await asyncio.sleep(600)

    # ----- Liquidation guard -----
    async def liq_loop(self, perp: PerpExec, borrow: BorrowMgr):
        """Emergency close if mark price approaches liquidation price."""
        async for msg in self.gw.ws_private_stream("positions"):
            p = msg["data"][0]
            if p["instId"] != self.pair_swap or p.get("posSide") != "short":
                continue
            liq_px = float(p["liqPx"])
            mark_px = float(p["markPx"])
            if liq_px == 0:
                continue
            gap = (liq_px - mark_px) / mark_px
            if gap <= LIQ_THRESHOLD:
                await tg.send(
                    f"‼️ Mark {mark_px} ≈ Liq {liq_px} ({gap:.3%}). Closing legs to avoid liquidation."
                )
                await perp.close_all()
                await borrow.repay_all()
