import math

import pandas as pd

from src import metrics


def test_summarize_basic_counts(sample_trades):
    summary = metrics.summarize(sample_trades)
    assert summary.total_trades == 8
    assert summary.wins == 4
    assert summary.losses == 4
    assert summary.win_rate == 50.0


def test_summarize_profit_figures(sample_trades):
    summary = metrics.summarize(sample_trades)
    assert math.isclose(summary.gross_profit, 350.0)
    assert math.isclose(summary.gross_loss, -150.0)
    assert math.isclose(summary.net_profit, 200.0)
    assert math.isclose(summary.profit_factor, 350 / 150)
    assert math.isclose(summary.average_win, 87.5)
    assert math.isclose(summary.average_loss, -37.5)
    assert math.isclose(summary.expectancy, 25.0)


def test_summarize_streaks(sample_trades):
    summary = metrics.summarize(sample_trades)
    assert summary.max_consecutive_wins == 2
    assert summary.max_consecutive_losses == 2


def test_max_drawdown(sample_trades):
    dd_abs, dd_pct = metrics.max_drawdown(sample_trades)
    assert math.isclose(dd_abs, -100.0)
    assert math.isclose(dd_pct, -50.0)


def test_equity_curve_final_value_matches_net_profit(sample_trades):
    curve = metrics.equity_curve(sample_trades)
    assert math.isclose(curve.iloc[-1], 200.0)


def test_summarize_empty_returns_zeros():
    empty = pd.DataFrame(columns=sample_columns())
    summary = metrics.summarize(empty)
    assert summary.total_trades == 0
    assert summary.win_rate == 0.0
    assert summary.profit_factor == 0.0


def sample_columns():
    return [
        "ticket", "symbol", "type", "volume", "open_time", "close_time",
        "open_price", "close_price", "sl", "tp", "commission", "swap",
        "profit", "net_profit",
    ]
