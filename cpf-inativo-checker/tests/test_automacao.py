import json
import threading
import urllib.error
import urllib.request

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from cpf_checker.checker import Cache, consultar_um
from cpf_checker.cli import main
from cpf_checker.providers import FakeProvider
from cpf_checker.server import criar_handler
from http.server import ThreadingHTTPServer

REGULAR = "52998224725"
SUSPENSO = "11144477735"
CHAVE = "chave-de-teste-1234567890"


def test_consultar_um_usa_cache(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    prov = FakeProvider({SUSPENSO: "2"})
    assert consultar_um("111.444.777-35", prov, cache).inativo is True
    assert consultar_um(SUSPENSO, prov, cache).fonte == "cache:fake"
    consultar_um(SUSPENSO, prov, cache, forcar=True)
    assert prov.chamadas == [SUSPENSO, SUSPENSO]
    assert consultar_um("123", prov, cache).status == "cpf_invalido"
    cache.close()


@pytest.fixture
def servidor(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), criar_handler(FakeProvider({SUSPENSO: "2"}), cache, CHAVE))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    cache.close()


def _req(url, chave=CHAVE, corpo=None):
    headers = {"X-API-Key": chave} if chave else {}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        headers["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, dados, headers)) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_consulta_um(servidor):
    status, corpo = _req(f"{servidor}/cpf/111.444.777-35")
    assert status == 200
    assert corpo["inativo"] is True and corpo["situacao_descricao"] == "Suspensa"


def test_api_exige_chave(servidor):
    assert _req(f"{servidor}/cpf/{REGULAR}", chave=None)[0] == 401
    assert _req(f"{servidor}/cpf/{REGULAR}", chave="errada")[0] == 401
    assert _req(f"{servidor}/saude", chave=None)[0] == 200


def test_api_cpf_invalido(servidor):
    assert _req(f"{servidor}/cpf/12345")[0] == 422


def test_api_lote(servidor):
    status, corpo = _req(f"{servidor}/cpfs", corpo={"cpfs": [REGULAR, SUSPENSO]})
    assert status == 200
    assert [c["inativo"] for c in corpo] == [False, True]
    assert _req(f"{servidor}/cpfs", corpo={"x": 1})[0] == 400


def test_cli_grava_tabela_e_atualiza(tmp_path):
    db = f"sqlite:///{tmp_path / 'erp.db'}"
    eng = create_engine(db)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE clientes (id int, cpf text)"))
        c.execute(text(f"INSERT INTO clientes VALUES (1, '{REGULAR}'), (2, '{SUSPENSO}'), (3, 'lixo')"))
    args = ["--sql", "SELECT * FROM clientes", "--db-url", db, "--provedor", "fake",
            "--gravar-tabela", "cpf_situacao", "--saida", str(tmp_path / "o.csv"),
            "--sem-cache", "--por-segundo", "0"]
    assert main(args) == 0
    assert main(args) == 0  # segunda execução substitui, não duplica
    tab = pd.read_sql("SELECT * FROM cpf_situacao ORDER BY cpf", eng)
    eng.dispose()
    assert tab["cpf"].tolist() == [SUSPENSO, REGULAR]
    assert tab["inativo"].tolist() == ["NAO", "NAO"]  # FakeProvider padrão = Regular
