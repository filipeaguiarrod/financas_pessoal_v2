import pandas as pd
import numpy as np
import streamlit as st
from io import BytesIO
import sys
import os
# Get the current directory of main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
# Append the root folder to sys.path
root_folder = os.path.join(current_dir, 'src', '..')
sys.path.append(root_folder)
from src import parcelas
from src import classifier
from src import banks

st.set_page_config(page_title='easy-financ-export',layout='centered') # layout="wide",


# Function to convert csv to xlsx
@st.cache_data
def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Sheet1',index=False)
    writer.save()
    processed_data = output.getvalue()
    return processed_data


# Main Script

st.title('XP Investimentos')

try:

    xp_file = st.file_uploader("Jogue aqui o arquivo .csv XP Investimentos")

    xp_raw,xp = banks.transform_xp(xp_file=xp_file)
    xp_class = banks.classify_xp(xp)
    print(xp_class)

    option1 = st.checkbox("*Classificar transações ?*",value=True)

    if option1: # Classificar transações.
        st.dataframe(banks.display_xp(xp_class))
    else:
        st.dataframe(banks.display_xp(xp))

    xp_xlsx = to_excel(xp) # Converte para excel csv->xlsx
    st.download_button(label="Download",data=xp_xlsx,file_name='xp.xlsx')

    option2 = st.checkbox("*Quer detalhar suas parcelas ?*")

    if option2:

        try:

            xp_report,fig,fig2 = parcelas.execute_analysis(xp_raw,xp_class)

            st.data_editor(xp_report.round(1),
                            disabled=True)

            st.plotly_chart(fig)   
            st.plotly_chart(fig2)   

        except Exception as e:
            print(f"An exception occurred: {e}")
            pass

except Exception as e:
    print(f"An exception occurred: {e}")
    pass


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

    sujeiras = ['SALDO ANTERIOR','REND PAGO APLIC AUT MAIS','SDO CTA/APL AUTOMATICAS','SALDO DO DIA','SALDO TOTAL DISPONÃVEL DIA']

    itau = itau.loc[itau.lançamento.isin(sujeiras)==False]

    itau['valor (R$)'] = itau['valor (R$)'].astype('str').str.replace('.',',')
    
    #st.button(label="Copy",key=1,on_click=itau.to_clipboard(excel=True, sep=None,index=False))

    st.dataframe(itau)

    itau = to_excel(itau)

    st.download_button(label="Download",data=itau,file_name='itau.xlsx')

    
except Exception as e:
    print(f"An error occurred: {e}")


# itaucard:

try:


    itau_card_file = st.file_uploader("Jogue aqui o arquivo .xls Itaucard")

    itau_card_file = pd.read_excel(itau_card_file)

    itau_card = itau_card_file.iloc[itau_card_file.loc[itau_card_file['Logotipo Itaú'] == 'data'].index[0]:].drop(columns='Unnamed: 2') #Localiza primeiros registros baseado na coluna "data"

    itau_card = itau_card.dropna().dropna().drop_duplicates().reset_index(drop=True)

    itau_card = itau_card.rename(columns=itau_card.iloc[0])

    itau_card = itau_card.iloc[1:]

    itau_card['valor'] = itau_card['valor'].astype('str').str.replace('.',',')

    #st.button(label="Copy",key=2,on_click=itau_card.to_clipboard(excel=True, sep=None,index=False))    

    st.dataframe(itau_card)

    itau_card = to_excel(itau_card)

    st.download_button(label="Download",data=itau_card,file_name='itaucard.xlsx')

except Exception as e:
    print(f"An error occurred: {e}")


## Nubank


st.title('Nubank')
st.text('Cartão teste')


try:

    string  = st.text_area(f'Texto da fatura Nubank')

    nu_parcial = banks.transform_partial_nu(string)

    st.dataframe(nu_parcial)

    df2 = to_excel(nu_parcial)

    st.download_button(label="Download",data=nu_parcial,file_name='df2.xlsx')


except Exception as e:
    print(f"An error occurred: {e}")


try:

    nu_file = st.file_uploader("Jogue aqui o arquivo .csv Nubank")

    nubank = pd.read_csv(nu_file)

    # Editando arquivo csv para usar no google sheets.

    nubank.amount = nubank.amount.astype('str')

    nubank.amount = nubank.amount.str.replace('.',',')

    nubank.drop(columns='category',inplace=True)

    nubank = nubank[nubank.title != 'Pagamento recebido']
        
    #st.button(label="Copy",key=4,on_click=nubank.to_clipboard(excel=True, sep=None,index=False)) 
    
    st.dataframe(nubank)

    nubank = to_excel(nubank)

    st.download_button(label="Download",data=nubank,file_name='nubank.xlsx')
   
    
except Exception as e:
    print(f"An error occurred: {e}")
