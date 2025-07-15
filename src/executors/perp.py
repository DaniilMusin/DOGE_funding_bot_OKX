from decimal import Decimal
import structlog
import httpx
from ..core.gateway import OKXGateway
from ..db.state import StateDB
from ..alerts.telegram import tg
from ..utils import safe_float

log = structlog.get_logger()


class PerpExec:
    def __init__(self, gw: OKXGateway, db: StateDB, inst: str):
        self.gw, self.db, self.inst = gw, db, inst

    async def check_margin_requirements(self, qty: Decimal):
        """Check if we have sufficient margin for the short position."""
        try:
            # Get current account balance and risk info
            balance_data = await self.gw.get("/api/v5/account/balance")
            if not balance_data:
                return None
                
            account_info = balance_data[0]
            total_eq = safe_float(account_info.get("totalEq"))
            adj_eq = safe_float(account_info.get("adjEq"), total_eq)
            
            # Get current price for margin calculation
            ticker_data = await self.gw.get("/api/v5/market/ticker", {"instId": self.inst})
            if not ticker_data:
                return None
                
            mark_price = safe_float(ticker_data[0].get("last"))
            notional = float(qty) * mark_price
            
            # Rough margin requirement estimation (typically 10-20% for cross margin)
            estimated_margin = notional * 0.15  # Conservative 15% margin requirement
            
            return {
                "total_equity": total_eq,
                "adj_equity": adj_eq,
                "mark_price": mark_price,
                "notional": notional,
                "estimated_margin": estimated_margin,
                "margin_sufficient": adj_eq >= estimated_margin * 2,  # 2x buffer
            }
        except Exception as e:
            log.error("MARGIN_CHECK_ERROR", exc_info=e)
            return None

    async def short(self, qty: Decimal):
        if qty <= 0:
            raise ValueError(f"Invalid quantity for short order: {qty}")
            
        log.info("PERP_SHORT_ATTEMPT", qty=qty, inst=self.inst)
        
        # Check margin requirements before placing order
        margin_check = await self.check_margin_requirements(qty)
        if margin_check:
            log.info("PERP_MARGIN_CHECK", **margin_check)
            
            if not margin_check["margin_sufficient"]:
                error_msg = (f"Insufficient margin for short: "
                           f"Need ~{margin_check['estimated_margin']:.2f} USDT margin, "
                           f"Available equity: {margin_check['adj_equity']:.2f} USDT")
                await tg.send(f"❌ {error_msg}")
                raise RuntimeError(error_msg)
        
        try:
            res = await self.gw.post_order(
                {
                    "instId": self.inst,
                    "side": "sell",
                    "ordType": "market",
                    "tdMode": "cross",
                    "sz": str(qty),
                }
            )
            
            # Get execution price if available
            mark_price = margin_check["mark_price"] if margin_check else 0
            
            log.info("PERP_SHORT_SUCCESS", qty=qty, price=mark_price, resp=res)
            await tg.send(f"✅ Perp SHORT {qty} {self.inst} @ ${mark_price:.4f}")
            
            # Update state
            spot, perp, loan = await self.db.get()
            await self.db.save(spot, perp - float(qty), loan)
            return True
            
        except Exception as e:
            log.error("PERP_SHORT_ERROR", qty=qty, exc_info=e)
            await tg.send(f"❌ Perp short failed: {str(e)[:150]}")
            raise

    async def close_all(self):
        try:
            # First check current position
            _, perp_qty, _ = await self.db.get()
            if perp_qty >= 0:
                log.warning("NO_SHORT_POSITION", perp_qty=perp_qty)
                await tg.send("⚠️ No short position to close")
                return True
            
            res = await self.gw.post(
                "/api/v5/trade/close-position",
                {"instId": self.inst, "mgnMode": "cross", "posSide": "short"},
            )
            
            if not res or res[0].get("sCode") != "0":
                await tg.send(f"❌ Perp CLOSE failed: {res}")
                raise RuntimeError("orderRejected")
                
            log.info("PERP_CLOSE_SUCCESS", resp=res)
            await tg.send("✅ Perp short closed")
            
            # Update state
            spot, _, loan = await self.db.get()
            await self.db.save(spot, 0.0, loan)
            return True
            
        except httpx.HTTPStatusError as e:
            await tg.send(f"❌ Perp CLOSE rejected: {e.response.text[:120]}")
            raise
        except Exception as e:
            log.error("PERP_CLOSE_ERROR", exc_info=e)
            await tg.send(f"❌ Perp close failed: {str(e)[:150]}")
            raise

    async def get_position_info(self):
        """Get current perpetual position information."""
        try:
            positions = await self.gw.get("/api/v5/account/positions", {"instId": self.inst})
            for pos in positions:
                if pos["instId"] == self.inst and pos.get("posSide") == "short":
                    return {
                        "size": safe_float(pos.get("pos")),
                        "notional": safe_float(pos.get("notionalUsd")),
                        "unrealized_pnl": safe_float(pos.get("upl")),
                        "mark_price": safe_float(pos.get("markPx")),
                        "liq_price": safe_float(pos.get("liqPx")),
                    }
            return None
        except Exception as e:
            log.error("POSITION_INFO_ERROR", exc_info=e)
            return None
