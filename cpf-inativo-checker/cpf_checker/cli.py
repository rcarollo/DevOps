"""Linha de comando: python -m cpf_checker ..."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from . import sources
from .checker import Cache, resumo, verificar
from .providers import FakeProvider, ProviderError, SerproProvider

log = logging.getLogger("cpf_checker")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cpf_checker",
        description="Verifica a situação cadastral na Receita Federal dos CPFs da base de clientes "
        "e gera relatório com os CPFs inativos (suspensos, cancelados, nulos, falecidos, pendentes).",
    )
    origem = p.add_mutually_exclusive_group(required=True)
    origem.add_argument("--arquivo", help="CSV ou Excel com a base de clientes")
    origem.add_argument("--sql", help="Consulta SQL que retorna os clientes (usar com --db-url ou DB_URL)")

    p.add_argument("--db-url", default=os.getenv("DB_URL"),
                   help="URL SQLAlchemy do banco (padrão: variável DB_URL)")
    p.add_argument("--coluna-cpf", help="Nome da coluna do CPF (padrão: detecta coluna com 'cpf' no nome)")
    p.add_argument("--sep", help="Separador do CSV (padrão: detecta automaticamente)")
    p.add_argument("--saida", default="resultado_cpfs.xlsx",
                   help="Arquivo de saída .xlsx ou .csv (padrão: resultado_cpfs.xlsx)")
    p.add_argument("--somente-inativos", action="store_true",
                   help="Grava só os CPFs inativos/indeterminados no arquivo principal")

    p.add_argument("--provedor", choices=["serpro", "fake"], default="serpro")
    p.add_argument("--trial", action="store_true",
                   help="Usa o ambiente de demonstração do SERPRO (sem custo, só CPFs de teste)")
    p.add_argument("--workers", type=int, default=4, help="Consultas em paralelo (padrão: 4)")
    p.add_argument("--por-segundo", type=float, default=5.0,
                   help="Máximo de consultas por segundo (padrão: 5)")
    p.add_argument("--limite", type=int,
                   help="Consulta no máximo N CPFs nesta execução (controle de custo)")
    p.add_argument("--cache", default=".cache_cpf.sqlite",
                   help="Arquivo de cache SQLite (padrão: .cache_cpf.sqlite)")
    p.add_argument("--sem-cache", action="store_true", help="Ignora o cache")
    p.add_argument("--validade-cache", type=float, default=30,
                   help="Dias em que um resultado em cache é considerado válido (padrão: 30)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _provider(args: argparse.Namespace):
    if args.provedor == "fake":
        return FakeProvider()
    return SerproProvider(
        os.getenv("SERPRO_CONSUMER_KEY"),
        os.getenv("SERPRO_CONSUMER_SECRET"),
        trial=args.trial,
        base_url=os.getenv("SERPRO_BASE_URL") or None,
    )


def _salvar(df: pd.DataFrame, destino: Path, somente_inativos: bool) -> None:
    saida = df.drop(columns=["cpf_normalizado"])
    inativos = saida[saida["inativo"].isin(["SIM", "indeterminado"])]
    principal = inativos if somente_inativos else saida
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.suffix.lower() == ".csv":
        principal.to_csv(destino, index=False, sep=";", encoding="utf-8-sig")
    else:
        with pd.ExcelWriter(destino, engine="openpyxl") as xw:
            inativos.to_excel(xw, sheet_name="Inativos", index=False)
            if not somente_inativos:
                saida.to_excel(xw, sheet_name="Todos", index=False)
            (saida.groupby(["status_consulta", "situacao_receita"], dropna=False)
                  .size().reset_index(name="quantidade")
                  .to_excel(xw, sheet_name="Resumo", index=False))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        if args.arquivo:
            df = sources.ler_arquivo(args.arquivo, sep=args.sep)
        else:
            if not args.db_url:
                log.error("Informe --db-url ou a variável de ambiente DB_URL para usar --sql.")
                return 2
            df = sources.ler_sql(args.db_url, args.sql)
        coluna = sources.detectar_coluna_cpf(df, args.coluna_cpf)
        provider = _provider(args)
    except (ValueError, FileNotFoundError, ProviderError) as exc:
        log.error("%s", exc)
        return 2

    log.info("Coluna de CPF: %s | provedor: %s%s", coluna, provider.nome, " (trial)" if args.trial else "")
    cache = None if args.sem_cache else Cache(args.cache, args.validade_cache)

    def progresso(feito: int, total: int) -> None:
        if feito == total or feito % 50 == 0:
            log.info("Consultados %d/%d", feito, total)

    try:
        resultado = verificar(
            df, coluna, provider,
            cache=cache, workers=args.workers, por_segundo=args.por_segundo,
            limite=args.limite, progresso=progresso,
        )
    except ProviderError as exc:
        log.error("%s", exc)
        return 3
    finally:
        if cache:
            cache.close()

    destino = Path(args.saida)
    _salvar(resultado, destino, args.somente_inativos)

    r = resumo(resultado)
    print(
        f"\nResumo: {r['linhas']} linhas | regulares: {r['regulares']} | INATIVOS: {r['inativos']} | "
        f"CPF inválido: {r['cpf_invalido']} | vazio: {r['cpf_vazio']} | erros: {r['erros']} | "
        f"não consultados: {r['nao_consultados']}\nRelatório: {destino.resolve()}"
    )
    return 1 if r["erros"] else 0


if __name__ == "__main__":
    sys.exit(main())
