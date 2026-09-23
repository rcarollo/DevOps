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
| `--gravar-tabela TABELA` | Grava a situação de cada CPF numa tabela do banco (ver Automação) |
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

## Automação: integrar com o sistema

Há duas formas, e elas podem ser usadas juntas:

| | **A. Consulta na hora (API)** | **B. Rotina agendada (tabela no banco)** |
|---|---|---|
| Como funciona | O sistema chama um endereço HTTP ao abrir, cadastrar ou aprovar o cliente | Toda noite, ou toda semana, a base inteira é verificada e o resultado vai para uma tabela |
| Quando usar | Cadastro de cliente novo, aprovação de venda/crédito | Tela de consulta, relatórios, bloqueio automático no ERP |
| Precisa mexer no sistema? | Sim: uma chamada HTTP | Só uma consulta (JOIN) na tabela `cpf_situacao` |

Nas duas, o cache evita pagar de novo por um CPF consultado nos últimos
30 dias (ajustável com `--validade-cache`).

### A. Serviço HTTP para consulta na hora

```bash
export CPF_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m cpf_checker.server --host 0.0.0.0 --porta 8080
```

O sistema faz:

```bash
curl -H "X-API-Key: $CPF_API_KEY" http://servidor:8080/cpf/529.982.247-25
```

```json
{"cpf": "52998224725", "status": "ok", "situacao_codigo": "2",
 "situacao_descricao": "Suspensa", "inativo": true, "nome": "...", "ano_obito": "", ...}
```

| Rota | Retorno |
|------|---------|
| `GET /cpf/{cpf}` | 200 com a situação; 422 se o CPF for inválido; 502 se o SERPRO recusar a credencial |
| `GET /cpf/{cpf}?forcar=1` | Ignora o cache e consulta a Receita de novo |
| `POST /cpfs` com `{"cpfs": [...]}` | Lista de resultados, até 100 CPFs por chamada |
| `GET /saude` | Monitoramento, sem chave |

No sistema, a regra fica: se `inativo` for `true`, bloquear ou alertar; se
for `null` (erro temporário), deixar seguir e verificar depois.

**Segurança:** a resposta contém dados pessoais. Rode o serviço só na rede
interna ou atrás do proxy HTTPS da empresa, nunca exposto na internet, e
guarde a `CPF_API_KEY` como segredo.

**Deixar rodando como serviço:**

- *Linux (systemd)*: `/etc/systemd/system/cpf-checker.service`
  ```ini
  [Unit]
  Description=Consulta situação de CPF
  After=network.target

  [Service]
  WorkingDirectory=/opt/cpf-inativo-checker
  EnvironmentFile=/opt/cpf-inativo-checker/.env
  ExecStart=/opt/cpf-inativo-checker/.venv/bin/python -m cpf_checker.server --host 0.0.0.0 --porta 8080
  Restart=always
  User=cpfchecker

  [Install]
  WantedBy=multi-user.target
  ```
  `sudo systemctl enable --now cpf-checker`
- *Windows*: use o [NSSM](https://nssm.cc/) para registrar
  `C:\cpf-inativo-checker\.venv\Scripts\python.exe -m cpf_checker.server --host 0.0.0.0 --porta 8080`
  como serviço, com as variáveis `SERPRO_*` e `CPF_API_KEY` em *Environment*.

### B. Rotina agendada que grava no banco

```bash
python -m cpf_checker \
  --sql "SELECT id, nome, cpf FROM clientes WHERE tipo_pessoa = 'F'" \
  --gravar-tabela cpf_situacao \
  --saida relatorios/cpfs_$(date +%F).xlsx
```

Isso cria (ou atualiza) a tabela `cpf_situacao` no mesmo banco, com uma linha
por CPF: `cpf` (só dígitos), `status_consulta`, `situacao_codigo`,
`situacao_receita`, `inativo` (`SIM`/`NAO`), `ano_obito` e `atualizado_em`.
Para usar no sistema, basta um JOIN, por exemplo numa view:

```sql
CREATE VIEW vw_clientes_cpf AS
SELECT c.*, s.situacao_receita, s.inativo, s.atualizado_em
FROM clientes c
LEFT JOIN cpf_situacao s
  ON s.cpf = LPAD(REGEXP_REPLACE(c.cpf, '[^0-9]', '', 'g'), 11, '0');  -- PostgreSQL
```

(No SQL Server/MySQL, ajuste a limpeza do CPF, ou compare direto se o
sistema já grava só os dígitos.)

O usuário do banco usado em `DB_URL` precisa ter permissão de criar e gravar
a tabela `cpf_situacao`.

**Agendar:**

- *Linux (cron)*, toda segunda às 2h: `crontab -e`
  ```
  0 2 * * 1  cd /opt/cpf-inativo-checker && set -a && . ./.env && set +a && .venv/bin/python -m cpf_checker --sql "SELECT id, cpf FROM clientes WHERE tipo_pessoa='F'" --gravar-tabela cpf_situacao --saida relatorios/cpfs.xlsx >> logs/cpf.log 2>&1
  ```
- *Windows (Agendador de Tarefas)*: crie um `rodar_cpf.bat`
  ```bat
  cd /d C:\cpf-inativo-checker
  .venv\Scripts\python.exe -m cpf_checker --sql "SELECT id, cpf FROM clientes WHERE tipo_pessoa='F'" --gravar-tabela cpf_situacao --saida relatorios\cpfs.xlsx >> logs\cpf.log 2>&1
  ```
  e agende com `schtasks /create /tn "Consulta CPF" /tr C:\cpf-inativo-checker\rodar_cpf.bat /sc weekly /d MON /st 02:00`
  (as variáveis `SERPRO_*` e `DB_URL` devem estar definidas para o usuário da tarefa).

Com o cache de 30 dias, uma rotina semanal só consulta de novo, e só paga
por, os CPFs novos ou cujo resultado venceu.

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
