import logging
import streamlit as st
from ai_agents import llm_agent
from src import banks, classifier
from src.sidebars import Navbar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='easy-financ-export', layout='centered')

Navbar()


def installment_analysis(data, provider="gemini", model_name="gemini-3-flash-preview"):
    col1, col2 = st.columns(2)
    with col1:
        provider = st.selectbox("Provider", ["gemini", "openai"])
    with col2:
        model_name = st.text_input("Model Name", value="gemini-3-flash-preview")

    try:
        with st.spinner(f'🤖 Analisando parcelas futuras com **{provider}** - **{model_name}**'):
            result = llm_agent.InstallmentAgent(provider=provider, model_name=model_name).generate_report_df(data)
        st.write(result.round(0))
        st.button("🔄 Rerun")
    except Exception as e:
        logging.error(f"Erro no agente LLM: {e}")


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

    if st.toggle("Analisar parcelas **AI**", key='xp_parcelas'):
        installment_analysis(xp_raw)

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
    nubank = banks.transform_nubank(nu_file)

    if st.toggle("*Classificar transações ?*", value=False, key='nu_classifier'):
        nubank = classifier.classify_complete(nubank, numeric_col='Valor', cat_col='Estabelecimento')

    st.metric("Valor Parcial", round(nubank['Valor'].astype('float64').sum(), 2))
    nubank['Valor'] = nubank['Valor'].astype('str').str.replace('.', ',')
    st.dataframe(nubank)

    if st.toggle("Analisar parcelas **AI**", key='nu_parcelas'):
        installment_analysis(nubank)

except Exception as e:
    logging.info(f"Nubank: {e}")
