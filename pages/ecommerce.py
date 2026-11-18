import streamlit as st
import pandas as pd
import logging
from src import credit_card, ecommerce_enrichment, ecommerce_sync, postgres
from src.scrapers import (
    extract_shoppe_data,
    extract_amazon_data,
    extract_mercadolivre_data,
)
from src.sidebars import Navbar

st.set_page_config(page_title='Ecommerce', layout='wide')

Navbar()

st.title("🛒 Ecommerce & Enriquecimento de Fatura")
st.markdown(
    "Sincronize seus pedidos da Amazon com o banco de dados, faça o de/para automático na fatura ou extraia pedidos via HTML."
)

tab_enrich, tab_shopee, tab_amazon, tab_ml = st.tabs([
    "🔄 Enriquecer Fatura (Amazon)",
    "🛍️ Shopee",
    "📦 Amazon (HTML)",
    "💛 Mercado Livre",
])

with tab_enrich:
    st.subheader("1. Base de Pedidos Amazon (Sheets → Postgres)")
    col_sync1, col_sync2 = st.columns([1, 2])
    with col_sync1:
        if st.button("🔄 Sincronizar Planilha → DB", use_container_width=True, key="btn_sync_ecommerce"):
            try:
                with st.spinner("Sincronizando pedidos do Google Sheets para o PostgreSQL..."):
                    res = ecommerce_sync.sync_ecommerce_orders_to_db()
                st.success(
                    f"Sincronização concluída: **{res['total_sheet']}** pedido(s) lido(s), "
                    f"**{res['inserted']}** novo(s) inserido(s) no banco."
                )
            except Exception as e:
                st.error("Erro ao sincronizar planilha com o banco. Verifique a configuração no .env e as permissões.")
                logging.error(f"Erro no sync ecommerce: {e}")

    orders_df = pd.DataFrame()
    try:
        psql = postgres.PostgresUploader()
        orders_df = psql.get_ecommerce_orders(days=120, origem="Amazon")
        with col_sync2:
            st.info(f"📦 **{len(orders_df)} pedido(s) Amazon** disponíveis no banco (últimos 120 dias).")
    except Exception as e:
        with col_sync2:
            st.warning("Não foi possível consultar a tabela de pedidos no PostgreSQL.")
        logging.error(f"Erro ao consultar ecommerce_orders: {e}")

    if not orders_df.empty:
        with st.expander("Visualizar pedidos Amazon salvos no DB", expanded=False):
            st.dataframe(orders_df[["data", "pedido_id", "descricao", "valor"]], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("2. De/Para Automático na Fatura")
    cc_file = st.file_uploader(
        "Suba a fatura do cartão (.csv — Nubank ou XP Investimentos)",
        type=["csv"],
        key="enrich_cc_uploader",
    )

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        days_before = st.number_input("Dias antes do pedido (tolerância)", min_value=0, max_value=15, value=2)
    with col_w2:
        days_after = st.number_input("Dias após o pedido (cobrança no envio)", min_value=0, max_value=30, value=7)

    if cc_file is not None:
        try:
            with st.spinner("Processando fatura e cruzando lançamentos Amazon..."):
                invoice = credit_card.process_credit_card_invoice(cc_file)
                df_class = credit_card.classify_invoice(invoice.df)
                enriched_df, ambiguous_map = ecommerce_enrichment.enrich_amazon_transactions(
                    df_class,
                    orders_df,
                    days_before=int(days_before),
                    days_after=int(days_after),
                )

            amazon_mask = enriched_df["match_status"] != "nao_amazon"
            total_amz = int(amazon_mask.sum())
            matched_cnt = int((enriched_df["match_status"] == "matched").sum())
            ambig_cnt = int((enriched_df["match_status"] == "ambiguo").sum())
            no_match_cnt = int((enriched_df["match_status"] == "sem_match").sum())

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Lançamentos Amazon", total_amz)
            m2.metric("Enriquecidos (Auto)", matched_cnt)
            m3.metric("Ambíguos", ambig_cnt)
            m4.metric("Sem Match", no_match_cnt)

            if ambiguous_map:
                st.markdown("#### ⚠️ Resolução de Casos Ambíguos")
                st.caption("Mais de um pedido com o mesmo valor foi encontrado na janela de datas. Selecione o produto correto:")
                for row_idx, candidates in ambiguous_map.items():
                    orig_estab = enriched_df.at[row_idx, "Estabelecimento"]
                    orig_val = enriched_df.at[row_idx, "Valor"]
                    orig_dt = enriched_df.at[row_idx, "Data"]
                    options = ["-- Manter original --"] + [
                        f"{c['descricao']} (Pedido {c['pedido_id']} | {c['data']} | R$ {c['valor']:.2f})"
                        for c in candidates
                    ]
                    choice = st.selectbox(
                        f"{orig_dt} | {orig_estab} | R$ {orig_val:.2f}",
                        options=options,
                        key=f"ambig_choice_{row_idx}",
                    )
                    if choice != "-- Manter original --":
                        sel_idx = options.index(choice) - 1
                        chosen = candidates[sel_idx]
                        enriched_df.at[row_idx, "Estabelecimento"] = f"{orig_estab} — {chosen['descricao']}"
                        enriched_df.at[row_idx, "match_status"] = "matched_manual"
                        enriched_df.at[row_idx, "pedido_id"] = chosen["pedido_id"]
                        enriched_df.at[row_idx, "descricao_produto"] = chosen["descricao"]
                        reclass = credit_card.classify_invoice(pd.DataFrame([{
                            "Data": orig_dt,
                            "Estabelecimento": chosen["descricao"],
                            "Valor": orig_val,
                        }]))
                        enriched_df.at[row_idx, "categoria"] = reclass.at[0, "categoria"]
                        if "_source" in reclass.columns:
                            enriched_df.at[row_idx, "_source"] = reclass.at[0, "_source"]

            st.markdown("#### 📋 Resultado da Fatura Enriquecida")
            only_amazon = st.toggle("Mostrar apenas lançamentos Amazon", value=False, key="toggle_only_amazon")
            view_df = enriched_df[amazon_mask].copy() if only_amazon else enriched_df.copy()

            export_cols = ["categoria", "Data", "Estabelecimento", "Valor"]
            disp_df = credit_card.format_display_df(view_df[["categoria", "_source", "Data", "Estabelecimento", "Valor"]])
            st.dataframe(credit_card.style_classified(disp_df), use_container_width=True, hide_index=True)

            csv_out = credit_card.format_display_df(enriched_df[export_cols]).to_csv(index=False, sep="\t").encode("utf-8-sig")
            st.download_button(
                label="📥 Baixar Fatura Enriquecida (TSV p/ Sheets)",
                data=csv_out,
                file_name="fatura_enriquecida_amazon.tsv",
                mime="text/tab-separated-values",
                key="dl_enriched_tsv",
            )
        except Exception as e:
            st.error(f"Erro ao enriquecer fatura: {e}")
            logging.error(f"Erro enriquecimento Amazon: {e}")

with tab_shopee:
    st.subheader("Pedidos da Shopee")
    text_shopee = st.text_area(
        "Cole o HTML dos seus pedidos da Shopee",
        height=150,
        key="html_shopee",
        placeholder="Cole o HTML completo ou outerHTML do DevTools aqui..."
    )

    if text_shopee and text_shopee.strip():
        try:
            df_shopee = extract_shoppe_data(text_shopee.strip())
            if not df_shopee.empty:
                st.success(f"Encontrado(s) {len(df_shopee)} pedido(s) na Shopee!")
                config_shopee = {
                    "descricao": st.column_config.TextColumn("Descrição", width="medium"),
                    "loja": st.column_config.TextColumn("Loja", width="medium"),
                    "preco": st.column_config.TextColumn("Preço", width="small"),
                    "status": st.column_config.TextColumn("Status", width="small"),
                    "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large"),
                }
                st.dataframe(df_shopee, column_config=config_shopee, row_height=100, hide_index=True)
                csv_shopee = df_shopee.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 Baixar pedidos Shopee (CSV)",
                    data=csv_shopee,
                    file_name="pedidos_shopee.csv",
                    mime="text/csv",
                    key="dl_shopee"
                )
            else:
                st.warning("Nenhum pedido identificado no HTML fornecido da Shopee. Verifique se copiou a página ou elementos corretos.")
        except Exception as e:
            st.error(f"Erro ao processar Shopee: {e}")
            logging.error(f"Erro Shopee: {e}")
    else:
        st.info("💡 Cole o HTML dos seus pedidos da Shopee acima.")

