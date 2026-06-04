import streamlit as st
import pandas as pd
import logging
from src.scrapers import parse_shoppe, parse_amazon, parse_mercadolivre
from src.sidebars import Navbar

st.set_page_config(page_title='Ecommerce',layout='wide') # layout="wide",

Navbar()

try:
    st.title('Shopee')
    html_text = st.text_input("Cole aqui o HTML da sua página de compras Shopee",key='html_shopee')
    
    parse_shoppe(html_text)

except Exception as e:
    logging.error(f"Erro Shopee: {e}")

try:
    st.title('Amazon')
    html_amz = st.text_input("Cole aqui o HTML da sua página de compras Amazon",key='html_amz')

    parse_amazon(html_amz)

except Exception as e:
    logging.error(f"Erro Amazon: {e}")

try:
    st.title('Mercado Livre')
    html_ml = st.text_input("Cole aqui o HTML da sua página de compras Mercado Livre",key='html_ml')

    parse_mercadolivre(html_ml)

except Exception as e:
    logging.error(f"Erro Mercado Livre: {e}")


