"""Seed the watchlist with initial tickers.

Run once after database setup:
    python scripts/seed_watchlist.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import async_session
from app.models import Ticker, WatchlistEntry


INITIAL_TICKERS = [
    {"symbol": "PLTR", "name": "Palantir Technologies", "category": "holdings"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "category": "holdings"},
    {"symbol": "CRWV", "name": "CrowdStrike Holdings", "category": "watching"},
    {"symbol": "SOUN", "name": "SoundHound AI", "category": "speculative"},
    {"symbol": "MU", "name": "Micron Technology", "category": "watching"},
    {"symbol": "BE", "name": "Bloom Energy", "category": "speculative"},
]


async def seed():
    async with async_session() as db:
        for i, data in enumerate(INITIAL_TICKERS):
            # Check if already exists
            existing = await db.execute(
                select(Ticker).where(Ticker.symbol == data["symbol"])
            )
            if existing.scalar_one_or_none():
                print(f"  {data['symbol']} already exists, skipping")
                continue

            # Create ticker
            ticker = Ticker(
                symbol=data["symbol"],
                name=data["name"],
                category=data["category"],
                active=True,
                model_tier="pro",
            )
            db.add(ticker)
            await db.flush()

            # Create watchlist entry
            wl = WatchlistEntry(
                ticker_id=ticker.id,
                position=i,
                group_name=data["category"],
                frequency="daily",
            )
            db.add(wl)
            print(f"  Added {data['symbol']} ({data['name']}) to {data['category']}")

        await db.commit()
        print("\nWatchlist seeded successfully.")


if __name__ == "__main__":
    print("Seeding watchlist...")
    asyncio.run(seed())
