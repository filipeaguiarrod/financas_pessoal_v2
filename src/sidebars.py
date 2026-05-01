import streamlit as st
import os

# Determine the root directory dynamically
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Qualquer página criada deve ser incluida aqui.

def Navbar():
    with st.sidebar:
        st.page_link(os.path.join(ROOT_DIR, "app.py"), label="Bancos", icon='🏦')
        st.page_link(os.path.join(ROOT_DIR, "pages", "parcelas.py"), label="Parcelas", icon='💳')
        st.page_link(os.path.join(ROOT_DIR, "pages", "ecommerce.py"), label="Ecommerce", icon='🛒')
        # Main Script
    return