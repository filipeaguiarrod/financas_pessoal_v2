import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src import parcelas

BANK_COLORS = {'Nubank': '#5C2D91', 'XP Investimentos': "#B5B4B4"}


def different_months_warning(bank_data: dict) -> str | None:
    """Retorna mensagem de aviso se as faturas forem de meses diferentes, ou None."""
    months = {label: v[1] for label, v in bank_data.items()}
    if len(set(months.values())) > 1:
        details = " | ".join(f"{label}: {m.strftime('%m/%Y')}" for label, m in months.items())
        return f"As faturas são de meses diferentes — os valores podem não ser diretamente comparáveis. ({details})"
    return None


def bank_pie(bank_data: dict, invoice_month) -> go.Figure:
    """Retorna rosca com total a ser pago por banco."""
    pizza_data = []
    for label, (std_df, _) in bank_data.items():
        ct = parcelas.build_crosstable(std_df, invoice_month)
        m_cols = [c for c in ct.columns if c not in ('estabelecimento', 'qtd_parcelas_faltantes')]
        pizza_data.append({'Banco': label, 'Total': round(ct[m_cols].sum().sum(), 2)})

    df_pizza = pd.DataFrame(pizza_data)
    fig = px.pie(
        df_pizza,
        names='Banco',
        values='Total',
        title='Total a ser pago por banco',
        hole=0.55,
        color='Banco',
        color_discrete_map=BANK_COLORS,
    )
    fig.update_traces(textinfo='percent+value')
    fig.update_layout(
        legend=dict(orientation='h', yanchor='bottom', y=-0.2, xanchor='center', x=0.5),
    )
    return fig


def estab_bar(df: pd.DataFrame, month_cols: list) -> go.Figure:
    """Retorna barra horizontal com total a ser pago por estabelecimento."""
    df_estab = df.copy()
    df_estab['Total'] = df_estab[month_cols].sum(axis=1).round(2)
    df_estab = (
        df_estab.groupby('estabelecimento')['Total']
        .sum()
        .round(2)
        .sort_values()
        .reset_index()
        .rename(columns={'estabelecimento': 'Estabelecimento'})
    )

    fig = px.bar(
        df_estab,
        x='Total',
        y='Estabelecimento',
        orientation='h',
        title='Total a ser pago por estabelecimento',
        text='Total',
    )
    fig.update_traces(texttemplate='R$ %{text:.2f}', textposition='outside')
    fig.update_layout(yaxis_title=None, xaxis_title='R$', height=500)
    return fig


def month_bar(df: pd.DataFrame, month_cols: list) -> go.Figure:
    """Retorna gráfico de colunas com total a ser pago por mês."""
    df_months = (
        df[month_cols].sum()
        .round(2)
        .reset_index()
        .rename(columns={'index': 'Mês', 0: 'Total'})
    )

    fig = px.bar(
        df_months,
        x='Mês',
        y='Total',
        title='Total a ser pago por mês',
        text='Total',
    )
    fig.update_traces(texttemplate='R$ %{text:.2f}', textposition='outside')
    fig.update_layout(xaxis_title=None, yaxis_title='R$')
    return fig
