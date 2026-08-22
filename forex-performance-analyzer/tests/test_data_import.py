import io
import math

import pandas as pd
import pytest

from src.data_import import build_trades_from_deals, load_trades_from_csv


def _mt5_deal(position_id, ticket, symbol, deal_type, entry, time, price, volume, profit=0.0, commission=0.0, swap=0.0):
    return {
        "ticket": ticket,
        "position_id": position_id,
        "symbol": symbol,
        "type": deal_type,  # 0=buy, 1=sell, 2=balance
        "entry": entry,  # 0=in, 1=out
        "time": time,
        "price": price,
        "volume": volume,
        "profit": profit,
        "commission": commission,
        "swap": swap,
        "sl": 0.0,
        "tp": 0.0,
    }


def test_build_trades_from_deals_groups_open_and_close():
    t0 = int(pd.Timestamp("2024-01-01 09:00:00").timestamp())
    t1 = int(pd.Timestamp("2024-01-01 09:10:00").timestamp())
    deals = pd.DataFrame(
        [
            _mt5_deal(101, 1, "EURUSD", 0, 0, t0, 1.1000, 0.1),
            _mt5_deal(101, 2, "EURUSD", 1, 1, t1, 1.1010, 0.1, profit=100.0, commission=-0.5),
        ]
    )
    trades = build_trades_from_deals(deals)
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["symbol"] == "EURUSD"
    assert row["type"] == "buy"
    assert math.isclose(row["profit"], 100.0)
    assert math.isclose(row["net_profit"], 99.5)
    assert row["open_price"] == 1.1000
    assert row["close_price"] == 1.1010


def test_build_trades_from_deals_ignores_still_open_positions():
    t0 = int(pd.Timestamp("2024-01-01 09:00:00").timestamp())
    deals = pd.DataFrame([_mt5_deal(102, 1, "GBPUSD", 0, 0, t0, 1.2500, 0.1)])
    trades = build_trades_from_deals(deals)
    assert trades.empty


def test_build_trades_from_deals_ignores_balance_operations():
    t0 = int(pd.Timestamp("2024-01-01 09:00:00").timestamp())
    deals = pd.DataFrame([_mt5_deal(0, 1, None, 2, 2, t0, 0.0, 0.0, profit=1000.0)])
    trades = build_trades_from_deals(deals)
    assert trades.empty


def test_load_trades_from_csv_with_common_broker_headers():
    csv_content = (
        "Ticket,Symbol,Type,Volume,Open Time,Close Time,Open Price,Close Price,Commission,Swap,Profit\n"
        "1,EURUSD,buy,0.10,2024-01-01 09:00:00,2024-01-01 09:10:00,1.1000,1.1010,-0.5,0.0,100.0\n"
        "2,GBPUSD,sell,0.10,2024-01-02 14:00:00,2024-01-02 14:05:00,1.2500,1.2530,-0.5,0.0,-30.0\n"
    )
    trades = load_trades_from_csv(io.StringIO(csv_content))
    assert len(trades) == 2
    assert set(trades["symbol"]) == {"EURUSD", "GBPUSD"}
    assert math.isclose(trades.loc[trades["symbol"] == "EURUSD", "net_profit"].iloc[0], 99.5)


def test_load_trades_from_csv_missing_required_columns_raises():
    csv_content = "Foo,Bar\n1,2\n"
    with pytest.raises(ValueError):
        load_trades_from_csv(io.StringIO(csv_content))
