import structlog
from .core.gateway import OKXGateway
from .db.state import StateDB
from .alerts.telegram import tg
from .utils import safe_float

log = structlog.get_logger()

class BorrowMgr:
    def __init__(self, gw: OKXGateway, db: StateDB):
        self.gw, self.db = gw, db

    async def get_max_loan_info(self, currency: str = "USDT"):
        """Get maximum loan information for a currency."""
        try:
            data = await self.gw.get(
                "/api/v5/account/max-loan",
                {"ccy": currency},
            )
            if data:
                d = data[0]
                return {
                    "maxLoan": safe_float(d.get("maxLoan")),
                    "loanQuota": safe_float(d.get("loanQuota")),
                    "usedQuota": safe_float(d.get("usedQuota")),
                    "availableQuota": safe_float(d.get("loanQuota")) - safe_float(d.get("usedQuota")),
                    "interestRate": safe_float(d.get("interestRate")),
                }
        except Exception as e:
            log.error("LOAN_INFO_ERROR", exc_info=e)
            await tg.send(f"⚠️ Failed to get loan info: {str(e)}")
        return None

    async def get_account_balance(self):
        """Get detailed account balance information."""
        try:
            data = await self.gw.get("/api/v5/account/balance", {"ccy": "USDT"})
            if data:
                balance_info = data[0]
                return {
                    "totalEq": safe_float(balance_info.get("totalEq")),
                    "adjEq": safe_float(balance_info.get("adjEq")),
                    "details": balance_info["details"][0] if balance_info.get("details") else {},
                }
        except Exception as e:
            log.error("BALANCE_INFO_ERROR", exc_info=e)
            await tg.send(f"⚠️ Failed to get balance info: {str(e)}")
        return None

    async def calculate_safe_loan(self, target_multiplier: float = 2.0, safety_factor: float = 0.9):
        """Calculate maximum safe loan amount based on available quota and balance."""
        loan_info = await self.get_max_loan_info()
        balance_info = await self.get_account_balance()
        
        if not loan_info or not balance_info:
            return 0.0
            
        current_equity = balance_info["totalEq"]
        available_quota = loan_info["availableQuota"]
        max_loan = loan_info["maxLoan"]
        
        # Calculate desired loan based on target multiplier
        desired_loan = current_equity * target_multiplier
        
        # Apply constraints
        max_safe_loan = min(
            desired_loan,
            available_quota * safety_factor,  # Don't use full quota
            max_loan * safety_factor,         # Don't use max allowed
        )
        
        log.info("LOAN_CALCULATION", 
                current_equity=current_equity,
                desired_loan=desired_loan,
                available_quota=available_quota,
                max_loan=max_loan,
                max_safe_loan=max_safe_loan)
        
        return max(0.0, max_safe_loan)

    async def borrow(self, usdt: float):
        if usdt <= 0:
            return False
            
        # Check if we can actually borrow this amount
        loan_info = await self.get_max_loan_info()
        if loan_info and usdt > loan_info["availableQuota"]:
            await tg.send(f"⚠️ Requested loan {usdt:.2f} USDT exceeds available quota {loan_info['availableQuota']:.2f}")
            return False
            
        try:
            await self.gw.post(
                "/api/v5/account/borrow-repay",
                {
                    "ccy": "USDT",
                    "amt": str(usdt),
                    "side": "borrow",
                    "loanType": "2",
                },
            )
            spot, perp, loan = await self.db.get()
            await self.db.save(spot, perp, loan + usdt)
            await tg.send(f"Borrowed {usdt} USDT")
            return True
        except Exception as e:
            log.error("BORROW_ERROR", amount=usdt, exc_info=e)
            await tg.send(f"❌ Borrow failed: {str(e)}")
            return False

    async def repay_all(self):
        try:
            await self.gw.post(
                "/api/v5/account/borrow-repay",
                {"ccy": "USDT", "side": "repay", "amt": ""},
            )
            spot, perp, _ = await self.db.get()
            await self.db.save(spot, perp, 0.0)
            await tg.send("Loan fully repaid")
            return True
        except Exception as e:
            log.error("REPAY_ERROR", exc_info=e)
            await tg.send(f"❌ Repay failed: {str(e)}")
            return False

    async def repay(self, usdt: float) -> bool:
        """Repay part of the outstanding loan."""
        if usdt <= 0:
            return True
        try:
            await self.gw.post(
                "/api/v5/account/borrow-repay",
                {"ccy": "USDT", "side": "repay", "amt": str(usdt)},
            )
            spot, perp, loan = await self.db.get()
            await self.db.save(spot, perp, max(loan - usdt, 0.0))
            await tg.send(f"Repaid {usdt:.2f} USDT")
            return True
        except Exception as e:
            log.error("REPAY_PART_ERROR", exc_info=e)
            await tg.send(f"❌ Repay failed: {str(e)}")
            return False
