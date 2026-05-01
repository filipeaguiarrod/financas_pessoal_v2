import logging
import streamlit as st
from src import banks, classifier, parcelas
from src.sidebars import Navbar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='easy-financ-export', layout='centered')

Navbar()


# --- XP Investimentos ---

try:
    st.title('XP Investimentos')

    xp_file = st.file_uploader("Jogue aqui o arquivo .csv XP Investimentos")
    xp_raw, xp = banks.transform_xp(xp_file=xp_file)
    logging.info(f"XP processado: xp_raw={xp_raw.shape}, xp={xp.shape}")

    total_xp = xp['Valor'].str.replace(',', '.').astype('float64').sum()
    st.metric("Valor Parcial", round(total_xp, 2))

    if st.toggle("*Classificar transações ?*", value=False, key='xp_classifier'):
        xp_class = banks.classify_xp(xp)
        st.dataframe(banks.display_xp(xp_class))
    else:
        st.dataframe(banks.display_xp(xp))

    if st.toggle("Analisar parcelas", key='xp_parcelas'):
        st.dataframe(parcelas.display_crosstable(parcelas.pipeline_from_df(xp_raw)), use_container_width=True, height=600)

except Exception as e:
    logging.info(f"XP: {e}")


# --- Itau ---

try:
    st.title('Itau')
    itau_file = st.file_uploader("Jogue aqui o arquivo .xls Itau")
    st.dataframe(banks.transform_itau(itau_file))

except Exception as e:
    logging.info(f"Itau: {e}")


# --- Itaucard ---

try:
    st.title('Itaucard')
    itau_card_file = st.file_uploader("Jogue aqui o arquivo .xls Itaucard")
    st.dataframe(banks.transform_itaucard(itau_card_file))

except Exception as e:
    logging.info(f"Itaucard: {e}")


# --- Nubank ---

try:
    st.title('Nubank')

    nu_file = st.file_uploader("Jogue aqui o arquivo .csv Nubank")
    nubank_raw = parcelas.load_csv(nu_file)
    nu_file.seek(0)
    nubank = banks.transform_nubank(nu_file)

    if st.toggle("*Classificar transações ?*", value=False, key='nu_classifier'):
        nubank = classifier.classify_complete(nubank, numeric_col='Valor', cat_col='Estabelecimento')

    st.metric("Valor Parcial", round(nubank['Valor'].astype('float64').sum(), 2))
    nubank['Valor'] = nubank['Valor'].astype('str').str.replace('.', ',')
    st.dataframe(nubank)

    if st.toggle("Analisar parcelas", key='nu_parcelas'):
        st.dataframe(parcelas.display_crosstable(parcelas.pipeline_from_df(nubank_raw)), use_container_width=True, height=600)

except Exception as e:
    logging.info(f"Nubank: {e}")
