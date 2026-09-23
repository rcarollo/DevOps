"""Serviço HTTP para o sistema consultar a situação de um CPF na hora.

Só usa a biblioteca padrão (sem framework). Endpoints:

  GET  /cpf/<cpf>            situação de um CPF (usa cache; ?forcar=1 ignora o cache)
  POST /cpfs                 {"cpfs": ["...", "..."]} → lista de resultados (máx. 100)
  GET  /saude                verificação de disponibilidade (sem autenticação)

Toda chamada (exceto /saude) exige o cabeçalho ``X-API-Key`` igual à variável
de ambiente CPF_API_KEY, porque a resposta traz dados pessoais.
"""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import cpf as cpf_utils
from .checker import Cache, consultar_um
from .providers import FakeProvider, Provider, ProviderError, Resultado, SerproProvider

log = logging.getLogger("cpf_checker.server")

MAX_LOTE = 100


def _payload(r: Resultado) -> dict:
    d = asdict(r)
    d["inativo"] = r.inativo
    d["cpf_formatado"] = cpf_utils.format_cpf(r.cpf)
    return d


def criar_handler(provider: Provider, cache: Cache | None, api_key: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "cpf-checker"

        def log_message(self, fmt, *args):  # não logar a URL, que contém o CPF
            pass

        def _responder(self, status: int, corpo: dict | list) -> None:
            dados = json.dumps(corpo, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _autorizado(self) -> bool:
            enviado = self.headers.get("X-API-Key", "")
            if hmac.compare_digest(enviado.encode(), api_key.encode()):
                return True
            self._responder(401, {"erro": "X-API-Key ausente ou inválida"})
            return False

        def _consultar(self, valor: object, forcar: bool = False) -> dict:
            r = consultar_um(valor, provider, cache, forcar=forcar)
            log.info("consulta %s -> %s %s", cpf_utils.mask(r.cpf), r.status, r.situacao_codigo)
            return _payload(r)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/saude":
                return self._responder(200, {"status": "ok"})
            if not url.path.startswith("/cpf/"):
                return self._responder(404, {"erro": "rota não encontrada"})
            if not self._autorizado():
                return
            forcar = parse_qs(url.query).get("forcar", ["0"])[0] in ("1", "true", "sim")
            try:
                corpo = self._consultar(url.path[len("/cpf/"):], forcar)
            except ProviderError as exc:
                log.error("%s", exc)
                return self._responder(502, {"erro": str(exc)})
            status = 200 if corpo["status"] != "cpf_invalido" else 422
            self._responder(status, corpo)

        def do_POST(self):
            if urlparse(self.path).path != "/cpfs":
                return self._responder(404, {"erro": "rota não encontrada"})
            if not self._autorizado():
                return
            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                cpfs = json.loads(self.rfile.read(tamanho) or b"{}").get("cpfs")
                if not isinstance(cpfs, list):
                    raise ValueError
            except (ValueError, AttributeError):
                return self._responder(400, {"erro": 'corpo esperado: {"cpfs": ["..."]}'})
            if len(cpfs) > MAX_LOTE:
                return self._responder(413, {"erro": f"máximo de {MAX_LOTE} CPFs por chamada"})
            try:
                self._responder(200, [self._consultar(c) for c in cpfs])
            except ProviderError as exc:
                log.error("%s", exc)
                self._responder(502, {"erro": str(exc)})

    return Handler


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cpf_checker.server", description=__doc__.splitlines()[0])
    p.add_argument("--host", default=os.getenv("CPF_HOST", "127.0.0.1"),
                   help="Interface de escuta (padrão 127.0.0.1; use 0.0.0.0 para a rede interna)")
    p.add_argument("--porta", type=int, default=int(os.getenv("CPF_PORTA", "8080")))
    p.add_argument("--provedor", choices=["serpro", "fake"], default="serpro")
    p.add_argument("--trial", action="store_true")
    p.add_argument("--cache", default=os.getenv("CPF_CACHE", ".cache_cpf.sqlite"))
    p.add_argument("--validade-cache", type=float, default=30, help="dias (padrão 30)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    api_key = os.getenv("CPF_API_KEY", "")
    if len(api_key) < 16:
        log.error("Defina CPF_API_KEY com pelo menos 16 caracteres (a API expõe dados pessoais).")
        return 2
    try:
        provider = FakeProvider() if args.provedor == "fake" else SerproProvider(
            os.getenv("SERPRO_CONSUMER_KEY"), os.getenv("SERPRO_CONSUMER_SECRET"),
            trial=args.trial, base_url=os.getenv("SERPRO_BASE_URL") or None,
        )
    except ProviderError as exc:
        log.error("%s", exc)
        return 2

    cache = Cache(args.cache, args.validade_cache)
    httpd = ThreadingHTTPServer((args.host, args.porta), criar_handler(provider, cache, api_key))
    log.info("Servindo em http://%s:%d (provedor: %s)", args.host, args.porta, provider.nome)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        cache.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
