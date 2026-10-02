import streamlit as st
import os

# Determine the root directory dynamically
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Qualquer página criada deve ser incluida aqui.

def Navbar():
    with st.sidebar:
        st.markdown("""
        <style>
            /* Subitem hierárquico indentado na sidebar para Reconciliação */
            [data-testid="stSidebar"] div:has(> a[href*="reconcile"]),
            [data-testid="stSidebar"] a[href*="reconcile"] {
                margin-left: 1.25rem !important;
                padding-left: 0.5rem !important;
                border-left: 2px solid rgba(128, 128, 128, 0.35) !important;
                border-radius: 0 0.375rem 0.375rem 0 !important;
                width: calc(100% - 1.25rem) !important;
            }
        </style>
        """, unsafe_allow_html=True)
        st.page_link(os.path.join(ROOT_DIR, "app.py"), label="Bancos", icon='🏦')
        st.page_link(os.path.join(ROOT_DIR, "pages", "reconcile.py"), label="Reconciliação", icon='🔄')
        st.page_link(os.path.join(ROOT_DIR, "pages", "installments.py"), label="Parcelas", icon='💳')
        st.page_link(os.path.join(ROOT_DIR, "pages", "ecommerce.py"), label="Ecommerce", icon='🛒')
        st.markdown("---")
        st.markdown("### 💼 Backoffice")
        st.page_link(os.path.join(ROOT_DIR, "pages", "regras.py"), label="Regras do Usuário", icon='📋')
        st.page_link(os.path.join(ROOT_DIR, "pages", "etl.py"), label="ETL", icon='⚙️')
        st.page_link(os.path.join(ROOT_DIR, "pages", "price_tracker.py"), label="Monitor de Preços", icon='🏷️')
        # Main Script
    return
