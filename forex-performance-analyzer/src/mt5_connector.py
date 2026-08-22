"""Conexão direta a um terminal MetaTrader 5 para baixar o histórico de negociações.

Depende do pacote oficial `MetaTrader5`, que só funciona em Windows com o
terminal MT5 instalado localmente (ele conversa com o terminal em execução,
não com um servidor remoto genérico). O login usa o número da conta, a senha
e o servidor da corretora, exatamente como na tela de login do terminal.

As credenciais nunca são gravadas em disco por este módulo: elas só vivem em
memória durante a chamada de `connect`.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - só existe de fato no Windows
    mt5 = None

from src.data_import import build_trades_from_deals


class MT5ConnectionError(RuntimeError):
    """Erro ao conectar ou autenticar no terminal MT5."""


@dataclass
class MT5Credentials:
    login: int
    password: str
    server: str
    terminal_path: Optional[str] = None


def is_available() -> bool:
    """True se o pacote MetaTrader5 pôde ser importado neste sistema."""
    return mt5 is not None


def connect(creds: MT5Credentials) -> None:
    if mt5 is None:
        raise MT5ConnectionError(
            "O pacote 'MetaTrader5' não está disponível neste sistema. Ele só "
            "funciona em Windows com o terminal MT5 instalado localmente. "
            "Use a importação de arquivo como alternativa."
        )

    initialized = (
        mt5.initialize(path=creds.terminal_path) if creds.terminal_path else mt5.initialize()
    )
    if not initialized:
        raise MT5ConnectionError(f"Falha ao iniciar o terminal MT5: {mt5.last_error()}")

    authorized = mt5.login(creds.login, password=creds.password, server=creds.server)
    if not authorized:
        error = mt5.last_error()
        mt5.shutdown()
        raise MT5ConnectionError(f"Falha no login MT5 (conta/senha/servidor): {error}")


def disconnect() -> None:
    if mt5 is not None:
        mt5.shutdown()


def fetch_closed_trades(date_from: dt.datetime, date_to: dt.datetime) -> pd.DataFrame:
    """Busca os deals do período e agrupa em trades fechadas (round-turn)."""
    if mt5 is None:
        raise MT5ConnectionError("Pacote MetaTrader5 indisponível neste sistema.")

    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        raise MT5ConnectionError(f"Falha ao buscar histórico: {mt5.last_error()}")
    if len(deals) == 0:
        return build_trades_from_deals(pd.DataFrame())

    raw = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
    return build_trades_from_deals(raw)
