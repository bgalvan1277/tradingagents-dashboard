"""SimTrader paper trading service.

Handles trade execution, position tracking, P&L calculation,
and performance metrics using live prices from yfinance.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

STARTING_CASH = Decimal("100000.00")


def _to_dec(value) -> Decimal:
    """Safely convert any numeric to Decimal(2)."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def get_live_price(symbol: str) -> Optional[Decimal]:
    """Fetch current market price via yfinance. Returns None on failure."""
    import asyncio
    import functools

    def _fetch():
        try:
            import yfinance as yf
            t = yf.Ticker(symbol)
            hist = t.history(period="1d")
            if hist.empty:
                return None
            return float(hist["Close"].iloc[-1])
        except Exception as e:
            logger.warning("yfinance price fetch failed for %s: %s", symbol, e)
            return None

    loop = asyncio.get_running_loop()
    price = await loop.run_in_executor(None, _fetch)
    return Decimal(str(price)).quantize(Decimal("0.0001")) if price else None


async def get_account(db: AsyncSession) -> dict:
    """Return account summary with cash balance and equity value."""
    row = (await db.execute(text("SELECT * FROM sim_account LIMIT 1"))).mappings().first()
    if not row:
        return {
            "starting_cash": STARTING_CASH,
            "cash_balance": STARTING_CASH,
            "inception_date": datetime.utcnow(),
        }
    return dict(row)


async def get_positions(db: AsyncSession, with_prices: bool = True) -> list[dict]:
    """Return all open positions. Optionally enriches with live prices and P&L."""
    rows = (await db.execute(
        text("SELECT * FROM sim_positions WHERE shares > 0 ORDER BY ticker_symbol")
    )).mappings().all()

    positions = []
    for r in rows:
        pos = dict(r)
        pos["avg_cost"] = _to_dec(pos["avg_cost"])
        pos["total_cost_basis"] = _to_dec(pos["total_cost_basis"])

        if with_prices:
            price = await get_live_price(pos["ticker_symbol"])
            if price:
                current_value = _to_dec(price * pos["shares"])
                pnl = current_value - pos["total_cost_basis"]
                pnl_pct = (pnl / pos["total_cost_basis"] * 100) if pos["total_cost_basis"] else Decimal("0")
                pos["current_price"] = _to_dec(price)
                pos["current_value"] = current_value
                pos["unrealized_pnl"] = pnl
                pos["unrealized_pnl_pct"] = pnl_pct.quantize(Decimal("0.01"))
            else:
                pos["current_price"] = pos["avg_cost"]
                pos["current_value"] = pos["total_cost_basis"]
                pos["unrealized_pnl"] = Decimal("0.00")
                pos["unrealized_pnl_pct"] = Decimal("0.00")

        positions.append(pos)
    return positions


async def get_portfolio_value(db: AsyncSession) -> dict:
    """Calculate total portfolio value: cash + positions equity."""
    account = await get_account(db)
    positions = await get_positions(db, with_prices=True)

    cash = _to_dec(account.get("cash_balance", STARTING_CASH))
    equity = sum(p.get("current_value", Decimal("0")) for p in positions)
    total = cash + equity
    starting = _to_dec(account.get("starting_cash", STARTING_CASH))
    total_pnl = total - starting
    total_pnl_pct = (total_pnl / starting * 100) if starting else Decimal("0")

    return {
        "cash": cash,
        "equity": equity,
        "total_value": total,
        "starting_cash": starting,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct.quantize(Decimal("0.01")),
        "positions_count": len(positions),
    }


