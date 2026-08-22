"""Forex Performance Analyzer — dashboard Streamlit.

Analisa o histórico de operações de uma conta Forex (via conexão direta ao
MetaTrader 5 ou importação de arquivo) e apresenta métricas de performance,
drawdown, melhores horários/dias da semana e desempenho por par.

Rodar com: streamlit run app.py
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from src import analysis, charts, metrics
from src.data_import import load_trades_from_file
from src.mt5_connector import (
    MT5ConnectionError,
    MT5Credentials,
    connect,
    disconnect,
    fetch_closed_trades,
    is_available,
)

st.set_page_config(page_title="Forex Performance Analyzer", layout="wide")
st.title("📊 Forex Performance Analyzer")

if "trades" not in st.session_state:
    st.session_state.trades = None

with st.sidebar:
    st.header("Dados da conta")
    source = st.radio("Fonte dos dados", ["Conectar ao MetaTrader 5", "Importar arquivo"])

    if source == "Conectar ao MetaTrader 5":
        if not is_available():
            st.warning(
                "O pacote MetaTrader5 só funciona em Windows com o terminal MT5 "
                "instalado localmente. Neste ambiente, use a importação de arquivo."
            )

        login = st.number_input("Número da conta", min_value=0, step=1, format="%d")
        password = st.text_input("Senha", type="password")
        server = st.text_input("Servidor (ex: SuaCorretora-Live)")
        date_from = st.date_input("De", value=dt.date.today() - dt.timedelta(days=90))
        date_to = st.date_input("Até", value=dt.date.today())

        if st.button("Conectar e buscar histórico", disabled=not is_available()):
            if not login or not password or not server:
                st.error("Preencha conta, senha e servidor.")
            else:
                creds = MT5Credentials(login=int(login), password=password, server=server)
                try:
                    with st.spinner("Conectando ao MT5 e baixando histórico..."):
                        connect(creds)
                        try:
                            trades = fetch_closed_trades(
                                dt.datetime.combine(date_from, dt.time.min),
                                dt.datetime.combine(date_to, dt.time.max),
                            )
                        finally:
                            disconnect()
                    st.session_state.trades = trades
                    st.success(f"{len(trades)} trades encontradas.")
                except MT5ConnectionError as exc:
                    st.error(str(exc))

        st.caption(
            "Suas credenciais são usadas apenas para autenticar no terminal MT5 "
            "local durante esta sessão e não são gravadas em disco."
        )

    else:
        uploaded = st.file_uploader(
            "Envie o histórico exportado do MT4/MT5 (CSV ou HTML)",
            type=["csv", "html", "htm"],
        )
        if uploaded is not None:
            try:
                st.session_state.trades = load_trades_from_file(uploaded)
                st.success(f"{len(st.session_state.trades)} trades carregadas.")
            except Exception as exc:  # noqa: BLE001 - mostrado ao usuário
                st.error(f"Não foi possível interpretar o arquivo: {exc}")

trades = st.session_state.trades

if trades is None or trades.empty:
    st.info("Conecte-se ao MT5 ou importe um arquivo para ver a análise.")
    st.stop()

# --- filtros ---
col1, col2 = st.columns(2)
symbols = sorted(trades["symbol"].dropna().unique())
selected_symbols = col1.multiselect("Filtrar por par", symbols, default=symbols)

min_date, max_date = trades["close_time"].min().date(), trades["close_time"].max().date()
date_range = col2.date_input("Período", value=(min_date, max_date), min_value=min_date, max_value=max_date)

filtered = trades[trades["symbol"].isin(selected_symbols)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[(filtered["close_time"].dt.date >= start) & (filtered["close_time"].dt.date <= end)]

if filtered.empty:
    st.warning("Nenhuma trade no filtro selecionado.")
    st.stop()

summary = metrics.summarize(filtered)

# --- cartões de métricas ---
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total de trades", summary.total_trades)
m2.metric("Taxa de acerto", f"{summary.win_rate:.1f}%")
m3.metric("Lucro líquido", f"{summary.net_profit:,.2f}")
m4.metric(
    "Fator de lucro",
    f"{summary.profit_factor:.2f}" if summary.profit_factor != float("inf") else "∞",
)

m5, m6, m7, m8 = st.columns(4)
m5.metric("Ganho médio", f"{summary.average_win:,.2f}")
m6.metric("Perda média", f"{summary.average_loss:,.2f}")
m7.metric("Drawdown máximo", f"{summary.max_drawdown:,.2f} ({summary.max_drawdown_pct:.1f}%)")
m8.metric("Maior seq. de perdas", summary.max_consecutive_losses)

tabs = st.tabs(["Visão geral", "Horários", "Dias da semana", "Pares", "Duração", "Trades"])

with tabs[0]:
    curve = metrics.equity_curve(filtered)
    st.plotly_chart(charts.equity_curve_chart(curve), use_container_width=True)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.win_loss_pie_chart(summary), use_container_width=True)
    c2.plotly_chart(charts.pnl_distribution_chart(filtered), use_container_width=True)

with tabs[1]:
    hourly = analysis.by_hour(filtered)
    st.plotly_chart(
        charts.profit_by_group_chart(hourly, "hour", "Resultado por hora do dia (horário de abertura)"),
        use_container_width=True,
    )
    st.plotly_chart(
        charts.win_rate_by_group_chart(hourly, "hour", "Taxa de acerto por hora do dia"),
        use_container_width=True,
    )
    best_hour = hourly.loc[hourly["net_profit"].idxmax()]
    st.success(
        f"Melhor horário: {int(best_hour['hour']):02d}h — lucro líquido "
        f"{best_hour['net_profit']:,.2f}, taxa de acerto {best_hour['win_rate']:.1f}%"
    )
    st.dataframe(hourly, use_container_width=True)

with tabs[2]:
    weekday = analysis.by_weekday(filtered)
    st.plotly_chart(
        charts.profit_by_group_chart(weekday, "weekday", "Resultado por dia da semana"),
        use_container_width=True,
    )
    st.dataframe(weekday, use_container_width=True)

with tabs[3]:
    by_symbol = analysis.by_symbol(filtered)
    st.plotly_chart(charts.profit_by_group_chart(by_symbol, "symbol", "Resultado por par"), use_container_width=True)
    st.dataframe(by_symbol, use_container_width=True)

with tabs[4]:
    duration = analysis.by_duration_bucket(filtered)
    st.plotly_chart(
        charts.profit_by_group_chart(duration, "duration_bucket", "Resultado por duração da operação"),
        use_container_width=True,
    )
    st.dataframe(duration, use_container_width=True)

with tabs[5]:
    best, worst = analysis.best_and_worst(filtered)
    st.subheader("Melhores trades")
    st.dataframe(best, use_container_width=True)
    st.subheader("Piores trades")
    st.dataframe(worst, use_container_width=True)
    st.subheader("Todas as trades")
    st.dataframe(filtered.sort_values("close_time", ascending=False), use_container_width=True)
