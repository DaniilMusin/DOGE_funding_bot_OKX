import asyncio
import structlog
from decimal import Decimal
from .core.gateway import OKXGateway
from .db.state import StateDB
from .executors.perp import PerpExec
from .executors.spot import SpotExec
from .alerts.telegram import tg
from prometheus_client import Gauge
from . import config

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
        self.thr = config.REBALANCE_DELTA_THRESHOLD

    async def check_rebalance_feasibility(self, imbalance: float, spot_qty: float):
        """Check if we can safely execute the rebalance operation."""
        try:
            if imbalance < 0:  # Need to close some short
                return True  # Closing positions is always safe
            
            # Need to add more short - check margin
            current_equity = await self.gw.get_equity()
            ticker_data = await self.gw.get(
                "/api/v5/market/ticker",
                {"instId": self.perp_exec.inst},
            )
            
            if not ticker_data:
                return False
                
            price = float(ticker_data[0]["last"])
            required_margin = abs(imbalance) * price * config.MARGIN_REQUIREMENT_ESTIMATE

            if current_equity < required_margin * config.REBALANCE_MARGIN_BUFFER:
                await tg.send(f"⚠️ Insufficient margin for rebalance. Need ~{required_margin:.2f}, have {current_equity:.2f}")
                return False
                
            return True
        except Exception as e:
            log.error("REBALANCE_FEASIBILITY_ERROR", exc_info=e)
            return False

    async def safe_rebalance(self, imbalance: float, spot_qty: float):
        """Perform safe rebalancing with proper error handling."""
        try:
            if imbalance > 0:
                # Too much spot, need more short
                can_rebalance = await self.check_rebalance_feasibility(imbalance, spot_qty)
                if not can_rebalance:
                    await tg.send("⚠️ Skipping rebalance due to insufficient margin")
                    return False
                    
                await self.perp_exec.short(Decimal(abs(imbalance)))
                await tg.send(f"✅ Added short position: {abs(imbalance):.2f} DOGE")
                
            else:
                # Too much short, need to close some
                current_perp_qty = abs(imbalance)
                _, stored_perp_qty, _ = await self.db.get()
                
                if abs(stored_perp_qty) < current_perp_qty:
                    # Don't try to close more than we have
                    current_perp_qty = abs(stored_perp_qty)
                
                if current_perp_qty > spot_qty * config.REBALANCE_THRESHOLD_MULTIPLIER:
                    # If we need to close too much, close all and re-establish
                    await self.perp_exec.close_all()
                    await asyncio.sleep(2)  # Brief pause
                    
                    if spot_qty > 0:
                        can_rebalance = await self.check_rebalance_feasibility(spot_qty, spot_qty)
                        if can_rebalance:
                            await self.perp_exec.short(Decimal(spot_qty))
                            await tg.send(f"✅ Re-established short position: {spot_qty:.2f} DOGE")
                        else:
                            await tg.send("⚠️ Could not re-establish short position due to insufficient margin")
                else:
                    # Partial close not easily supported, close all and re-establish
                    await self.perp_exec.close_all()
                    await asyncio.sleep(2)
                    
                    remaining_short = spot_qty
                    if remaining_short > 0:
                        can_rebalance = await self.check_rebalance_feasibility(remaining_short, spot_qty)
                        if can_rebalance:
                            await self.perp_exec.short(Decimal(remaining_short))
                            await tg.send(f"✅ Adjusted short position: {remaining_short:.2f} DOGE")
                        else:
                            await tg.send("⚠️ Could not adjust short position due to insufficient margin")
            
            return True
            
        except Exception as e:
            log.error("SAFE_REBALANCE_ERROR", exc_info=e)
            await tg.send(f"❌ Rebalance failed: {str(e)[:150]}")
            return False

    async def run(self):
        while True:
            try:
                spot, perp, _ = await self.db.get()
                if spot == 0 or abs(spot) < config.MIN_POSITION_SIZE:
                    await asyncio.sleep(config.REBALANCE_LOOP_INTERVAL)
                    continue

                delta = abs(spot + perp) / abs(spot) if abs(spot) > 0 else 0
                delta_gauge.set(delta)
                
                if delta >= self.thr:
                    log.info("REBALANCE_TRIGGERED", spot=spot, perp=perp, delta=delta, threshold=self.thr)
                    await tg.send(f"🔄 Δ {delta:.2%} > {self.thr:.2%} – rebalancing")
                    
                    # Calculate imbalance
                    imbalance = spot + perp  # positive = excess spot, negative = excess short
                    
                    if abs(imbalance) > spot * self.thr:
                        success = await self.safe_rebalance(imbalance, spot)
                        if success:
                            # Verify the rebalance worked
                            new_spot, new_perp, _ = await self.db.get()
                            new_delta = abs(new_spot + new_perp) / new_spot if new_spot > 0 else 0
                            await tg.send(f"✅ Rebalance complete. New delta: {new_delta:.2%}")
                        else:
                            await tg.send("❌ Rebalance failed - will retry next cycle")
                            
            except Exception as e:
                log.error("REBALANCE_LOOP_ERROR", exc_info=e)
                await tg.send(f"❌ Rebalance loop error: {str(e)[:150]}")

            await asyncio.sleep(config.REBALANCE_LOOP_INTERVAL)
