"""Normaliza dados brutos de negociação (deals do MT5 ou arquivo exportado)
em uma tabela única e consistente de trades fechadas (round-turn).

Colunas do resultado final:
    ticket, symbol, type, volume, open_time, close_time,
    open_price, close_price, sl, tp, commission, swap, profit, net_profit
"""
from __future__ import annotations

import io
from typing import IO, Union

import numpy as np
import pandas as pd

TRADE_COLUMNS = [
    "ticket",
    "symbol",
    "type",
    "volume",
    "open_time",
    "close_time",
    "open_price",
    "close_price",
    "sl",
    "tp",
    "commission",
    "swap",
    "profit",
    "net_profit",
]

# Constantes do pacote MetaTrader5 (evita depender do pacote em si, que só
# existe no Windows, para poder rodar/testar esta lógica em qualquer SO).
_MT5_ENTRY_IN = 0
_MT5_TYPE_BUY = 0
_MT5_TYPE_SELL = 1
_MT5_TYPE_BALANCE = 2

_EMPTY_TRADES = pd.DataFrame(columns=TRADE_COLUMNS)


def _empty() -> pd.DataFrame:
    return _EMPTY_TRADES.copy()


def build_trades_from_deals(deals: pd.DataFrame) -> pd.DataFrame:
    """Agrupa deals brutos do MT5 (um registro por execução) em trades
    fechadas por posição (position_id), combinando a(s) execução(ões) de
    abertura com a(s) de fechamento."""
    if deals.empty:
        return _empty()

    df = deals.copy()
    df = df[df["type"].isin([_MT5_TYPE_BUY, _MT5_TYPE_SELL])]
    if df.empty:
        return _empty()

    df["time"] = pd.to_datetime(df["time"], unit="s")

    trades = []
    for position_id, group in df.groupby("position_id"):
        opens = group[group["entry"] == _MT5_ENTRY_IN]
        closes = group[group["entry"] != _MT5_ENTRY_IN]
        if opens.empty or closes.empty:
            continue  # posição ainda aberta ou registro incompleto: ignora

        open_row = opens.iloc[0]
        close_row = closes.sort_values("time").iloc[-1]
        trades.append(
            {
                "ticket": position_id,
                "symbol": open_row["symbol"],
                "type": "buy" if open_row["type"] == _MT5_TYPE_BUY else "sell",
                "volume": open_row["volume"],
                "open_time": open_row["time"],
                "close_time": close_row["time"],
                "open_price": open_row["price"],
                "close_price": close_row["price"],
                "sl": open_row.get("sl", np.nan),
                "tp": open_row.get("tp", np.nan),
                "commission": group["commission"].sum(),
                "swap": group["swap"].sum(),
                "profit": closes["profit"].sum(),
            }
        )

    if not trades:
        return _empty()

    result = pd.DataFrame(trades)
    result["net_profit"] = result["profit"] + result["commission"] + result["swap"]
    result = result.sort_values("close_time").reset_index(drop=True)
    return result[TRADE_COLUMNS]


# Aliases de nomes de coluna usados por relatórios comuns do MT4/MT5 e de
# outras plataformas, para reconhecer arquivos exportados sem exigir um
# template exato.
_COLUMN_ALIASES = {
    "ticket": ["ticket", "order", "deal", "position", "id"],
    "symbol": ["symbol", "item", "instrument", "pair"],
    "type": ["type", "side", "direction"],
    "volume": ["volume", "size", "lots", "volume / lots", "volume/lots"],
    "open_time": ["open time", "opentime", "time open", "date open", "time"],
    "close_time": ["close time", "closetime", "time close", "date close"],
    "open_price": ["open price", "price open", "open"],
    "close_price": ["close price", "price close", "close", "price"],
    "sl": ["s / l", "sl", "stop loss"],
    "tp": ["t / p", "tp", "take profit"],
    "commission": ["commission"],
    "swap": ["swap"],
    "profit": ["profit"],
}


