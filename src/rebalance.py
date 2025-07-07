import asyncio
import structlog
from decimal import Decimal
from .core.gateway import OKXGateway
from .db.state import StateDB
from .executors.perp import PerpExec
from .executors.spot import SpotExec
from .alerts.telegram import tg
from prometheus_client import Gauge

log = structlog.get_logger()
delta_gauge = Gauge("delta_abs", "absolute delta doge")

class Rebalancer:
    def __init__(
        self,
        gw: OKXGateway,
        db: StateDB,
        spot_exec: SpotExec,
        perp_exec: PerpExec,
    ) -> None:
        self.gw, self.db, self.spot_exec, self.perp_exec = (
            gw,
            db,
            spot_exec,
            perp_exec,
        )
        self.thr = 0.01

    async def run(self):
        while True:
            spot, perp, _ = await self.db.get()
            if spot == 0:
                await asyncio.sleep(60)
                continue
            delta = abs(spot + perp) / spot
            delta_gauge.set(delta)
            if delta >= self.thr:
                await tg.send(f"Δ {delta:.2%} > {self.thr:.2%} – rebalance")
                if perp < -1e-6:
                    await self.perp_exec.short(Decimal(delta * spot))
                else:
                    await self.perp_exec.close_all()
            await asyncio.sleep(60)
