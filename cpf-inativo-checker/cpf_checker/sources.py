"""Leitura da base de clientes (arquivo CSV/Excel ou banco de dados via SQL)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def ler_arquivo(caminho: str | Path, sep: str | None = None) -> pd.DataFrame:
    """Lê CSV ou Excel mantendo todas as colunas como texto (preserva zeros do CPF)."""
    caminho = Path(caminho)
    sufixo = caminho.suffix.lower()
    if sufixo in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(caminho, dtype=str)
    if sufixo in (".csv", ".txt"):
        # sep=None + engine python detecta ";" (padrão do Excel pt-BR) ou ","
        return pd.read_csv(caminho, dtype=str, sep=sep, engine="python", encoding_errors="replace")
    raise ValueError(f"Formato não suportado: {sufixo} (use .csv, .txt ou .xlsx)")


def ler_sql(url_conexao: str, consulta: str) -> pd.DataFrame:
    """Executa uma consulta SQL e devolve o resultado.

    ``url_conexao`` segue o padrão SQLAlchemy, por exemplo:
      postgresql+psycopg2://usuario:senha@host:5432/banco
      mysql+pymysql://usuario:senha@host/banco
      mssql+pyodbc://usuario:senha@DSN
      oracle+oracledb://usuario:senha@host:1521/?service_name=XE
    O driver correspondente precisa estar instalado.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(url_conexao)
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(consulta), conn, dtype=str)
    finally:
        engine.dispose()


def detectar_coluna_cpf(df: pd.DataFrame, coluna: str | None = None) -> str:
    """Retorna a coluna do CPF: a informada ou a primeira cujo nome contém 'cpf'."""
    if coluna:
        if coluna not in df.columns:
            raise ValueError(f"Coluna '{coluna}' não existe. Colunas: {list(df.columns)}")
        return coluna
    candidatas = [c for c in df.columns if "cpf" in str(c).lower()]
    if not candidatas:
        raise ValueError(
            f"Não achei coluna de CPF. Use --coluna-cpf. Colunas: {list(df.columns)}"
        )
    return candidatas[0]
