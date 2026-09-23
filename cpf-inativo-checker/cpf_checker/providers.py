"""Provedores de consulta da situação cadastral do CPF.

A Receita Federal não oferece API pública e gratuita para consulta em lote.
O canal oficial é a API **Consulta CPF** do SERPRO (contratada na Loja SERPRO,
cobrada por consulta). O site "Comprovante de Situação Cadastral" da Receita
exige CAPTCHA e data de nascimento e não deve ser automatizado.

Por isso a consulta fica atrás da interface ``Provider``: hoje há o SERPRO
(produção e trial) e um provedor fictício para testes. Se a empresa já
contrata outro bureau (Serasa, Boa Vista, Infosimples...), basta criar uma
nova classe com o método ``consultar``.
"""

from __future__ import annotations

import base64
import random
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import requests

# Códigos de situação cadastral usados pela Receita / SERPRO.
SITUACOES = {
    "0": "Regular",
    "2": "Suspensa",
    "3": "Titular Falecido",
    "4": "Pendente de Regularização",
    "5": "Cancelada por Multiplicidade",
    "8": "Nula",
    "9": "Cancelada de Ofício",
}
CODIGO_REGULAR = "0"


@dataclass
class Resultado:
    """Resposta normalizada de uma consulta, independente do provedor."""

    cpf: str
    status: str  # "ok", "nao_encontrado", "cpf_invalido" ou "erro"
    situacao_codigo: str = ""
    situacao_descricao: str = ""
    nome: str = ""
    ano_obito: str = ""
    erro: str = ""
    fonte: str = ""

    @property
    def inativo(self) -> bool | None:
        """True = CPF não regular; False = regular; None = não foi possível saber."""
        if self.status == "ok":
            return self.situacao_codigo != CODIGO_REGULAR
        if self.status == "nao_encontrado":
            return True
        return None


class Provider(Protocol):
    nome: str

    def consultar(self, cpf: str) -> Resultado: ...


class ProviderError(Exception):
    """Falha que não deve ser re-tentada (credencial inválida, contrato etc.)."""


class SerproProvider:
    """API Consulta CPF do SERPRO (https://loja.serpro.gov.br/consultacpf).

    Autenticação OAuth2 client_credentials com Consumer Key/Secret obtidos na
    área do cliente da Loja SERPRO. O token é renovado automaticamente.
    """

    nome = "serpro"

    TOKEN_URL = "https://gateway.apiserpro.serpro.gov.br/token"
    BASE_URL = "https://gateway.apiserpro.serpro.gov.br/consulta-cpf-df/v1/cpf"

    # Ambiente de demonstração público do SERPRO: não consome créditos e só
    # responde para CPFs de teste listados na documentação da API.
    TRIAL_URL = "https://gateway.apiserpro.serpro.gov.br/consulta-cpf-df-trial/v1/cpf"
    TRIAL_TOKEN = "06aef429-a981-3ec5-a1f8-71d38d86481e"

    def __init__(
        self,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        *,
        trial: bool = False,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 4,
        session: requests.Session | None = None,
    ) -> None:
        if not trial and not (consumer_key and consumer_secret):
            raise ProviderError(
                "Informe SERPRO_CONSUMER_KEY e SERPRO_CONSUMER_SECRET "
                "(ou use --trial para o ambiente de demonstração)."
            )
        self.trial = trial
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.base_url = (base_url or (self.TRIAL_URL if trial else self.BASE_URL)).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._token: str | None = self.TRIAL_TOKEN if trial else None
        self._token_expira = float("inf") if trial else 0.0
        self._lock = threading.Lock()

    # -- autenticação -----------------------------------------------------
    def _obter_token(self, forcar: bool = False) -> str:
        with self._lock:
            if self.trial:
                return self._token  # type: ignore[return-value]
            if not forcar and self._token and time.time() < self._token_expira - 60:
                return self._token
            cred = base64.b64encode(
                f"{self.consumer_key}:{self.consumer_secret}".encode()
            ).decode()
            resp = self.session.post(
                self.TOKEN_URL,
                headers={
                    "Authorization": f"Basic {cred}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise ProviderError(
                    f"Falha ao obter token SERPRO (HTTP {resp.status_code}). "
                    "Confira Consumer Key/Secret."
                )
            payload = resp.json()
            self._token = payload["access_token"]
            self._token_expira = time.time() + float(payload.get("expires_in", 3600))
            return self._token

    # -- consulta ---------------------------------------------------------
    def consultar(self, cpf: str) -> Resultado:
        ultimo_erro = ""
        renovou_token = False
        for tentativa in range(self.max_retries + 1):
            token = self._obter_token()
            try:
                resp = self.session.get(
                    f"{self.base_url}/{cpf}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                ultimo_erro = f"falha de rede: {exc.__class__.__name__}"
                self._esperar(tentativa)
                continue

            if resp.status_code == 200:
                return self._parse(cpf, resp.json())
            if resp.status_code == 404:
                return Resultado(cpf, "nao_encontrado", situacao_descricao="CPF não encontrado na base da Receita", fonte=self.nome)
            if resp.status_code == 400:
                return Resultado(cpf, "cpf_invalido", erro="CPF rejeitado pela API (HTTP 400)", fonte=self.nome)
            if resp.status_code == 401 and not renovou_token and not self.trial:
                self._obter_token(forcar=True)
                renovou_token = True
                continue
            if resp.status_code in (401, 403):
                raise ProviderError(
                    f"Acesso negado pela API SERPRO (HTTP {resp.status_code}). "
                    "Verifique credenciais e se o contrato Consulta CPF está ativo."
                )
            # 429 (limite de requisições), 5xx e demais: re-tenta com backoff
            ultimo_erro = f"HTTP {resp.status_code}"
            retry_after = resp.headers.get("Retry-After")
            self._esperar(tentativa, float(retry_after) if retry_after and retry_after.isdigit() else None)

        return Resultado(cpf, "erro", erro=ultimo_erro or "falha desconhecida", fonte=self.nome)

    @staticmethod
    def _esperar(tentativa: int, segundos: float | None = None) -> None:
        time.sleep(segundos if segundos is not None else min(2 ** tentativa, 30) + random.random())

    def _parse(self, cpf: str, data: dict) -> Resultado:
        situacao = data.get("situacao") or {}
        codigo = str(situacao.get("codigo", "")).strip()
        descricao = situacao.get("descricao") or SITUACOES.get(codigo, "Desconhecida")
        return Resultado(
            cpf=cpf,
            status="ok",
            situacao_codigo=codigo,
            situacao_descricao=descricao,
            nome=data.get("nome", "") or "",
            ano_obito=str(data.get("obito", "") or ""),
            fonte=self.nome + ("-trial" if self.trial else ""),
        )


class FakeProvider:
    """Provedor determinístico, sem rede, para testes e ensaio do fluxo.

    ``situacoes`` mapeia CPF -> código de situação; CPFs não mapeados
    retornam Regular.
    """

    nome = "fake"

    def __init__(self, situacoes: dict[str, str] | None = None) -> None:
        self.situacoes = situacoes or {}
        self.chamadas: list[str] = []

    def consultar(self, cpf: str) -> Resultado:
        self.chamadas.append(cpf)
        codigo = self.situacoes.get(cpf, CODIGO_REGULAR)
        if codigo == "404":
            return Resultado(cpf, "nao_encontrado", situacao_descricao="CPF não encontrado na base da Receita", fonte=self.nome)
        return Resultado(cpf, "ok", codigo, SITUACOES.get(codigo, "Desconhecida"), fonte=self.nome)
