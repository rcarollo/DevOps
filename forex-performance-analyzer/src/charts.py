"""Construtores de gráficos Plotly para o dashboard Streamlit."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.metrics import PerformanceSummary

_GREEN = "#2e7d32"
_RED = "#c62828"


def equity_curve_chart(curve: pd.Series) -> go.Figure:
    fig = go.Figure(go.Scatter(x=curve.index, y=curve.values, mode="lines", line=dict(color="#1565c0")))
    fig.update_layout(
        title="Curva de capital (equity curve)",
        xaxis_title="Data",
        yaxis_title="Saldo acumulado",
    )
    return fig


def profit_by_group_chart(df: pd.DataFrame, x_col: str, title: str) -> go.Figure:
    colors = [_GREEN if v >= 0 else _RED for v in df["net_profit"]]
    fig = go.Figure(go.Bar(x=df[x_col].astype(str), y=df["net_profit"], marker_color=colors))
    fig.update_layout(title=title, xaxis_title=x_col, yaxis_title="Lucro/Prejuízo líquido")
    return fig


def win_rate_by_group_chart(df: pd.DataFrame, x_col: str, title: str) -> go.Figure:
    fig = px.bar(df, x=df[x_col].astype(str), y="win_rate", title=title)
    fig.update_layout(xaxis_title=x_col, yaxis_title="Taxa de acerto (%)")
    return fig


def pnl_distribution_chart(trades: pd.DataFrame) -> go.Figure:
    fig = px.histogram(trades, x="net_profit", nbins=40, title="Distribuição de resultado por trade")
    fig.update_layout(xaxis_title="Lucro/Prejuízo líquido", yaxis_title="Nº de trades")
    return fig


def win_loss_pie_chart(summary: PerformanceSummary) -> go.Figure:
    fig = px.pie(
        names=["Vencedoras", "Perdedoras"],
        values=[summary.wins, summary.losses],
        color=["Vencedoras", "Perdedoras"],
        color_discrete_map={"Vencedoras": _GREEN, "Perdedoras": _RED},
        title="Trades vencedoras vs. perdedoras",
    )
    return fig