async def execute_trade(
    db: AsyncSession,
    ticker_symbol: str,
    side: str,
    shares: int,
    run_id: Optional[int] = None,
    note: Optional[str] = None,
) -> dict:
    """Execute a simulated buy or sell at current market price.

    Returns dict with trade details or error message.
    """
    symbol = ticker_symbol.upper().strip()
    side = side.lower().strip()

    if side not in ("buy", "sell"):
        return {"error": "Side must be 'buy' or 'sell'"}
    if shares <= 0:
        return {"error": "Shares must be greater than 0"}

    # Get live price
    price = await get_live_price(symbol)
    if not price:
        return {"error": f"Could not fetch price for {symbol}. Verify the ticker is valid."}

    total_value = _to_dec(price * shares)

    if side == "buy":
        return await _execute_buy(db, symbol, shares, price, total_value, run_id, note)
    else:
        return await _execute_sell(db, symbol, shares, price, total_value, run_id, note)


async def _execute_buy(
    db: AsyncSession, symbol: str, shares: int, price: Decimal,
    total_value: Decimal, run_id: Optional[int], note: Optional[str]
) -> dict:
    """Process a buy order."""
    # Check cash
    account = await get_account(db)
    cash = _to_dec(account.get("cash_balance", 0))
    if total_value > cash:
        return {"error": f"Insufficient cash. Need ${total_value:,.2f}, have ${cash:,.2f}"}

    # Deduct cash
    await db.execute(text(
        "UPDATE sim_account SET cash_balance = cash_balance - :cost WHERE id = 1"
    ), {"cost": float(total_value)})

    # Update or create position
    existing = (await db.execute(
        text("SELECT * FROM sim_positions WHERE ticker_symbol = :s"),
        {"s": symbol}
    )).mappings().first()

    if existing:
        old_shares = existing["shares"]
        old_cost_basis = _to_dec(existing["total_cost_basis"])
        new_shares = old_shares + shares
        new_cost_basis = old_cost_basis + total_value
        new_avg = _to_dec(new_cost_basis / new_shares)
        await db.execute(text(
            "UPDATE sim_positions SET shares = :sh, avg_cost = :ac, "
            "total_cost_basis = :tcb WHERE ticker_symbol = :s"
        ), {"sh": new_shares, "ac": float(new_avg), "tcb": float(new_cost_basis), "s": symbol})
    else:
        avg = _to_dec(price)
        await db.execute(text(
            "INSERT INTO sim_positions (ticker_symbol, shares, avg_cost, total_cost_basis) "
            "VALUES (:s, :sh, :ac, :tcb)"
        ), {"s": symbol, "sh": shares, "ac": float(avg), "tcb": float(total_value)})

    # Log trade
    await db.execute(text(
        "INSERT INTO sim_trades (ticker_symbol, side, shares, price, total_value, run_id, note) "
        "VALUES (:s, 'buy', :sh, :p, :tv, :rid, :n)"
    ), {"s": symbol, "sh": shares, "p": float(price), "tv": float(total_value),
        "rid": run_id, "n": note})

    await db.commit()

    return {
        "success": True,
        "side": "buy",
        "ticker": symbol,
        "shares": shares,
        "price": price,
        "total": total_value,
    }


async def _execute_sell(
    db: AsyncSession, symbol: str, shares: int, price: Decimal,
    total_value: Decimal, run_id: Optional[int], note: Optional[str]
) -> dict:
    """Process a sell order."""
    existing = (await db.execute(
        text("SELECT * FROM sim_positions WHERE ticker_symbol = :s"),
        {"s": symbol}
    )).mappings().first()

    if not existing or existing["shares"] < shares:
        held = existing["shares"] if existing else 0
        return {"error": f"Insufficient shares. Trying to sell {shares}, hold {held}"}

    avg_cost = _to_dec(existing["avg_cost"])
    cost_basis_sold = _to_dec(avg_cost * shares)
    realized_pnl = total_value - cost_basis_sold

    # Add cash
    await db.execute(text(
        "UPDATE sim_account SET cash_balance = cash_balance + :proceeds WHERE id = 1"
    ), {"proceeds": float(total_value)})

    # Update position
    new_shares = existing["shares"] - shares
    if new_shares == 0:
        await db.execute(text("DELETE FROM sim_positions WHERE ticker_symbol = :s"), {"s": symbol})
    else:
        new_cost_basis = _to_dec(avg_cost * new_shares)
        await db.execute(text(
            "UPDATE sim_positions SET shares = :sh, total_cost_basis = :tcb WHERE ticker_symbol = :s"
        ), {"sh": new_shares, "tcb": float(new_cost_basis), "s": symbol})

    # Log trade
    await db.execute(text(
        "INSERT INTO sim_trades (ticker_symbol, side, shares, price, total_value, realized_pnl, run_id, note) "
        "VALUES (:s, 'sell', :sh, :p, :tv, :rpnl, :rid, :n)"
    ), {"s": symbol, "sh": shares, "p": float(price), "tv": float(total_value),
        "rpnl": float(realized_pnl), "rid": run_id, "n": note})

    await db.commit()

    return {
        "success": True,
        "side": "sell",
        "ticker": symbol,
        "shares": shares,
        "price": price,
        "total": total_value,
        "realized_pnl": realized_pnl,
    }


