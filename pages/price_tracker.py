"""Página de Monitoramento e Histórico de Preços da Amazon com Plotly."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src.sidebars import Navbar
from src.price_tracker_service import (
    add_product_to_db,
    toggle_product_status,
    get_tracked_products_df,
    get_price_history_df,
    calculate_distribution_stats,
    extract_asin,
)

st.set_page_config(page_title="Rastreador de Preços", layout="wide", page_icon="🏷️")
Navbar()

st.title("🏷️ Monitor & Rastreador de Preços Amazon")
st.caption("Acompanhe a evolução de preços dos seus produtos monitorados e analise a distribuição histórica das ofertas.")

tab_analytics, tab_catalog = st.tabs(["📊 Análise de Preços & Séries Temporais", "➕ Gerenciar Catálogo"])

# ==============================================================================
# ABA 1: ANÁLISE DE PREÇOS & SÉRIE TEMPORAL
# ==============================================================================
with tab_analytics:
    df_products = get_tracked_products_df()

    if df_products.empty:
        st.warning("Nenhum produto cadastrado no banco de dados. Cadastre um link na aba 'Gerenciar Catálogo'.")
    else:
        # Seletor de produto
        prod_options = {}
        for _, row in df_products.iterrows():
            label = f"{row['name']} ({row['asin']})"
            prod_options[label] = row

        selected_label = st.selectbox("Selecione o produto para visualizar:", options=list(prod_options.keys()))
        selected_prod = prod_options[selected_label]
        asin = selected_prod["asin"]

        df_history = get_price_history_df(asin)

        if df_history.empty:
            st.info(f"O produto **{selected_prod['name']}** ainda não possui coletas de preços registradas no banco.")
        else:
            stats = calculate_distribution_stats(df_history)

            # --- Cards de Métricas Principais ---
            st.markdown("### 📌 Indicadores Gerais")
            m1, m2, m3, m4, m5 = st.columns(5)
            
            diff_curr_min = stats["current_price"] - stats["min_price"]
            diff_curr_min_str = f"+R$ {diff_curr_min:.2f}" if diff_curr_min > 0 else "Na mínima!"
            
            m1.metric("Preço Atual", f"R$ {stats['current_price']:.2f}")
            m2.metric("Mínima Histórica", f"R$ {stats['min_price']:.2f}", delta=diff_curr_min_str, delta_color="inverse")
            m3.metric("Média Histórica", f"R$ {stats['mean_price']:.2f}")
            m4.metric("Máxima Histórica", f"R$ {stats['max_price']:.2f}")
            m5.metric("Total de Coletas", f"{len(df_history)}")

            st.divider()

            # --- Gráfico 1: Série Temporal Plotly ---
            st.markdown("### 📈 Evolução Temporal de Preços")

            fig_ts = go.Figure()

            # Linha de preços
            fig_ts.add_trace(go.Scatter(
                x=df_history["scraped_at"],
                y=df_history["price"],
                mode="lines+markers",
                name="Preço Coletado",
                line=dict(color="#1f77b4", width=2.5),
                marker=dict(size=5, color="#1f77b4"),
                hovertemplate="<b>Data:</b> %{x|%d/%m/%Y %H:%M}<br><b>Preço:</b> R$ %{y:.2f}<extra></extra>"
            ))

            # Linha de Mínima Histórica
            fig_ts.add_hline(
                y=stats["min_price"],
                line_dash="dash",
                line_color="#2ca02c",
                annotation_text=f"Mínima: R$ {stats['min_price']:.2f}",
                annotation_position="bottom left"
            )

            # Linha de Média Histórica
            fig_ts.add_hline(
                y=stats["mean_price"],
                line_dash="dot",
                line_color="#7f7f7f",
                annotation_text=f"Média: R$ {stats['mean_price']:.2f}",
                annotation_position="top left"
            )

            # Controles de zoom e range slider
            fig_ts.update_layout(
                title=f"Histórico de Preços — {selected_prod['name']}",
                xaxis_title="Data da Coleta",
                yaxis_title="Preço (R$)",
                hovermode="x unified",
                template="plotly_white",
                height=450,
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

            st.divider()

            # --- Gráfico 2 & Simulador: Distribuição e Posição do Preço ---
            st.markdown("### 🎯 Distribuição de Preços & Análise de Posição")
            st.caption("Verifique como um preço específico se posiciona em relação a todo o histórico de coletas registradas.")

            col_input, col_rec = st.columns([1, 2])
            with col_input:
                simulated_price = st.number_input(
                    "Simular Preço (R$):",
                    min_value=0.01,
                    max_value=float(stats["max_price"] * 2),
                    value=float(stats["current_price"]),
                    step=1.0,
                    help="Digite um preço que encontrou hoje para avaliar sua posição na distribuição histórica."
                )
            
            sim_stats = calculate_distribution_stats(df_history, test_val=simulated_price)

            with col_rec:
                st.markdown(f"#### Avaliação: {sim_stats['recommendation']}")
                st.markdown(
                    f"O valor de **R$ {simulated_price:.2f}** está no **percentil {sim_stats['percentile']:.1f}%** "
                    f"— sendo **mais barato que {sim_stats['cheaper_than_pct']:.1f}%** de todo o histórico!"
                )

            # Histograma com Limites Mínimo e Máximo
            fig_dist = go.Figure()

            fig_dist.add_trace(go.Histogram(
                x=df_history["price"],
                nbinsx=25,
                name="Frequência de Preços",
                marker_color="#a6c8e0",
                opacity=0.8,
                hovertemplate="Faixa de Preço: R$ %{x}<br>Registros: %{y}<extra></extra>"
            ))

            # Limite Mínimo
            fig_dist.add_vline(
                x=stats["min_price"],
                line_width=2.5,
                line_color="#2ca02c",
                annotation_text=f"Mín: R$ {stats['min_price']:.2f}",
                annotation_position="top left"
            )

            # Mediana
            fig_dist.add_vline(
                x=stats["median_price"],
                line_width=2,
                line_dash="dot",
                line_color="#1f77b4",
                annotation_text=f"Mediana: R$ {stats['median_price']:.2f}",
                annotation_position="bottom left"
            )

            # Limite Máximo
            fig_dist.add_vline(
                x=stats["max_price"],
                line_width=2.5,
                line_color="#d62728",
                annotation_text=f"Máx: R$ {stats['max_price']:.2f}",
                annotation_position="top right"
            )

            # Linha do Preço Avaliado / Simulado
            fig_dist.add_vline(
                x=simulated_price,
                line_width=3.5,
                line_dash="dash",
                line_color="#ff7f0e",
                annotation_text=f"Seu Preço: R$ {simulated_price:.2f} (P{sim_stats['percentile']:.0f}%)",
                annotation_position="top"
            )

            fig_dist.update_layout(
                title=f"Distribuição de Preços com Limites — {selected_prod['name']}",
                xaxis_title="Preço (R$)",
                yaxis_title="Quantidade de Coletas",
                template="plotly_white",
                height=420,
                bargap=0.08
            )

            st.plotly_chart(fig_dist, use_container_width=True)

# ==============================================================================
# ABA 2: GERENCIAR CATÁLOGO (DIRETO NO BANCO DE DADOS)
# ==============================================================================
with tab_catalog:
    st.subheader("Cadastrar Novo Link no Banco de Dados")
    st.markdown("Adicione produtos da Amazon para serem monitorados. Os dados são salvos diretamente na tabela `scrapers.amazon_products`.")

    with st.form("form_add_product_db", clear_on_submit=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            prod_url = st.text_input("URL do Produto na Amazon*", placeholder="https://www.amazon.com.br/dp/B0XXXXXXXX")
            prod_name = st.text_input("Nome / Descrição amigável*", placeholder="ex: Areia Higiênica Viva Verde 4kg")
        with col2:
            prod_cat = st.selectbox("Categoria", options=["Pet", "Eletrônicos", "Casa & Cozinha", "Livros", "Alimentos & Bebidas", "Saúde & Cuidados", "Outros"])
            prod_active = st.checkbox("Ativar monitoramento imediatamente", value=True)

        btn_save = st.form_submit_button("💾 Salvar Produto no Banco", use_container_width=True)

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
                    st.success(f"✅ Produto '{added['name']}' (ASIN: {added['asin']}) cadastrado com sucesso na tabela `scrapers.amazon_products`!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar produto: {e}")

    st.divider()
    st.subheader("Produtos Cadastrados no Banco (`scrapers.amazon_products`)")

    df_db_prods = get_tracked_products_df()
    if not df_db_prods.empty:
        st.dataframe(
            df_db_prods[["asin", "name", "category", "is_active", "created_at", "url"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Nenhum produto cadastrado no momento.")
