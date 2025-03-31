import streamlit as st

# Qualquer página criada deve ser incluida aqui.

def Navbar():
    with st.sidebar:
        st.page_link("app.py", label="Bancos", icon='🏦')
        st.page_link("pages/ecommerce.py", label="Ecommerce", icon='🛒')
        # Main Script
