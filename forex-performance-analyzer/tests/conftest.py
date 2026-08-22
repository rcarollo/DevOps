import pandas as pd
import pytest


@pytest.fixture
def sample_trades() -> pd.DataFrame:
    """8 trades sintéticas com resultado conhecido, para validar as métricas.

    Segunda 09h EURUSD: +100, +50 (2 vitórias)
    Terça   14h GBPUSD: -30 (1 derrota)
    Quarta  09h EURUSD: +80 (1 vitória)
    Quinta  20h USDJPY: -60, -40 (2 derrotas seguidas)
    Sexta   09h EURUSD: +120 (1 vitória)
    Sexta   14h GBPUSD: -20 (1 derrota)
    """
    rows = [
        # ticket, symbol, type, volume, open_time, close_time, open_price, close_price, sl, tp, commission, swap, profit
        (1, "EURUSD", "buy", 0.10, "2024-01-01 09:00", "2024-01-01 09:10", 1.1000, 1.1010, None, None, -0.5, 0.0, 100.5),
        (2, "EURUSD", "buy", 0.10, "2024-01-01 09:20", "2024-01-01 09:25", 1.1010, 1.1015, None, None, -0.5, 0.0, 50.5),
        (3, "GBPUSD", "sell", 0.10, "2024-01-02 14:00", "2024-01-02 14:05", 1.2500, 1.2530, None, None, -0.5, 0.0, -29.5),
        (4, "EURUSD", "buy", 0.10, "2024-01-03 09:05", "2024-01-03 09:40", 1.1020, 1.1028, None, None, -0.5, 0.0, 80.5),
        (5, "USDJPY", "sell", 0.10, "2024-01-04 20:00", "2024-01-04 20:02", 145.00, 145.60, None, None, -0.5, 0.0, -59.5),
        (6, "USDJPY", "sell", 0.10, "2024-01-04 20:10", "2024-01-04 20:12", 145.60, 146.00, None, None, -0.5, 0.0, -39.5),
        (7, "EURUSD", "buy", 0.20, "2024-01-05 09:00", "2024-01-05 09:15", 1.1030, 1.1042, None, None, -0.5, 0.0, 120.5),
        (8, "GBPUSD", "sell", 0.10, "2024-01-05 14:00", "2024-01-05 14:03", 1.2550, 1.2570, None, None, -0.5, 0.0, -19.5),
    ]
    columns = [
        "ticket", "symbol", "type", "volume", "open_time", "close_time",
        "open_price", "close_price", "sl", "tp", "commission", "swap", "profit",
    ]
    df = pd.DataFrame(rows, columns=columns)
    df["open_time"] = pd.to_datetime(df["open_time"])
    df["close_time"] = pd.to_datetime(df["close_time"])
    df["net_profit"] = df["profit"] + df["commission"] + df["swap"]
    return df