with tab_amazon:
    st.subheader("Pedidos da Amazon")
    text_amz = st.text_area(
        "Cole o HTML dos seus pedidos da Amazon",
        height=150,
        key="html_amz",
        placeholder="Cole o HTML completo ou outerHTML do DevTools aqui..."
    )

    if text_amz and text_amz.strip():
        try:
            df_amz = extract_amazon_data(text_amz.strip())
            if not df_amz.empty:
                st.success(f"Encontrado(s) {len(df_amz)} produto(s)/pedido(s) na Amazon!")
                config_amz = {
                    "descricao": st.column_config.TextColumn("Descrição", width="medium"),
                    "data": st.column_config.TextColumn("Data", width="medium"),
                    "preco": st.column_config.TextColumn("Preço", width="small"),
                    "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large"),
                }
                st.dataframe(df_amz, column_config=config_amz, row_height=100, hide_index=True)
                csv_amz = df_amz.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 Baixar pedidos Amazon (CSV)",
                    data=csv_amz,
                    file_name="pedidos_amazon.csv",
                    mime="text/csv",
                    key="dl_amz"
                )
            else:
                st.warning("Nenhum pedido identificado no HTML fornecido da Amazon. Verifique se copiou a página ou elementos corretos.")
        except Exception as e:
            st.error(f"Erro ao processar Amazon: {e}")
            logging.error(f"Erro Amazon: {e}")
    else:
        st.info("💡 Cole o HTML dos seus pedidos da Amazon acima.")

