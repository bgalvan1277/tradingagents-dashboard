"""Quick fix: update CRWV ticker name from 'CrowdStrike Holdings' to 'CoreWeave'."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from sqlalchemy import select, update
from app.database import async_session
from app.models import Ticker


async def fix():
    async with async_session() as db:
        result = await db.execute(select(Ticker).where(Ticker.symbol == "CRWV"))
        ticker = result.scalar_one_or_none()
        if ticker:
            old_name = ticker.name
            ticker.name = "CoreWeave"
            await db.commit()
            print(f"Updated CRWV: '{old_name}' -> 'CoreWeave'")
        else:
            print("CRWV ticker not found")


if __name__ == "__main__":
    asyncio.run(fix())
