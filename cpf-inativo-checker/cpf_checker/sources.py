"""Leitura da base de clientes (arquivo CSV/Excel ou banco de dados via SQL)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
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


def gravar_situacoes(url_conexao: str, tabela: str, df: pd.DataFrame) -> int:
    """Grava/atualiza a situação de cada CPF numa tabela do banco (uma linha por CPF).

    Cria a tabela se não existir. CPFs já presentes são substituídos; os demais
    são preservados (útil ao processar a base em lotes com --limite).
    Só grava resultados definitivos (consultados com sucesso ou não encontrados).
    """
    from sqlalchemy import bindparam, create_engine, inspect, text

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", tabela):
        raise ValueError(f"Nome de tabela inválido: {tabela!r}")
    schema, _, nome = tabela.rpartition(".")
    schema = schema or None

    linhas = (
        df[df["status_consulta"].isin(["ok", "nao_encontrado"])]
        .drop_duplicates("cpf_normalizado")
        [["cpf_normalizado", "status_consulta", "situacao_codigo", "situacao_receita", "inativo", "ano_obito"]]
        .rename(columns={"cpf_normalizado": "cpf"})
        .assign(atualizado_em=datetime.now(timezone.utc).replace(tzinfo=None))
    )
    if linhas.empty:
        return 0

    engine = create_engine(url_conexao)
    try:
        with engine.begin() as conn:
            if not inspect(conn).has_table(nome, schema=schema):
                linhas.head(0).to_sql(nome, conn, schema=schema, index=False)
            alvo = f"{schema}.{nome}" if schema else nome
            apagar = text(f"DELETE FROM {alvo} WHERE cpf IN :cpfs").bindparams(
                bindparam("cpfs", expanding=True)
            )
            cpfs = linhas["cpf"].tolist()
            for i in range(0, len(cpfs), 500):
                conn.execute(apagar, {"cpfs": cpfs[i:i + 500]})
            linhas.to_sql(nome, conn, schema=schema, index=False, if_exists="append", chunksize=500)
    finally:
        engine.dispose()
    return len(linhas)
