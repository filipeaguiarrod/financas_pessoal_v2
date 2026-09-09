"""Página de Monitoramento e Histórico de Preços da Amazon."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src.sidebars import Navbar
from src.price_tracker_service import (
    add_product_to_db,
    toggle_product_status,
    get_tracked_products_df,
    get_price_history_df,
    get_products_summary_df,
    calculate_distribution_stats,
)

st.set_page_config(page_title="Monitor de Preços", layout="wide")
Navbar()

st.title("Monitor de Preços")
st.caption("Acompanhe o catálogo de produtos monitorados, preços mais recentes e análise estatística detalhada.")

# ==============================================================================
# BLOCO 1: GESTÃO DE PRODUTOS (CADASTRAR / ATIVAR / DESATIVAR)
# ==============================================================================
with st.expander("Gerenciar Produtos (Cadastrar / Alterar Status)", expanded=False):
    col_cadastrar, col_status = st.columns(2)

    with col_cadastrar:
        st.markdown("##### Cadastrar Novo Produto")
        with st.form("form_add_product", clear_on_submit=True):
            prod_url = st.text_input("URL do Produto na Amazon*", placeholder="https://www.amazon.com.br/dp/B0XXXXXXXX")
            prod_name = st.text_input("Nome / Descrição*", placeholder="ex: Areia Higiênica Viva Verde 4kg")
            col_cat, col_act = st.columns([2, 1])
            with col_cat:
                prod_cat = st.selectbox(
                    "Categoria",
                    options=["Pet", "Eletrônicos", "Casa & Cozinha", "Livros", "Alimentos & Bebidas", "Saúde & Cuidados", "Outros"]
                )
            with col_act:
                prod_active = st.checkbox("Ativo", value=True)

            btn_save = st.form_submit_button("Salvar Produto", use_container_width=True)

            if btn_save:
                if not prod_url or not prod_name:
                    st.error("Por favor, preencha a URL e o Nome do produto.")
                else:
                    try:
                        added = add_product_to_db(
                            name=prod_name,
                            url=prod_url,
                            category=prod_cat,
                            is_active=prod_active
                        )
                        st.success(f"Produto '{added['name']}' cadastrado com sucesso.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar produto: {e}")

    with col_status:
        st.markdown("##### Alterar Status de Monitoramento")
        df_all = get_tracked_products_df()
        if df_all.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            status_options = {
                f"{row['name']} ({row['asin']}) — {'Ativo' if row['is_active'] else 'Pausado'}": row
                for _, row in df_all.iterrows()
            }
            selected_to_toggle = st.selectbox(
                "Selecione o produto para alternar status:",
                options=list(status_options.keys()),
                key="select_product_status"
            )
            prod_to_toggle = status_options[selected_to_toggle]
            curr_active = bool(prod_to_toggle["is_active"])
            status_txt = "Ativo" if curr_active else "Pausado"
            st.write(f"Status atual: **{status_txt}**")

            if curr_active:
                if st.button("Pausar Monitoramento", use_container_width=True):
                    toggle_product_status(prod_to_toggle["asin"], False)
                    st.success(f"Monitoramento de '{prod_to_toggle['name']}' pausado.")
                    st.rerun()
            else:
                if st.button("Ativar Monitoramento", type="primary", use_container_width=True):
                    toggle_product_status(prod_to_toggle["asin"], True)
                    st.success(f"Monitoramento de '{prod_to_toggle['name']}' ativado.")
                    st.rerun()

st.divider()

# ==============================================================================
# BLOCO 2: VISÃO GLOBAL EM TABELA (TODOS OS PRODUTOS TRACKEADOS)
# ==============================================================================
st.subheader("Produtos Monitorados")

df_summary = get_products_summary_df()

if df_summary.empty:
    st.info("Nenhum produto cadastrado no banco de dados para monitoramento.")
else:
    df_display = df_summary.copy()
    df_display["status_label"] = df_display["is_active"].apply(lambda x: "Ativo" if x else "Pausado")
    df_display["latest_date_str"] = df_display["latest_scraped_at"].dt.strftime("%d/%m/%Y %H:%M").fillna("Sem coletas")

    st.dataframe(
        df_display[[
            "name",
            "category",
            "status_label",
            "min_price",
            "mean_price",
            "max_price",
            "latest_price",
            "latest_date_str",
            "total_samples"
        ]],
        column_config={
            "name": st.column_config.TextColumn("Descrição", width="large"),
            "category": st.column_config.TextColumn("Categoria", width="small"),
            "status_label": st.column_config.TextColumn("Status", width="small"),
            "min_price": st.column_config.NumberColumn("Mínima", format="R$ %.2f"),
            "mean_price": st.column_config.NumberColumn("Média", format="R$ %.2f"),
            "max_price": st.column_config.NumberColumn("Máxima", format="R$ %.2f"),
            "latest_price": st.column_config.NumberColumn("Último Preço", format="R$ %.2f"),
            "latest_date_str": st.column_config.TextColumn("Última Coleta", width="medium"),
            "total_samples": st.column_config.NumberColumn("Total Coletas", format="%d"),
        },
        use_container_width=True,
        hide_index=True
    )

st.divider()

# ==============================================================================
# BLOCO 3: BLOCO ANALÍTICO (SOB DEMANDA)
# ==============================================================================
st.subheader("Análise Detalhada")

if not df_summary.empty:
    prod_options = {
        f"{row['name']} ({row['asin']})": row
        for _, row in df_summary.iterrows()
    }

    selected_label = st.selectbox(
        "Selecione um produto para analisar:",
        options=list(prod_options.keys()),
        index=None,
        placeholder="Escolha um produto para visualizar histórico e distribuição...",
        key="select_product_analysis"
    )

    if selected_label is None:
        st.info("Selecione um produto acima para carregar a série histórica e distribuição de preços.")
    else:
        selected_prod = prod_options[selected_label]
        asin = selected_prod["asin"]
        df_history = get_price_history_df(asin)

        if df_history.empty:
            st.info(f"O produto '{selected_prod['name']}' ainda não possui coletas de preços registradas no banco.")
        else:
            stats = calculate_distribution_stats(df_history)

            # --- Gráfico de Série Temporal ---
            st.markdown("#### Evolução Temporal de Preços")

            fig_ts = go.Figure()
            fig_ts.add_trace(go.Scatter(
                x=df_history["scraped_at"],
                y=df_history["price"],
                mode="lines+markers",
                name="Preço Coletado",
                line=dict(color="#2563eb", width=2),
                marker=dict(size=4, color="#2563eb"),
                hovertemplate="<b>Data:</b> %{x|%d/%m/%Y %H:%M}<br><b>Preço:</b> R$ %{y:.2f}<extra></extra>"
            ))

            fig_ts.add_hline(
                y=stats["min_price"],
                line_dash="dash",
                line_color="#16a34a",
                annotation_text=f"Mínima: R$ {stats['min_price']:.2f}",
                annotation_position="bottom left"
            )

            fig_ts.add_hline(
                y=stats["mean_price"],
                line_dash="dot",
                line_color="#64748b",
                annotation_text=f"Média: R$ {stats['mean_price']:.2f}",
                annotation_position="top left"
            )

            fig_ts.update_layout(
                xaxis_title="Data da Coleta",
                yaxis_title="Preço (R$)",
                hovermode="x unified",
                template="plotly_white",
                height=400,
                margin=dict(l=40, r=20, t=20, b=40),
                xaxis=dict(
                    rangeselector=dict(
                        buttons=list([
                            dict(count=7, label="7D", step="day", stepmode="backward"),
                            dict(count=1, label="1M", step="month", stepmode="backward"),
                            dict(count=3, label="3M", step="month", stepmode="backward"),
                            dict(count=6, label="6M", step="month", stepmode="backward"),
                            dict(count=1, label="1A", step="year", stepmode="backward"),
                            dict(step="all", label="Tudo")
                        ])
                    ),
                    rangeslider=dict(visible=True),
                    type="date"
                )
            )

            st.plotly_chart(fig_ts, use_container_width=True)

            # --- Grid Inferior: Meia Coluna Esquerda (Métricas) + Meia Coluna Direita (Histograma) ---
            col_metrics, col_hist = st.columns([1, 1])

            with col_metrics:
                st.markdown("#### Indicadores Gerais")

                diff_min = stats["current_price"] - stats["min_price"]
                diff_min_pct = (diff_min / stats["min_price"] * 100) if stats["min_price"] > 0 else 0
                diff_min_str = f"+R$ {diff_min:.2f} (+{diff_min_pct:.1f}%)" if diff_min > 0 else "Na mínima histórica"

                metrics_records = [
                    {"Indicador": "Preço Atual", "Valor": f"R$ {stats['current_price']:.2f}"},
                    {"Indicador": "Mínima Histórica", "Valor": f"R$ {stats['min_price']:.2f}"},
                    {"Indicador": "Média Histórica", "Valor": f"R$ {stats['mean_price']:.2f}"},
                    {"Indicador": "Mediana Histórica", "Valor": f"R$ {stats['median_price']:.2f}"},
                    {"Indicador": "Máxima Histórica", "Valor": f"R$ {stats['max_price']:.2f}"},
                    {"Indicador": "Distância da Mínima", "Valor": diff_min_str},
                    {"Indicador": "Total de Coletas", "Valor": str(len(df_history))},
                    {"Indicador": "Última Coleta", "Valor": df_history["scraped_at"].max().strftime("%d/%m/%Y %H:%M")},
                ]

                st.dataframe(
                    pd.DataFrame(metrics_records),
                    use_container_width=True,
                    hide_index=True
                )

                st.markdown("##### Simular Preço")
                simulated_price = st.number_input(
                    "Preço para teste (R$):",
                    min_value=0.01,
                    max_value=float(max(stats["max_price"] * 2, 100.0)),
                    value=float(stats["current_price"]),
                    step=1.0,
                    help="Digite um valor para avaliar o percentil em relação ao histórico."
                )

                sim_stats = calculate_distribution_stats(df_history, test_val=simulated_price)
                st.markdown(f"**Avaliação:** {sim_stats['recommendation']}")
                st.caption(
                    f"R$ {simulated_price:.2f} está no percentil {sim_stats['percentile']:.1f}% "
                    f"— mais barato que {sim_stats['cheaper_than_pct']:.1f}% de todo o histórico."
                )

            with col_hist:
                st.markdown("#### Distribuição de Preços")

                fig_dist = go.Figure()
                fig_dist.add_trace(go.Histogram(
                    x=df_history["price"],
                    nbinsx=20,
                    marker_color="#93c5fd",
                    opacity=0.85,
                    hovertemplate="Faixa: R$ %{x}<br>Registros: %{y}<extra></extra>"
                ))

                fig_dist.add_vline(
                    x=stats["min_price"],
                    line_width=2,
                    line_color="#16a34a",
                    annotation_text=f"Mín: {stats['min_price']:.2f}",
                    annotation_position="top left"
                )

                fig_dist.add_vline(
                    x=stats["median_price"],
                    line_width=1.5,
                    line_dash="dot",
                    line_color="#2563eb",
                    annotation_text=f"Med: {stats['median_price']:.2f}",
                    annotation_position="bottom left"
                )

                fig_dist.add_vline(
                    x=stats["max_price"],
                    line_width=2,
                    line_color="#dc2626",
                    annotation_text=f"Máx: {stats['max_price']:.2f}",
                    annotation_position="top right"
                )

                if simulated_price:
                    fig_dist.add_vline(
                        x=simulated_price,
                        line_width=2.5,
                        line_dash="dash",
                        line_color="#ea580c",
                        annotation_text=f"Simulado: {simulated_price:.2f}",
                        annotation_position="top"
                    )

                fig_dist.update_layout(
                    template="plotly_white",
                    height=360,
                    margin=dict(l=30, r=20, t=30, b=30),
                    xaxis_title="Preço (R$)",
                    yaxis_title="Frequência",
                    bargap=0.08
                )

                st.plotly_chart(fig_dist, use_container_width=True)

