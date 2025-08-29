import pandas as pd
import streamlit as st
import sys
import os
import logging
from src.sidebars import Navbar
from src import llm_agent

# Configuração básica do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the current directory of main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
# Append the root folder to sys.path
root_folder = os.path.join(current_dir, 'src', '..')
sys.path.append(root_folder)
from src import parcelas,classifier, banks #, llm_agent

# Configuração do Streamlit
st.set_page_config(page_title='easy-financ-export',layout='centered')

Navbar()

try:

    st.title('XP Investimentos')

    xp_file = st.file_uploader("Jogue aqui o arquivo .csv XP Investimentos")
    logging.info(f"Iniciando tratamento dos dados da XP Investimentos...")

    xp_raw,xp = banks.transform_xp(xp_file=xp_file)
    logging.info(f"xp_raw: {xp_raw.shape}, xp: {xp.shape} processados com sucesso.")
    logging.info(xp.head(5))

    option1 = st.checkbox("*Classificar transações ?*",value=False,key='xp_classifier')

    # Valor total da fatura
    total_xp = xp['Valor'].str.replace(',','.').astype('float64').sum()
    st.metric("Valor Parcial",round(total_xp,2))

    if option1:
        xp_class = banks.classify_xp(xp)
        logging.info(f"Transações classificadas com sucesso.")
        logging.info(xp_class.head(5))

        st.dataframe(banks.display_xp(xp_class))
    else:
        st.dataframe(banks.display_xp(xp))

    option2 = st.checkbox("*Quer detalhar suas parcelas ?*",key='xp_parcelas')

    if option2:

        try:
            xp_parcelas = llm_agent.LLMAgent(xp_raw).llm_parcelas_analyser(llm_agent='genai')
            st.write(xp_parcelas.round(0))
#        try:
#            xp_report,fig,fig2 = parcelas.execute_analysis(xp_raw,xp_class)
#
#            st.data_editor(xp_report.round(1),disabled=True)
#            st.plotly_chart(fig)   
#            st.plotly_chart(fig2)   
#
        except Exception as e:
            print(f"An exception occurred: {e}")
            pass

except Exception as e:
    logging.info(f"An error occurred: {e}")

st.title('Itau')

try:

    itau_file = st.file_uploader("Jogue aqui o arquivo .xls Itau")

    itau = pd.read_excel(itau_file)

    try: #Possivelmente antiga forma do itau gerar xls.

        itau = itau.iloc[itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0]+1:itau.loc[itau['Logotipo Itaú'] == 'lançamentos futuros'].index[0],0:4] #+1 para ignorar linha lançamento

    except: #Caso seja a nova forma 22/01/2022

        itau = itau.iloc[itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0]+1:,0:4]

    nome_antigo = itau.columns.to_list()

    novos_nomes = ['data','lançamento','ag./origem','valor (R$)']

    dictionary = dict(zip(nome_antigo, novos_nomes))

    itau.rename(columns=dictionary,inplace=True)

    sujeiras = ['SALDO ANTERIOR','REND PAGO APLIC AUT MAIS',
                'SDO CTA/APL AUTOMATICAS','SALDO DO DIA',
                'SALDO TOTAL DISPONÃVEL DIA',
                'REND PAGO APLIC AUT APR']

    itau = itau.loc[itau.lançamento.isin(sujeiras)==False]

    itau['valor (R$)'] = itau['valor (R$)'].astype('str').str.replace('.',',')

    st.dataframe(itau)
    
except Exception as e:
    print(f"An error occurred: {e}")


# itaucard:

try:


    itau_card_file = st.file_uploader("Jogue aqui o arquivo .xls Itaucard")

    itau_card_file = pd.read_excel(itau_card_file)

    logging.info(f"Arquivo Itaucard carregado com sucesso. Shape: {itau_card_file.shape}")

    itau_card = itau_card_file.iloc[itau_card_file.loc[itau_card_file['Logotipo Itaú'] == 'data'].index[0]:].drop(columns='Unnamed: 2') #Localiza primeiros registros baseado na coluna "data"

    itau_card = itau_card.dropna().dropna().drop_duplicates().reset_index(drop=True)

    itau_card = itau_card.rename(columns=itau_card.iloc[0])

    itau_card = itau_card.iloc[1:]

    itau_card['valor'] = itau_card['valor'].astype('str').str.replace('.',',')

    st.dataframe(itau_card)

except Exception as e:
    print(f"An error occurred: {e}")


## Nubank

st.title('Nubank')

try:

    nu_file = st.file_uploader("Jogue aqui o arquivo .csv Nubank")

    nubank_raw = banks.transform_nubank(nu_file)

    nubank = nubank_raw.copy()

    option4 = st.checkbox("*Classificar transações ?*",value=False,key='nu_classifier')

    if option4:
        nubank = classifier.classify_complete(nubank_raw,numeric_col='Valor',cat_col='Estabelecimento')
    
    st.metric("Valor Parcial",round(nubank['Valor'].astype('float64').sum(),2))
    
    nubank['Valor'] = nubank['Valor'].astype('str').str.replace('.',',')

    st.dataframe(nubank)

    option5 = st.checkbox("**AI** - Analisar parcelas ?",key='nu_parcelas')

    if option5:

        logging.info("Iniciando análise de parcelas com LLM...")
        
        try:
            nu_parcelas = llm_agent.LLMAgent(nubank_raw).llm_parcelas_analyser(llm_agent='genai')
            st.write(nu_parcelas.round(0))
        except Exception as e:
            logging.info(f"An error occurred: {e}")


except Exception as e:
    logging.info(f"An error occurred: {e}")