with tab_ml:
    st.subheader("Pedidos do Mercado Livre")
    text_ml = st.text_area(
        "Cole o HTML dos seus pedidos do Mercado Livre",
        height=150,
        key="html_ml",
        placeholder="Cole o HTML completo ou outerHTML do DevTools aqui..."
    )

    if text_ml and text_ml.strip():
        try:
            df_ml = extract_mercadolivre_data(text_ml.strip())
            if not df_ml.empty:
                st.success(f"Encontrado(s) {len(df_ml)} pedido(s) no Mercado Livre!")
                config_ml = {
                    "descricao": st.column_config.TextColumn("Descrição", width="medium"),
                    "data": st.column_config.TextColumn("Data", width="medium"),
                    "preco": st.column_config.TextColumn("Preço", width="small"),
                    "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large"),
                }
                st.dataframe(df_ml, column_config=config_ml, row_height=100, hide_index=True)
                csv_ml = df_ml.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 Baixar pedidos Mercado Livre (CSV)",
                    data=csv_ml,
                    file_name="pedidos_mercadolivre.csv",
                    mime="text/csv",
                    key="dl_ml"
                )
            else:
                st.warning("Nenhum pedido identificado no HTML fornecido do Mercado Livre. Verifique se copiou a página ou elementos corretos.")
        except Exception as e:
            st.error(f"Erro ao processar Mercado Livre: {e}")
            logging.error(f"Erro Mercado Livre: {e}")
    else:
        st.info("💡 Cole o HTML dos seus pedidos do Mercado Livre acima.")
