import streamlit as st
import pandas as pd
import logging
from src.scrapers import (
    extract_shoppe_data,
    extract_amazon_data,
    extract_mercadolivre_data,
)
from src.sidebars import Navbar

st.set_page_config(page_title='Ecommerce', layout='wide')

Navbar()

st.title("🛒 Extrator de Pedidos de Ecommerce")
st.markdown(
    "Cole o HTML ou elementos copiados via Inspecionar Elemento (DevTools) para visualizar seus pedidos."
)

tab_shopee, tab_amazon, tab_ml = st.tabs(["🛍️ Shopee", "📦 Amazon", "💛 Mercado Livre"])

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
