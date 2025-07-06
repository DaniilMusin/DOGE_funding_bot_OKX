import structlog
from .core.gateway import OKXGateway
from .db.state import StateDB
from .alerts.telegram import tg

log = structlog.get_logger()

class BorrowMgr:
    def __init__(self, gw: OKXGateway, db: StateDB):
        self.gw, self.db = gw, db

    async def borrow(self, usdt: float):
        if usdt <= 0:
            return
        await self.gw.post("/api/v5/account/borrow-repay", {"ccy": "USDT", "amt": str(usdt), "side": "borrow"})
        spot, perp, loan = await self.db.get()
        await self.db.save(spot, perp, loan + usdt)
        await tg.send(f"Borrowed {usdt} USDT")

    async def repay_all(self):
        await self.gw.post("/api/v5/account/borrow-repay", {"ccy": "USDT", "side": "repay", "amt": ""})
        spot, perp, _ = await self.db.get()
        await self.db.save(spot, perp, 0.0)
        await tg.send("Loan fully repaid")