def _normalize_headers(columns: pd.Index) -> dict[str, str]:
    """Retorna um mapa {nome_original: nome_padrao} para as colunas reconhecidas."""
    lowered = {str(c).strip().lower(): c for c in columns}
    mapping: dict[str, str] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[lowered[alias]] = canonical
                break
    return mapping


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["sl", "tp", "commission", "swap", "profit"]:
        if col not in df.columns:
            df[col] = 0.0
    df["commission"] = pd.to_numeric(df["commission"], errors="coerce").fillna(0.0)
    df["swap"] = pd.to_numeric(df["swap"], errors="coerce").fillna(0.0)
    df["profit"] = pd.to_numeric(df["profit"], errors="coerce").fillna(0.0)
    df["volume"] = pd.to_numeric(df.get("volume", np.nan), errors="coerce")
    df["open_price"] = pd.to_numeric(df.get("open_price", np.nan), errors="coerce")
    df["close_price"] = pd.to_numeric(df.get("close_price", np.nan), errors="coerce")
    df["open_time"] = pd.to_datetime(df["open_time"], errors="coerce", dayfirst=False)
    if "close_time" in df.columns:
        df["close_time"] = pd.to_datetime(df["close_time"], errors="coerce", dayfirst=False)
    else:
        df["close_time"] = df["open_time"]

    df["type"] = df["type"].astype(str).str.strip().str.lower()
    df["type"] = df["type"].replace({"0": "buy", "1": "sell"})
    df.loc[~df["type"].isin(["buy", "sell"]), "type"] = df["type"].str.extract(
        r"(buy|sell)", expand=False
    )

    df = df.dropna(subset=["symbol", "close_time"])
    df["net_profit"] = df["profit"] + df["commission"] + df["swap"]
    for col in TRADE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    df = df.sort_values("close_time").reset_index(drop=True)
    return df[TRADE_COLUMNS]


def load_trades_from_csv(file: Union[str, IO[bytes], IO[str]]) -> pd.DataFrame:
    """Lê um CSV de histórico exportado (MT4/MT5 ou similar) e normaliza as
    colunas mais comuns para o esquema interno de trades."""
    raw = pd.read_csv(file)
    if raw.empty:
        return _empty()
    mapping = _normalize_headers(raw.columns)
    if "symbol" not in mapping.values() or "profit" not in mapping.values():
        raise ValueError(
            "Não foi possível reconhecer as colunas do CSV. Verifique se o "
            "arquivo contém pelo menos: símbolo, tipo, volume, horário de "
            "abertura/fechamento e lucro."
        )
    df = raw.rename(columns=mapping)
    return _finalize(df)


def load_trades_from_html(file: Union[str, IO[bytes], IO[str]]) -> pd.DataFrame:
    """Extrai a tabela de negociações de um relatório HTML exportado do
    MT4/MT5 ('Statement' / histórico de conta)."""
    tables = pd.read_html(file)
    candidates = []
    for table in tables:
        mapping = _normalize_headers(table.columns)
        if "symbol" in mapping.values() and "profit" in mapping.values():
            candidates.append((len(table), table, mapping))

    if not candidates:
        raise ValueError(
            "Nenhuma tabela de negociações reconhecível foi encontrada no HTML."
        )

    # usa a maior tabela candidata (normalmente a lista completa de deals/trades)
    _, table, mapping = max(candidates, key=lambda item: item[0])
    df = table.rename(columns=mapping)
    return _finalize(df)


def load_trades_from_file(uploaded_file) -> pd.DataFrame:
    """Detecta o tipo de arquivo (CSV ou HTML) pelo nome e carrega as trades.

    `uploaded_file` aceita tanto um caminho/objeto de arquivo quanto um
    `UploadedFile` do Streamlit (que expõe `.name` e é um stream de bytes).
    """
    name = getattr(uploaded_file, "name", str(uploaded_file)).lower()
    if name.endswith((".html", ".htm")):
        return load_trades_from_html(uploaded_file)
    if name.endswith(".csv"):
        return load_trades_from_csv(uploaded_file)
    raise ValueError("Formato de arquivo não suportado. Envie um .csv ou .html/.htm.")