async def get_trade_history(db: AsyncSession, limit: int = 50) -> list[dict]:
    """Return recent trade history."""
    rows = (await db.execute(text(
        "SELECT t.*, r.ticker_symbol AS run_ticker, r.final_recommendation "
        "FROM sim_trades t LEFT JOIN runs r ON t.run_id = r.id "
        "ORDER BY t.executed_at DESC LIMIT :lim"
    ), {"lim": limit})).mappings().all()
    return [dict(r) for r in rows]


async def get_performance(db: AsyncSession) -> dict:
    """Calculate performance metrics across all trades."""
    trades = (await db.execute(text(
        "SELECT * FROM sim_trades ORDER BY executed_at"
    ))).mappings().all()

    sells = [t for t in trades if t["side"] == "sell" and t["realized_pnl"] is not None]
    total_trades = len(trades)
    total_sells = len(sells)

    if total_sells == 0:
        return {
            "total_trades": total_trades,
            "closed_trades": 0,
            "win_rate": Decimal("0"),
            "avg_gain": Decimal("0"),
            "avg_loss": Decimal("0"),
            "total_realized_pnl": Decimal("0"),
            "best_trade": None,
            "worst_trade": None,
        }

    wins = [s for s in sells if _to_dec(s["realized_pnl"]) > 0]
    losses = [s for s in sells if _to_dec(s["realized_pnl"]) <= 0]

    win_rate = _to_dec(Decimal(len(wins)) / Decimal(total_sells) * 100)
    avg_gain = _to_dec(sum(_to_dec(w["realized_pnl"]) for w in wins) / len(wins)) if wins else Decimal("0")
    avg_loss = _to_dec(sum(_to_dec(l["realized_pnl"]) for l in losses) / len(losses)) if losses else Decimal("0")
    total_realized = _to_dec(sum(_to_dec(s["realized_pnl"]) for s in sells))

    best = max(sells, key=lambda s: _to_dec(s["realized_pnl"]))
    worst = min(sells, key=lambda s: _to_dec(s["realized_pnl"]))

    return {
        "total_trades": total_trades,
        "closed_trades": total_sells,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": win_rate,
        "avg_gain": avg_gain,
        "avg_loss": avg_loss,
        "total_realized_pnl": total_realized,
        "best_trade": {"ticker": best["ticker_symbol"], "pnl": _to_dec(best["realized_pnl"])},
        "worst_trade": {"ticker": worst["ticker_symbol"], "pnl": _to_dec(worst["realized_pnl"])},
    }


async def reset_account(db: AsyncSession) -> dict:
    """Wipe all SimTrader data and restart with fresh $100K."""
    await db.execute(text("DELETE FROM sim_trades"))
    await db.execute(text("DELETE FROM sim_positions"))
    await db.execute(text(
        "UPDATE sim_account SET cash_balance = 100000.00, "
        "starting_cash = 100000.00, inception_date = NOW() WHERE id = 1"
    ))
    await db.commit()
    return {"success": True, "message": "Account reset to $100,000.00"}
