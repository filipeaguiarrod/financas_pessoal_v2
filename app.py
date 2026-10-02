import logging
import streamlit as st
import pandas as pd
from src import credit_card, checking_account, installments
from src.sidebars import Navbar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='easy-financ-export', layout='centered')

Navbar()

# Custom CSS for a minimalist, clean, larger layout without borders/dividers
st.markdown("""
<style>
    /* Aumenta a distância abaixo do título principal (h1) */
    h1 {
        margin-bottom: 3.5rem !important;
    }
    /* Remove expander borders, shadows, and default background */
    div[data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        margin-bottom: 2rem !important;
        padding: 0 !important;
    }
    /* Make expander titles larger and bolder */
    div[data-testid="stExpander"] details summary p {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    /* Remove default details outline/border */
    div[data-testid="stExpander"] details {
        border: none !important;
    }
    /* Clean up headers inside the expanders */
    .stSubheader p {
        font-size: 1.4rem !important;
        font-weight: 600 !important;
        margin-top: 1.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("Extratos & Faturas")


def classification_legend(show_modelo=True):
    items = [
        '<span style="color:gray">■ Regras</span>',
        '<span style="color:#1565C0">■ Histórico</span>',
    ]
    if show_modelo:
        items.append('<span style="color:#E65100">■ Modelo</span>')
    st.markdown('<small>' + '&nbsp;&nbsp;'.join(items) + '</small>', unsafe_allow_html=True)


# --- Drill Down: Cartão de Crédito ---
with st.expander("💳 Cartão de Crédito", expanded=False):
    try:
        cc_file = st.file_uploader(
            "Jogue aqui o arquivo da fatura (.csv — Nubank ou XP Investimentos)",
            type=['csv'],
            key='cc_invoice_uploader'
        )
        if cc_file is not None:
            invoice = credit_card.process_credit_card_invoice(cc_file)
            logging.info(f"Fatura processada: banco={invoice.bank}, shape={invoice.df.shape}")

            st.success(f"Fatura identificada: **{invoice.bank_name}**")
            st.metric("Valor Parcial", round(invoice.total_amount, 2))

            col_t1, col_t2 = st.columns(2)
            with col_t1:
                classify = st.toggle("*Classificar transações ?*", value=False, key='cc_classifier')
            with col_t2:
                show_installments = False
                if invoice.has_installments:
                    show_installments = st.toggle("Analisar parcelas", key='cc_installments')

            if classify:
                df_class = credit_card.classify_invoice(invoice.df)
                classification_legend()
                disp_df = credit_card.format_display_df(df_class)
                st.dataframe(credit_card.style_classified(disp_df), use_container_width=True)
            else:
                disp_df = credit_card.format_display_df(invoice.df)
                st.dataframe(disp_df, use_container_width=True)

            if show_installments:
                st.dataframe(
                    installments.display_crosstable(installments.pipeline_from_df(invoice.raw_df)),
                    use_container_width=True,
                    height=600 if invoice.bank == 'xp' else None
                )
    except Exception as e:
        logging.info(f"Cartão de Crédito: {e}")
        st.error(f"Erro ao processar fatura: {e}")


# --- Drill Down: Conta Corrente ---
with st.expander("🏦 Conta Corrente", expanded=False):
    itau_file = None
    bradesco_file = None

    # --- Itau ---
    try:
        st.subheader('Itau')
        itau_file = st.file_uploader("Jogue aqui o arquivo .xls Itau")
        if itau_file is not None:
            itau = checking_account.transform_itau(itau_file)

            if st.toggle("*Classificar transações ?*", value=False, key='itau_classifier'):
                itau = checking_account.classify_checking_account(itau)
                itau['valor (R$)'] = itau['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                classification_legend(show_modelo=False)
                st.dataframe(checking_account.style_classified(itau))
            else:
                st.dataframe(itau)
    except Exception as e:
        logging.info(f"Itau: {e}")
        st.error(f"Erro ao processar extrato Itaú: {e}")

    # --- Bradesco ---
    try:
        st.subheader('Bradesco')
        bradesco_file = st.file_uploader("Jogue aqui o arquivo .csv Bradesco")
        if bradesco_file is not None:
            bradesco = checking_account.transform_bradesco(bradesco_file)

            if st.toggle("*Classificar transações ?*", value=False, key='bradesco_classifier'):
                bradesco = checking_account.classify_checking_account(bradesco)
                bradesco['valor (R$)'] = bradesco['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                classification_legend(show_modelo=False)
                st.dataframe(checking_account.style_classified(bradesco))
            else:
                st.dataframe(bradesco)
    except Exception as e:
        logging.info(f"Bradesco: {e}")
        st.error(f"Erro ao processar extrato Bradesco: {e}")

    # --- Consolidação (quando ambos forem carregados) ---
    if itau_file is not None and bradesco_file is not None:
        try:
            st.subheader('Extrato Consolidado')
            itau_raw = checking_account.transform_itau(itau_file)
            bradesco_raw = checking_account.transform_bradesco(bradesco_file)

            # Consolidar usando as regras de filtragem
            merged = checking_account.consolidate_checking_accounts(itau_raw, bradesco_raw)

            if st.toggle("*Classificar transações consolidadas ?*", value=False, key='consolidated_classifier'):
                merged_class = checking_account.classify_checking_account(merged)
                merged_class['valor (R$)'] = merged_class['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                classification_legend(show_modelo=False)
                st.dataframe(checking_account.style_classified(merged_class))
            else:
                st.dataframe(merged)
        except Exception as e:
            logging.info(f"Consolidação: {e}")
            st.error(f"Erro ao consolidar os extratos: {e}")
