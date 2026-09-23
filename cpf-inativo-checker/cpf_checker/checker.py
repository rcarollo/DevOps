"""Orquestra a verificação: valida, remove duplicados, usa cache e consulta."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import pandas as pd

from . import cpf as cpf_utils
from .providers import Provider, ProviderError, Resultado

log = logging.getLogger(__name__)


class Cache:
    """Cache em SQLite dos resultados, para não pagar duas vezes pela mesma consulta.

    Só resultados definitivos ("ok" e "nao_encontrado") são guardados; erros
    são consultados de novo na próxima execução.
    """

    def __init__(self, caminho: str | Path, validade_dias: float = 30) -> None:
        self.validade = validade_dias * 86400
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(caminho), check_same_thread=False)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS consultas (
                cpf TEXT PRIMARY KEY, status TEXT, situacao_codigo TEXT,
                situacao_descricao TEXT, nome TEXT, ano_obito TEXT,
                fonte TEXT, consultado_em REAL)"""
        )
        self.conn.commit()

    def get(self, cpf: str) -> Resultado | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT status, situacao_codigo, situacao_descricao, nome, ano_obito, fonte, consultado_em "
                "FROM consultas WHERE cpf = ?",
                (cpf,),
            ).fetchone()
        if not row or time.time() - row[6] > self.validade:
            return None
        return Resultado(cpf, row[0], row[1], row[2], row[3], row[4], fonte=f"cache:{row[5]}")

    def put(self, r: Resultado) -> None:
        if r.status not in ("ok", "nao_encontrado"):
            return
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO consultas VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (r.cpf, r.status, r.situacao_codigo, r.situacao_descricao, r.nome,
                 r.ano_obito, r.fonte, time.time()),
            )
            self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class RateLimiter:
    """Garante no máximo ``por_segundo`` chamadas por segundo entre todas as threads."""

    def __init__(self, por_segundo: float) -> None:
        self.intervalo = 1.0 / por_segundo if por_segundo > 0 else 0.0
        self._proximo = 0.0
        self._lock = threading.Lock()

    def aguardar(self) -> None:
        if not self.intervalo:
            return
        with self._lock:
            agora = time.monotonic()
            espera = self._proximo - agora
            self._proximo = max(agora, self._proximo) + self.intervalo
        if espera > 0:
            time.sleep(espera)


def consultar_um(
    valor: object, provider: Provider, cache: Cache | None = None, *, forcar: bool = False
) -> Resultado:
    """Consulta um único CPF: normaliza, valida, tenta o cache e só então a API.

    ``forcar`` ignora o cache (mas grava o resultado novo nele).
    ProviderError (credencial inválida etc.) é propagado para quem chamou.
    """
    c = cpf_utils.normalize(valor)
    if not cpf_utils.is_valid(c):
        return Resultado(c, "cpf_invalido", erro="dígito verificador inválido", fonte="validacao_local")
    if cache and not forcar and (hit := cache.get(c)):
        return hit
    r = provider.consultar(c)
    if cache:
        cache.put(r)
    return r


def verificar(
    df: pd.DataFrame,
    coluna_cpf: str,
    provider: Provider,
    *,
    cache: Cache | None = None,
    workers: int = 4,
    por_segundo: float = 5.0,
    limite: int | None = None,
    progresso: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Consulta a situação de cada CPF e devolve o DataFrame original + colunas do resultado.

    ``limite`` restringe quantos CPFs serão consultados na API (útil para um
    teste inicial controlando custo); os demais ficam com status "nao_consultado".
    """
    df = df.copy()
    df["cpf_normalizado"] = df[coluna_cpf].map(cpf_utils.normalize)

    unicos = [c for c in dict.fromkeys(df["cpf_normalizado"]) if c]
    resultados: dict[str, Resultado] = {}
    pendentes: list[str] = []

    for c in unicos:
        if not cpf_utils.is_valid(c):
            resultados[c] = Resultado(c, "cpf_invalido", erro="dígito verificador inválido", fonte="validacao_local")
        elif cache and (hit := cache.get(c)):
            resultados[c] = hit
        else:
            pendentes.append(c)

    if limite is not None and len(pendentes) > limite:
        for c in pendentes[limite:]:
            resultados[c] = Resultado(c, "nao_consultado", erro="fora do --limite desta execução")
        pendentes = pendentes[:limite]

    log.info(
        "%d linhas, %d CPFs únicos, %d inválidos, %d do cache, %d a consultar",
        len(df), len(unicos),
        sum(r.status == "cpf_invalido" for r in resultados.values()),
        sum(r.fonte.startswith("cache:") for r in resultados.values()),
        len(pendentes),
    )

    limiter = RateLimiter(por_segundo)
    abortar = threading.Event()

    def tarefa(c: str) -> Resultado:
        if abortar.is_set():
            return Resultado(c, "erro", erro="execução abortada")
        limiter.aguardar()
        try:
            return provider.consultar(c)
        except ProviderError:
            abortar.set()
            raise

    feitos = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futuros = {pool.submit(tarefa, c): c for c in pendentes}
        try:
            for fut in as_completed(futuros):
                r = fut.result()
                resultados[r.cpf] = r
                if cache:
                    cache.put(r)
                feitos += 1
                if r.status == "erro":
                    log.warning("Erro ao consultar %s: %s", cpf_utils.mask(r.cpf), r.erro)
                if progresso:
                    progresso(feitos, len(pendentes))
        except ProviderError:
            for f in futuros:
                f.cancel()
            raise

    def coluna(attr: str):
        return df["cpf_normalizado"].map(lambda c: getattr(resultados[c], attr) if c in resultados else "")

    df["cpf_formatado"] = df["cpf_normalizado"].map(cpf_utils.format_cpf)
    df["status_consulta"] = df["cpf_normalizado"].map(
        lambda c: resultados[c].status if c in resultados else "cpf_vazio"
    )
    df["situacao_codigo"] = coluna("situacao_codigo")
    df["situacao_receita"] = coluna("situacao_descricao")
    df["nome_receita"] = coluna("nome")
    df["ano_obito"] = coluna("ano_obito")
    df["inativo"] = df["cpf_normalizado"].map(
        lambda c: _sim_nao(resultados[c].inativo) if c in resultados else ""
    )
    df["erro"] = coluna("erro")
    df["fonte"] = coluna("fonte")
    return df


def _sim_nao(valor: bool | None) -> str:
    if valor is None:
        return "indeterminado"
    return "SIM" if valor else "NAO"


def resumo(df: pd.DataFrame) -> dict[str, int]:
    return {
        "linhas": len(df),
        "regulares": int((df["inativo"] == "NAO").sum()),
        "inativos": int((df["inativo"] == "SIM").sum()),
        "cpf_invalido": int((df["status_consulta"] == "cpf_invalido").sum()),
        "cpf_vazio": int((df["status_consulta"] == "cpf_vazio").sum()),
        "erros": int((df["status_consulta"] == "erro").sum()),
        "nao_consultados": int((df["status_consulta"] == "nao_consultado").sum()),
    }

