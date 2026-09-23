# CPF Inativo Checker

Ferramenta de linha de comando que lê a base de clientes pessoa física
(arquivo CSV/Excel ou direto do banco via SQL), consulta a **situação
cadastral de cada CPF na Receita Federal** e gera um relatório destacando
os CPFs **inativos**, ou seja, qualquer situação diferente de *Regular*:

| Código | Situação                      | Inativo? |
|-------:|-------------------------------|:--------:|
| 0      | Regular                       | não      |
| 2      | Suspensa                      | sim      |
| 3      | Titular Falecido              | sim      |
| 4      | Pendente de Regularização     | sim      |
| 5      | Cancelada por Multiplicidade  | sim      |
| 8      | Nula                          | sim      |
| 9      | Cancelada de Ofício           | sim      |
| —      | CPF não encontrado na Receita | sim      |

## De onde vem o dado

A Receita Federal **não tem API pública gratuita** para consulta em lote.
O site "Comprovante de Situação Cadastral no CPF" exige CAPTCHA e data de
nascimento, e automatizá-lo viola os termos de uso. O canal oficial é a
**API Consulta CPF do SERPRO** (empresa pública que opera os sistemas da
Receita), contratada em <https://loja.serpro.gov.br/consultacpf> e cobrada
por consulta. É esse o provedor implementado.

> Se a empresa já contrata outro bureau (Serasa, Boa Vista, Infosimples...),
> basta criar uma classe com o método `consultar(cpf) -> Resultado` em
> `cpf_checker/providers.py`. O resto (leitura, cache, relatório) é reaproveitado.

## Instalação

```bash
cd cpf-inativo-checker
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# se for ler direto do banco, instale também o driver (ver requirements.txt)
```

Credenciais (Loja SERPRO → Área do cliente → Consumer Key / Consumer Secret):

```bash
export SERPRO_CONSUMER_KEY=...
export SERPRO_CONSUMER_SECRET=...
```

## Uso

**A partir de uma planilha exportada do sistema:**

```bash
python -m cpf_checker --arquivo clientes.xlsx
```

A coluna com "cpf" no nome é detectada sozinha. Se não for o caso, use
`--coluna-cpf NOME_DA_COLUNA`. CPF com ou sem pontuação e com zeros à esquerda
perdidos pelo Excel é tratado.

**Direto do banco de dados:**

```bash
export DB_URL="postgresql+psycopg2://usuario:senha@host:5432/erp"
python -m cpf_checker --sql "SELECT id, nome, cpf FROM clientes WHERE tipo_pessoa = 'F'"
```

Formatos de `DB_URL` para outros bancos estão em `cpf_checker/sources.py`
(MySQL, SQL Server, Oracle, SQLite).

**Recomendado na primeira vez:** rodar com um lote pequeno para validar
credenciais e custo:

```bash
python -m cpf_checker --arquivo clientes.xlsx --limite 20
```

### Opções úteis

| Opção | Para quê |
|-------|----------|
| `--saida arquivo.xlsx\|.csv` | Onde gravar o relatório (padrão `resultado_cpfs.xlsx`) |
| `--somente-inativos` | Grava só os inativos/indeterminados |
| `--limite N` | Consulta no máximo N CPFs nesta execução |
| `--workers N` / `--por-segundo N` | Paralelismo e teto de requisições por segundo (padrão 4 / 5) |
| `--validade-cache DIAS` | Quanto tempo reaproveitar um resultado já consultado (padrão 30) |
| `--sem-cache` | Força consultar tudo de novo |
| `--trial` | Ambiente de demonstração do SERPRO (sem custo, só CPFs de teste da documentação) |
| `--provedor fake` | Roda o fluxo inteiro sem rede (tudo "Regular"), para testar leitura/relatório |

## O relatório

O Excel de saída tem três abas:

- **Inativos**: clientes com CPF inativo ou cuja situação não pôde ser determinada;
- **Todos**: a base original com as colunas adicionadas;
- **Resumo**: contagem por situação.

Colunas adicionadas: `cpf_formatado`, `status_consulta` (`ok`,
`nao_encontrado`, `cpf_invalido`, `cpf_vazio`, `erro`, `nao_consultado`),
`situacao_codigo`, `situacao_receita`, `nome_receita`, `ano_obito`,
`inativo` (`SIM` / `NAO` / `indeterminado`), `erro`, `fonte`.

## Economia de consultas

Cada consulta ao SERPRO é cobrada, então a ferramenta:

1. valida os dígitos verificadores localmente, e CPF inválido não vai para a API;
2. remove CPFs duplicados, consultando cada um só uma vez;
3. guarda os resultados em cache (`.cache_cpf.sqlite`) por 30 dias. Rodar de
   novo, ou retomar após uma queda, só consulta o que falta;
4. `--limite` permite processar a base em lotes.

Erros temporários (limite de requisições 429, falhas 5xx, rede) são re-tentados
com espera progressiva. Credencial inválida interrompe a execução na hora.

## LGPD

- Cache e relatórios contêm dados pessoais. Ficam no `.gitignore` e **não
  devem ser versionados** nem compartilhados fora de quem precisa.
- Os logs mostram o CPF mascarado (`529.***.***-25`).
- A finalidade da consulta (ex.: saneamento cadastral, prevenção a fraude)
  deve estar amparada numa base legal da LGPD. Vale alinhar com o DPO.

## Testes

```bash
python -m pytest -q
```

Os testes não acessam a rede (a API SERPRO é simulada).
