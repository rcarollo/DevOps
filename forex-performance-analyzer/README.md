# Forex Performance Analyzer

Dashboard interativo (Streamlit) que analisa o histórico de operações de uma
conta Forex e mostra métricas de performance: taxa de acerto, fator de lucro,
drawdown, ganhos/perdas médios, melhores e piores horários e dias da semana
para operar, desempenho por par e por duração da operação.

## Fontes de dados

A aplicação aceita duas formas de trazer seus dados:

1. **Conexão direta ao MetaTrader 5** (conta, senha e servidor — como na
   tela de login do terminal). Usa o pacote oficial `MetaTrader5`, que só
   funciona em **Windows com o terminal MT5 instalado localmente** (ele
   conversa com o terminal em execução na máquina, não com um servidor
   remoto). Suas credenciais **não são gravadas em disco** — ficam em
   memória apenas durante a sessão do navegador.
2. **Importação de arquivo** (CSV ou HTML exportado do MT4/MT5). Funciona
   em qualquer sistema operacional, inclusive neste tipo de ambiente
   Linux/contêiner. Use esta opção se você não estiver no Windows ou não
   quiser digitar sua senha na aplicação.
   - No terminal MT5/MT4: aba **Histórico da conta** → clique com o botão
     direito → **Salvar como relatório** (HTML) ou exporte a lista para CSV.
   - O importador reconhece automaticamente as colunas mais comuns
     (símbolo, tipo, volume, horário de abertura/fechamento, preços,
     comissão, swap, lucro), então não é necessário um template exato.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Em Mac/Linux, o pacote `MetaTrader5` não será instalado (é restrito a
Windows via `sys_platform == "win32"` no `requirements.txt`) — use a
importação de arquivo.

## Rodando o dashboard

```bash
streamlit run app.py
```

Abra o endereço mostrado no terminal (por padrão `http://localhost:8501`).

## O que a análise mostra

- **Visão geral**: curva de capital (equity curve), distribuição de
  resultado por trade, proporção de vitórias/derrotas.
- **Horários**: lucro e taxa de acerto por hora do dia (horário de abertura
  da operação) — identifica seus melhores e piores horários para operar.
- **Dias da semana**: lucro e taxa de acerto por dia da semana.
- **Pares**: desempenho por par/símbolo negociado.
- **Duração**: desempenho por faixa de duração da operação (scalp, curto,
  médio, longo prazo).
- **Trades**: tabela com as melhores/piores operações e o histórico
  completo, com filtros por par e por período.

Métricas de topo: total de trades, taxa de acerto, lucro líquido, fator de
lucro, ganho médio, perda média, drawdown máximo e maior sequência de
perdas consecutivas.

## Estrutura do projeto

```
app.py                   # Dashboard Streamlit (interface e orquestração)
src/
  mt5_connector.py        # Login e busca de histórico via MetaTrader5
  data_import.py          # Normalização de deals MT5 e importação de CSV/HTML
  metrics.py               # Métricas de performance (win rate, drawdown, etc.)
  analysis.py               # Quebras por horário, dia da semana, par, duração
  charts.py                  # Construção dos gráficos (Plotly)
tests/                        # Testes unitários com dados sintéticos
```

## Testes

```bash
pip install pytest
pytest tests/ -v
```

Os testes cobrem a lógica de métricas, agregações e normalização de dados
com trades sintéticas — não dependem de uma conta MT5 real.

## Segurança

- As credenciais do MT5 digitadas no dashboard **não são persistidas** em
  nenhum arquivo, banco de dados ou log pela aplicação.
- Nunca commite senha, número de conta ou qualquer credencial em arquivos
  do projeto. Não há `.env` com segredos neste repositório.
- Se for expor este dashboard além do seu próprio computador (ex: em um
  servidor), adicione autenticação própria na frente dele — o Streamlit,
  por padrão, não tem controle de acesso.
