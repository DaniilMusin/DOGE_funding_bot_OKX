from decimal import Decimal
import structlog
from ..core.gateway import OKXGateway
from ..db.state import StateDB
from ..alerts.telegram import tg
from ..utils import safe_float

log = structlog.get_logger()


class SpotExec:
    def __init__(self, gw: OKXGateway, db: StateDB, inst: str):
        self.gw, self.db, self.inst = gw, db, inst

    async def get_detailed_balance_check(self, required_usdt: float):
        """Get detailed balance information to validate if we can execute the order."""
        try:
            # Get current account balance
            balance_data = await self.gw.get("/api/v5/account/balance", {"ccy": "USDT"})
            if not balance_data:
                return None
                
            balance_info = balance_data[0]
            usdt_details = None
            
            # Find USDT details
            for detail in balance_info.get("details", []):
                if detail.get("ccy") == "USDT":
                    usdt_details = detail
                    break
            
            if not usdt_details:
                return None
            
            return {
                "totalEq": safe_float(balance_info.get("totalEq")),
                "availEq": safe_float(usdt_details.get("availEq")),
                "cashBal": safe_float(usdt_details.get("cashBal")),
                "frozenBal": safe_float(usdt_details.get("frozenBal")),
                "ordFrozen": safe_float(usdt_details.get("ordFrozen")),
                "liab": safe_float(usdt_details.get("liab")),
                "maxLoan": safe_float(usdt_details.get("maxLoan")),
                "required": required_usdt,
                "can_execute": safe_float(usdt_details.get("availEq")) >= required_usdt * 1.05  # 5% buffer
            }
        except Exception as e:
            log.error("BALANCE_CHECK_ERROR", exc_info=e)
            return None

    async def buy(self, qty: Decimal, loan_auto: bool = True):
        if qty <= 0:
            raise ValueError(f"Invalid quantity for buy order: {qty}")
            
        # Get current price to estimate required USDT
        ticker_data = await self.gw.get(
            "/api/v5/market/ticker",
            {"instId": self.inst},
        )
        if not ticker_data:
            raise RuntimeError("Failed to get ticker data")
            
        price = safe_float(ticker_data[0].get("last"))
        estimated_cost = float(qty) * price
        
        # Get detailed balance check
        balance_check = await self.get_detailed_balance_check(estimated_cost)
        
        if balance_check:
            log.info("SPOT_BUY_BALANCE_CHECK", 
                    qty=qty, 
                    price=price, 
                    estimated_cost=estimated_cost,
                    **balance_check)
            
            if not balance_check["can_execute"]:
                error_msg = (f"Insufficient balance for spot buy: "
                           f"Need {estimated_cost:.2f} USDT, "
                           f"Available: {balance_check['availEq']:.2f} USDT, "
                           f"Total Equity: {balance_check['totalEq']:.2f} USDT")
                await tg.send(f"❌ {error_msg}")
                raise RuntimeError(error_msg)
        else:
            # Fallback check with basic equity
            current_equity = await self.gw.get_equity()
            log.info("SPOT_BUY_BASIC_CHECK", 
                    qty=qty, 
                    price=price, 
                    estimated_cost=estimated_cost, 
                    available=current_equity)
            
            if estimated_cost > current_equity * 0.95:  # 5% buffer
                error_msg = (f"Potential insufficient balance: "
                           f"need ~{estimated_cost:.2f} USDT, "
                           f"have {current_equity:.2f} USDT equity")
                await tg.send(f"⚠️ {error_msg}")
        
        # Check max allowed size from API
        max_info = await self.gw.get_max_size(self.inst, "cash")
        if max_info and max_info.get("maxBuy"):
            max_buy = Decimal(str(max_info["maxBuy"]))
            if qty > max_buy:
                await tg.send(
                    f"⚠️ Reducing buy size from {qty} to {max_buy} due to max-size"
                )
                qty = max_buy

        # Prepare order parameters
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
            res = await self.gw.post_order(params)
            log.info("SPOT_BUY_SUCCESS", qty=qty, price=price, resp=res)
            await tg.send(f"✅ Spot BUY {qty} {self.inst} @ ${price:.4f}")
            
            # Update state
            spot, perp, loan = await self.db.get()
            await self.db.save(spot + float(qty), perp, loan)
            return True
            
        except Exception as e:
            log.error("SPOT_BUY_ERROR", qty=qty, price=price, exc_info=e)
            await tg.send(f"❌ Spot buy failed: {str(e)[:150]}")
            raise

    async def sell(self, qty: Decimal):
        if qty <= 0:
            raise ValueError(f"Invalid quantity for sell order: {qty}")
            
        # Check if we have enough balance to sell
        spot_qty, _, _ = await self.db.get()
        if float(qty) > spot_qty:
            await tg.send(f"⚠️ Trying to sell {qty} but only have {spot_qty} in position")
            # Adjust quantity to available balance
            qty = Decimal(spot_qty)
            if qty <= 0:
                raise RuntimeError("No spot position to sell")
        
        try:
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
            log.info("SPOT_SELL_SUCCESS", qty=qty, resp=res)
            
            # Get current price for reporting
            ticker_data = await self.gw.get("/api/v5/market/ticker", {"instId": self.inst})
            price = safe_float(ticker_data[0].get("last")) if ticker_data else 0
            
            await tg.send(f"✅ Spot SELL {qty} {self.inst} @ ${price:.4f}")
            
            # Update state
            spot, perp, loan = await self.db.get()
            await self.db.save(spot - float(qty), perp, loan)
            return True
            
        except Exception as e:
            log.error("SPOT_SELL_ERROR", qty=qty, exc_info=e)
            await tg.send(f"❌ Spot sell failed: {str(e)[:150]}")
            raise
