from decimal import Decimal
import structlog
import httpx
from ..core.gateway import OKXGateway
from ..db.state import StateDB
from ..alerts.telegram import tg

log = structlog.get_logger()


class PerpExec:
    def __init__(self, gw: OKXGateway, db: StateDB, inst: str):
        self.gw, self.db, self.inst = gw, db, inst

    async def short(self, qty: Decimal):
        if qty <= 0:
            raise ValueError(f"Invalid quantity for short order: {qty}")
            
        log.info("PERP_SHORT_ATTEMPT", qty=qty, inst=self.inst)
        
        res = await self.gw.post_order(
            {
                "instId": self.inst,
                "side": "sell",
                "ordType": "market",
                "tdMode": "cross",
                "sz": str(qty),
            }
        )
        log.info("PERP_SHORT_OPEN", resp=res)
        await tg.send(f"Perp SHORT {qty}")
        spot, perp, loan = await self.db.get()
        await self.db.save(spot, perp - float(qty), loan)

    async def close_all(self):
        try:
            res = await self.gw.post(
                "/api/v5/trade/close-position",
                {"instId": self.inst, "mgnMode": "cross", "posSide": "short"},
            )
        except httpx.HTTPStatusError as e:
            await tg.send(f"❌ Perp CLOSE rejected: {e.response.text[:120]}")
            raise
        if not res or res[0].get("sCode") != "0":
            await tg.send(f"❌ Perp CLOSE failed: {res}")
            raise RuntimeError("orderRejected")
        log.info("PERP_CLOSE", resp=res)
        await tg.send("Perp short closed")
        spot, _, loan = await self.db.get()
        await self.db.save(spot, 0.0, loan)
