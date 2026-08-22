"""Quebras de performance por horário, dia da semana, par e duração."""
from __future__ import annotations

import pandas as pd

WEEKDAY_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _aggregate(trades: pd.DataFrame, group_col: str) -> pd.DataFrame:
    df = trades.copy()
    df["is_win"] = df["net_profit"] > 0
    grouped = df.groupby(group_col, observed=True)
    result = grouped["net_profit"].agg(trades="count", net_profit="sum", avg_profit="mean")
    result["win_rate"] = grouped["is_win"].mean() * 100
    return result.reset_index()


def by_hour(trades: pd.DataFrame, time_col: str = "open_time") -> pd.DataFrame:
    df = trades.copy()
    df["hour"] = df[time_col].dt.hour
    return _aggregate(df, "hour").sort_values("hour").reset_index(drop=True)


def by_weekday(trades: pd.DataFrame, time_col: str = "open_time") -> pd.DataFrame:
    df = trades.copy()
    df["weekday_num"] = df[time_col].dt.weekday
    result = _aggregate(df, "weekday_num").sort_values("weekday_num")
    result["weekday"] = result["weekday_num"].map(lambda i: WEEKDAY_PT[int(i)])
    return result[["weekday_num", "weekday", "trades", "net_profit", "avg_profit", "win_rate"]].reset_index(
        drop=True
    )


def by_symbol(trades: pd.DataFrame) -> pd.DataFrame:
    return _aggregate(trades, "symbol").sort_values("net_profit", ascending=False).reset_index(drop=True)


def by_duration_bucket(trades: pd.DataFrame) -> pd.DataFrame:
    df = trades.copy()
    minutes = (df["close_time"] - df["open_time"]).dt.total_seconds() / 60
    bins = [-0.1, 5, 30, 240, float("inf")]
    labels = ["Scalp (<5 min)", "Curto (5-30 min)", "Médio (30 min-4h)", "Longo (>4h)"]
    df["duration_bucket"] = pd.cut(minutes, bins=bins, labels=labels)
    result = _aggregate(df, "duration_bucket")
    result["duration_bucket"] = pd.Categorical(result["duration_bucket"], categories=labels, ordered=True)
    return result.sort_values("duration_bucket").reset_index(drop=True)


def best_and_worst(trades: pd.DataFrame, n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = trades.sort_values("net_profit", ascending=False)
    best = ordered.head(n)
    worst = ordered.tail(min(n, len(ordered))).sort_values("net_profit")
    return best, worst
