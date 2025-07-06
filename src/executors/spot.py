from decimal import Decimal
import structlog
import asyncio
from ..core.gateway import OKXGateway
from ..db.state import StateDB
from ..alerts.telegram import tg

log = structlog.get_logger()

class SpotExec:
    def __init__(self, gw: OKXGateway, db: StateDB, inst: str):
        self.gw, self.db, self.inst = gw, db, inst

    async def buy(self, qty: Decimal):
        px = "0"  # market
        res = await self.gw.post(
            "/api/v5/trade/order",
            {
                "instId": self.inst,
                "side": "buy",
                "ordType": "market",
                "sz": str(qty),
                "tdMode": "cash",
                "loanTrans": "auto",
            },
        )
        log.info("SPOT_BUY", resp=res)
        await tg.send(f"Spot BUY {qty} {self.inst}")
        spot, perp, loan = await self.db.get()
        await self.db.save(spot + float(qty), perp, loan)

    async def sell(self, qty: Decimal):
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
        log.info("SPOT_SELL", resp=res)
        await tg.send(f"Spot SELL {qty}")
        spot, perp, loan = await self.db.get()
        await self.db.save(spot - float(qty), perp, loan)
