from decimal import Decimal
import structlog
import httpx
from ..core.gateway import OKXGateway
from ..db.state import StateDB
from ..alerts.telegram import tg

log = structlog.get_logger()


class SpotExec:
    def __init__(self, gw: OKXGateway, db: StateDB, inst: str):
        self.gw, self.db, self.inst = gw, db, inst

    async def buy(self, qty: Decimal, loan_auto: bool = True):
        params = {
            "instId": self.inst,
            "side": "buy",
            "ordType": "market",
            "sz": str(qty),
            "tdMode": "cash",
        }
        if loan_auto:
            params["loanTrans"] = "auto"
        try:
            res = await self.gw.post("/api/v5/trade/order", params)
        except httpx.HTTPStatusError as e:
            await tg.send(f"❌ Spot BUY rejected: {e.response.text[:120]}")
            raise
        if not res or res[0].get("sCode") != "0":
            await tg.send(f"❌ Spot BUY failed: {res}")
            raise RuntimeError("orderRejected")
        log.info("SPOT_BUY", resp=res)
        await tg.send(f"Spot BUY {qty} {self.inst}")
        spot, perp, loan = await self.db.get()
        await self.db.save(spot + float(qty), perp, loan)

    async def sell(self, qty: Decimal):
        try:
            res = await self.gw.post(
                "/api/v5/trade/order",
                {
                    "instId": self.inst,
                    "side": "sell",
                    "ordType": "market",
                    "sz": str(qty),
                    "tdMode": "cash",
                    "loanTrans": "auto",
                },
            )
        except httpx.HTTPStatusError as e:
            await tg.send(f"❌ Spot SELL rejected: {e.response.text[:120]}")
            raise
        if not res or res[0].get("sCode") != "0":
            await tg.send(f"❌ Spot SELL failed: {res}")
            raise RuntimeError("orderRejected")
        log.info("SPOT_SELL", resp=res)
        await tg.send(f"Spot SELL {qty}")
        spot, perp, loan = await self.db.get()
        await self.db.save(spot - float(qty), perp, loan)
