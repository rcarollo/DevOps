"""Métricas de performance para um conjunto de trades fechadas."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PerformanceSummary:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: float
    expectancy: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float
    max_drawdown: float
    max_drawdown_pct: float
    max_consecutive_wins: int
    max_consecutive_losses: int


def _empty_summary() -> PerformanceSummary:
    return PerformanceSummary(
        total_trades=0,
        wins=0,
        losses=0,
        win_rate=0.0,
        gross_profit=0.0,
        gross_loss=0.0,
        net_profit=0.0,
        profit_factor=0.0,
        expectancy=0.0,
        average_win=0.0,
        average_loss=0.0,
        largest_win=0.0,
        largest_loss=0.0,
        max_drawdown=0.0,
        max_drawdown_pct=0.0,
        max_consecutive_wins=0,
        max_consecutive_losses=0,
    )


def _max_streaks(is_win: pd.Series) -> tuple[int, int]:
    best_win = best_loss = current_win = current_loss = 0
    for win in is_win:
        if win:
            current_win += 1
            current_loss = 0
        else:
            current_loss += 1
            current_win = 0
        best_win = max(best_win, current_win)
        best_loss = max(best_loss, current_loss)
    return best_win, best_loss


def equity_curve(trades: pd.DataFrame, starting_balance: float = 0.0) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    ordered = trades.sort_values("close_time")
    curve = starting_balance + ordered["net_profit"].cumsum()
    curve.index = ordered["close_time"]
    return curve


def max_drawdown(trades: pd.DataFrame, starting_balance: float = 0.0) -> tuple[float, float]:
    curve = equity_curve(trades, starting_balance)
    if curve.empty:
        return 0.0, 0.0
    running_max = curve.cummax()
    drawdown = curve - running_max
    with np.errstate(invalid="ignore", divide="ignore"):
        drawdown_pct = drawdown / running_max.replace(0, np.nan)
    pct_min = drawdown_pct.min()
    return float(drawdown.min()), float(pct_min * 100) if pd.notna(pct_min) else 0.0


def summarize(trades: pd.DataFrame, starting_balance: float = 0.0) -> PerformanceSummary:
    if trades.empty:
        return _empty_summary()

    ordered = trades.sort_values("close_time")
    wins = ordered[ordered["net_profit"] > 0]
    losses = ordered[ordered["net_profit"] <= 0]

    gross_profit = float(wins["net_profit"].sum())
    gross_loss = float(losses["net_profit"].sum())
    net_profit = float(ordered["net_profit"].sum())

    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else float("inf")
    win_rate = len(wins) / len(ordered) * 100
    average_win = float(wins["net_profit"].mean()) if not wins.empty else 0.0
    average_loss = float(losses["net_profit"].mean()) if not losses.empty else 0.0
    expectancy = (win_rate / 100 * average_win) + ((1 - win_rate / 100) * average_loss)

    dd_abs, dd_pct = max_drawdown(ordered, starting_balance)
    win_streak, loss_streak = _max_streaks(ordered["net_profit"] > 0)

    return PerformanceSummary(
        total_trades=len(ordered),
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net_profit,
        profit_factor=profit_factor,
        expectancy=expectancy,
        average_win=average_win,
        average_loss=average_loss,
        largest_win=float(ordered["net_profit"].max()),
        largest_loss=float(ordered["net_profit"].min()),
        max_drawdown=dd_abs,
        max_drawdown_pct=dd_pct,
        max_consecutive_wins=win_streak,
        max_consecutive_losses=loss_streak,
    )
