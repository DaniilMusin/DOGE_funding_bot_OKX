import aiosqlite
import pathlib
import asyncio
from typing import Tuple

DB_PATH = pathlib.Path(__file__).parent / "state.db"

DDL = """
create table if not exists bot_state (
    id integer primary key check (id = 1),
    spot_qty     real not null default 0,
    perp_qty     real not null default 0,
    loan_usdt    real not null default 0
);
insert or ignore into bot_state (id) values (1);
create table if not exists equity_ref (
    id integer primary key check (id = 1),
    eq_usd  real not null default 0,
    ts      integer not null default 0
);
insert or ignore into equity_ref (id) values (1);
"""

class StateDB:
    def __init__(self, path: pathlib.Path = DB_PATH):
        self.path = path
        self._lock = asyncio.Lock()

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(DDL)
            await db.commit()

    async def get(self) -> Tuple[float, float, float]:
        async with self._lock, aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "select spot_qty, perp_qty, "
                "loan_usdt from bot_state where id=1"
            )
            row = await cursor.fetchone()
            if not row:
                # Return default values if no state exists
                return (0.0, 0.0, 0.0)
            return row  # (spot, perp, loan)

    async def save(self, spot: float, perp: float, loan: float):
        async with self._lock, aiosqlite.connect(self.path) as db:
            await db.execute(
                (
                    "update bot_state set spot_qty=?, perp_qty=?, "
                    "loan_usdt=? where id=1"
                ),
                (spot, perp, loan),
            )
            await db.commit()

    async def update_spot(self, delta: float):
        """Atomically update spot quantity by delta."""
        async with self._lock, aiosqlite.connect(self.path) as db:
            await db.execute(
                "update bot_state set spot_qty = spot_qty + ? where id=1",
                (delta,),
            )
            await db.commit()

    async def update_perp(self, delta: float):
        """Atomically update perp quantity by delta."""
        async with self._lock, aiosqlite.connect(self.path) as db:
            await db.execute(
                "update bot_state set perp_qty = perp_qty + ? where id=1",
                (delta,),
            )
            await db.commit()

    async def update_loan(self, delta: float):
        """Atomically update loan amount by delta."""
        async with self._lock, aiosqlite.connect(self.path) as db:
            await db.execute(
                "update bot_state set loan_usdt = loan_usdt + ? where id=1",
                (delta,),
            )
            await db.commit()

    async def get_eq_ref(self) -> Tuple[float, int]:
        async with self._lock, aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "select eq_usd, ts from equity_ref where id=1"
            )
            row = await cursor.fetchone()
            if not row:
                # Return default values if no reference exists
                return (0.0, 0)
            return row  # (equity, timestamp)

    async def save_eq_ref(self, eq_usd: float, ts: int):
        async with self._lock, aiosqlite.connect(self.path) as db:
            await db.execute(
                "update equity_ref set eq_usd=?, ts=? where id=1",
                (eq_usd, ts),
            )
            await db.commit()
