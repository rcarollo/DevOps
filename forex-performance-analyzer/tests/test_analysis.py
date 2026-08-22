import math

from src import analysis


def test_by_hour_identifies_best_hour(sample_trades):
    hourly = analysis.by_hour(sample_trades)
    best = hourly.loc[hourly["net_profit"].idxmax()]
    assert int(best["hour"]) == 9
    assert math.isclose(best["net_profit"], 350.0)
    assert int(best["trades"]) == 4


def test_by_hour_worst_hour(sample_trades):
    hourly = analysis.by_hour(sample_trades)
    worst = hourly.loc[hourly["net_profit"].idxmin()]
    assert int(worst["hour"]) == 20
    assert math.isclose(worst["net_profit"], -100.0)


def test_by_weekday_totals(sample_trades):
    weekday = analysis.by_weekday(sample_trades)
    by_name = weekday.set_index("weekday")["net_profit"]
    assert math.isclose(by_name["Segunda"], 150.0)
    assert math.isclose(by_name["Terça"], -30.0)
    assert math.isclose(by_name["Quarta"], 80.0)
    assert math.isclose(by_name["Quinta"], -100.0)
    assert math.isclose(by_name["Sexta"], 100.0)


def test_by_symbol_totals(sample_trades):
    by_symbol = analysis.by_symbol(sample_trades).set_index("symbol")["net_profit"]
    assert math.isclose(by_symbol["EURUSD"], 350.0)
    assert math.isclose(by_symbol["GBPUSD"], -50.0)
    assert math.isclose(by_symbol["USDJPY"], -100.0)
    # ordenado do melhor para o pior resultado
    ordered = analysis.by_symbol(sample_trades)["symbol"].tolist()
    assert ordered[0] == "EURUSD"


def test_by_duration_bucket_counts_all_trades(sample_trades):
    duration = analysis.by_duration_bucket(sample_trades)
    assert duration["trades"].sum() == len(sample_trades)


def test_best_and_worst(sample_trades):
    best, worst = analysis.best_and_worst(sample_trades, n=2)
    assert best.iloc[0]["ticket"] == 7  # +120
    assert worst.iloc[0]["ticket"] == 5  # -60
