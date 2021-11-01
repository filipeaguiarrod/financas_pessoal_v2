import pandas as pd
import numpy as np
import streamlit as st
from io import BytesIO

st.set_page_config(page_title='easy-financ-export') # layout="wide",


# Function to convert csv to xlsx
@st.cache
def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Sheet1',index=False)
    writer.save()
    processed_data = output.getvalue()
    return processed_data


# Main Script

st.title('Nubank')

# Condição de tranformar texto em df editável.

try:

    string  = st.text_area(f'Texto da fatura Nubank')

    string = string.replace('\t','\n') # Padroniza para tornar possível criar uma lista com split('\n')

    three_split = np.array_split(string.split('\n'),len(string.split('\n'))/3) # dado que quero 3 colunas divide tamanho da lista e retorna o que preciso

    nubank_parcial = pd.DataFrame(three_split,columns=['data','descrição','valor'])

    nubank_parcial = nubank_parcial[nubank_parcial.descrição != 'Pagamento recebido']

    st.dataframe(nubank_parcial)

    nubank_parcial = to_excel(nubank_parcial)

    st.download_button(label="Download",data=nubank_parcial,file_name='nubank_parcial.xlsx')


except:

    pass




try:

    nu_file = st.file_uploader("Jogue aqui o arquivo .csv Nubank")

    nubank = pd.read_csv(nu_file)

    # Editando arquivo csv para usar no google sheets.

    nubank.amount = nubank.amount.astype('str')

    nubank.amount = nubank.amount.str.replace('.',',')

    nubank.drop(columns='category',inplace=True)

    nubank = nubank[nubank.title != 'Pagamento recebido']

    st.dataframe(nubank)

    nubank = to_excel(nubank)

    st.download_button(label="Download",data=nubank,file_name='nubank.xlsx')

except:

    pass


st.title('Itau')

try:

    itau_file = st.file_uploader("Jogue aqui o arquivo .xls Itau")

    itau = pd.read_excel(itau_file)

    itau = itau.iloc[itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0]+1:itau.loc[itau['Logotipo Itaú'] == 'lançamentos futuros'].index[0],0:4] #+1 para ignorar linha lançamento

    nome_antigo = itau.columns.to_list()

    novos_nomes = ['data','lançamento','ag./origem','valor (R$)']

    dictionary = dict(zip(nome_antigo, novos_nomes))

    itau.rename(columns=dictionary,inplace=True)

    sujeiras = ['SALDO ANTERIOR','REND PAGO APLIC AUT MAIS','SDO CTA/APL AUTOMATICAS','SALDO DO DIA']

    itau = itau.loc[itau.lançamento.isin(sujeiras)==False]

    itau['valor (R$)'] = itau['valor (R$)'].astype('str').str.replace('.',',')

    st.dataframe(itau)

    itau = to_excel(itau)

    st.download_button(label="Download",data=itau,file_name='itau.xlsx')


except:

    pass
