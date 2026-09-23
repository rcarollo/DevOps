import pandas as pd
import pytest

from cpf_checker import cpf as cpf_utils
from cpf_checker.checker import Cache, resumo, verificar
from cpf_checker.cli import main
from cpf_checker.providers import FakeProvider, ProviderError, SerproProvider

# CPFs com dígitos verificadores válidos (gerados, não pertencem a ninguém)
REGULAR = "52998224725"
SUSPENSO = "11144477735"
FALECIDO = "39053344705"
INEXISTENTE = "12345678909"


# --- validação --------------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("529.982.247-25", "52998224725"),
    ("1234567890", "01234567890"),       # zero à esquerda perdido na planilha
    ("52998224725.0", "52998224725"),    # lido como float
    (None, ""),
    ("  ", ""),
])
def test_normalize(entrada, esperado):
    assert cpf_utils.normalize(entrada) == esperado


@pytest.mark.parametrize("valor,ok", [
    (REGULAR, True), (SUSPENSO, True), ("52998224724", False),
    ("11111111111", False), ("123", False),
])
def test_is_valid(valor, ok):
    assert cpf_utils.is_valid(valor) is ok


def test_mask_nao_expoe_cpf():
    assert cpf_utils.mask(REGULAR) == "529.***.***-25"


# --- orquestração -----------------------------------------------------------

def _base():
    return pd.DataFrame({
        "id": ["1", "2", "3", "4", "5", "6", "7"],
        "CPF_Cliente": [
            "529.982.247-25", SUSPENSO, FALECIDO, INEXISTENTE,
            "111.111.111-11", "", "52998224725",  # duplicado do 1º
        ],
    })


def test_verificar_classifica_e_deduplica():
    prov = FakeProvider({SUSPENSO: "2", FALECIDO: "3", INEXISTENTE: "404"})
    out = verificar(_base(), "CPF_Cliente", prov, workers=2, por_segundo=0)

    assert sorted(prov.chamadas) == sorted([REGULAR, SUSPENSO, FALECIDO, INEXISTENTE])
    assert list(out["inativo"]) == ["NAO", "SIM", "SIM", "SIM", "indeterminado", "", "NAO"]
    assert list(out["status_consulta"])[4:6] == ["cpf_invalido", "cpf_vazio"]
    assert out.loc[1, "situacao_receita"] == "Suspensa"
    assert out.loc[2, "situacao_receita"] == "Titular Falecido"
    assert list(out["id"]) == list(_base()["id"])  # colunas originais preservadas

    r = resumo(out)
    assert (r["regulares"], r["inativos"], r["cpf_invalido"], r["cpf_vazio"]) == (2, 3, 1, 1)


def test_cache_evita_nova_consulta(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    verificar(_base(), "CPF_Cliente", FakeProvider({SUSPENSO: "2"}), cache=cache, por_segundo=0)

    prov2 = FakeProvider()
    out = verificar(_base(), "CPF_Cliente", prov2, cache=cache, por_segundo=0)
    assert prov2.chamadas == []
    assert out.loc[1, "inativo"] == "SIM"
    assert out.loc[1, "fonte"] == "cache:fake"
    cache.close()


def test_limite_controla_custo():
    prov = FakeProvider()
    out = verificar(_base(), "CPF_Cliente", prov, limite=2, por_segundo=0)
    assert len(prov.chamadas) == 2
    assert resumo(out)["nao_consultados"] == 2


# --- SERPRO (sem rede) ------------------------------------------------------

class _Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class _Session:
    def __init__(self, gets, token_status=200):
        self.gets = list(gets)
        self.token_status = token_status
        self.posts = 0

    def post(self, url, **kw):
        self.posts += 1
        assert kw["headers"]["Authorization"].startswith("Basic ")
        return _Resp(self.token_status, {"access_token": f"tok{self.posts}", "expires_in": 3600})

    def get(self, url, headers, **kw):
        return self.gets.pop(0)


def _serpro(session):
    p = SerproProvider("key", "secret", session=session)
    p._esperar = staticmethod(lambda *a, **k: None)
    return p


def test_serpro_parse_situacao():
    s = _Session([_Resp(200, {"ni": SUSPENSO, "nome": "FULANO",
                              "situacao": {"codigo": "2", "descricao": "Suspensa"}})])
    r = _serpro(s).consultar(SUSPENSO)
    assert (r.status, r.situacao_codigo, r.inativo, r.nome) == ("ok", "2", True, "FULANO")


def test_serpro_404_e_retry_429():
    s = _Session([_Resp(429), _Resp(503), _Resp(404)])
    r = _serpro(s).consultar(INEXISTENTE)
    assert r.status == "nao_encontrado" and r.inativo is True


def test_serpro_renova_token_em_401():
    s = _Session([_Resp(401), _Resp(200, {"situacao": {"codigo": "0"}})])
    r = _serpro(s).consultar(REGULAR)
    assert r.inativo is False and s.posts == 2


def test_serpro_credencial_invalida_aborta():
    with pytest.raises(ProviderError):
        _serpro(_Session([], token_status=401)).consultar(REGULAR)


def test_serpro_exige_credenciais():
    with pytest.raises(ProviderError):
        SerproProvider(None, None)


# --- CLI ponta a ponta ------------------------------------------------------

def test_cli_arquivo_csv(tmp_path, capsys):
    entrada = tmp_path / "clientes.csv"
    entrada.write_text("nome;cpf\nAna;529.982.247-25\nBia;123\n", encoding="utf-8")
    saida = tmp_path / "out.xlsx"
    code = main(["--arquivo", str(entrada), "--provedor", "fake", "--saida", str(saida),
                 "--sem-cache", "--por-segundo", "0"])
    assert code == 0
    abas = pd.read_excel(saida, sheet_name=None, dtype=str)
    assert set(abas) == {"Inativos", "Todos", "Resumo"}
    assert len(abas["Todos"]) == 2
    assert "INATIVOS: 0" in capsys.readouterr().out
