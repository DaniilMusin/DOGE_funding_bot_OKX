from decimal import Decimal
import structlog
from ..core.gateway import OKXGateway
from ..db.state import StateDB
from ..alerts.telegram import tg

log = structlog.get_logger()


class SpotExec:
    def __init__(self, gw: OKXGateway, db: StateDB, inst: str):
        self.gw, self.db, self.inst = gw, db, inst

    async def buy(self, qty: Decimal, loan_auto: bool = True):
        if qty <= 0:
            raise ValueError(f"Invalid quantity for buy order: {qty}")
            
        # Get current price to estimate required USDT
        ticker_data = await self.gw.get(
            "/api/v5/market/ticker",
            {"instId": self.inst},
        )
        if ticker_data:
            price = float(ticker_data[0]["last"])
            estimated_cost = float(qty) * price
            current_equity = await self.gw.get_equity()
            
            log.info("SPOT_BUY_CHECK", 
                    qty=qty, 
                    price=price, 
                    estimated_cost=estimated_cost, 
                    available=current_equity)
            
            if estimated_cost > current_equity * 0.98:  # 2% buffer
                await tg.send(f"⚠️ Potential insufficient balance: need ~{estimated_cost:.2f} USDT, have {current_equity:.2f}")
        
        params = {
            "instId": self.inst,
            "side": "buy",
            "ordType": "market",
            "sz": str(qty),
            "tdMode": "cash",
        }
        if loan_auto:
            params["loanTrans"] = "auto"
        res = await self.gw.post_order(params)
        log.info("SPOT_BUY", resp=res)
        await tg.send(f"Spot BUY {qty} {self.inst}")
        spot, perp, loan = await self.db.get()
        await self.db.save(spot + float(qty), perp, loan)

    async def sell(self, qty: Decimal):
        res = await self.gw.post_order(
            {
                "instId": self.inst,
                "side": "sell",
                "ordType": "market",
                "sz": str(qty),
                "tdMode": "cash",
                "loanTrans": "auto",
            }
        )
        log.info("SPOT_SELL", resp=res)
        await tg.send(f"Spot SELL {qty}")
        spot, perp, loan = await self.db.get()
        await self.db.save(spot - float(qty), perp, loan)
