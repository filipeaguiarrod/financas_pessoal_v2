import pandas as pd
import numpy as np
import streamlit as st
from io import BytesIO

st.set_page_config(page_title='easy-financ-export') # layout="wide",


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
# Condição de tranformar texto em df editável.
# Xp Investimentos

st.title('XP Investimentos')

try:

    xp_file = st.file_uploader("Jogue aqui o arquivo .csv XP Investimentos")

    xp = pd.read_csv(xp_file,sep=';')

    # Editando arquivo csv para usar no google sheets.

    xp['Valor'] = xp['Valor'].str.replace('R\$', '', regex=True)

    xp.drop(columns=['Parcela','Portador'],inplace=True)
    
    st.button(label="Copy",key=0,on_click=xp.to_clipboard(excel=True, sep=None,index=False))
    
    st.dataframe(xp)

    xp = to_excel(xp)

    st.download_button(label="Download",data=xp,file_name='xp.xlsx')


except Exception as e:
    st.error(e)    
       
    
except:

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

    sujeiras = ['SALDO ANTERIOR','REND PAGO APLIC AUT MAIS','SDO CTA/APL AUTOMATICAS','SALDO DO DIA']

    itau = itau.loc[itau.lançamento.isin(sujeiras)==False]

    itau['valor (R$)'] = itau['valor (R$)'].astype('str').str.replace('.',',')
    
    st.button(label="Copy",key=1,on_click=itau.to_clipboard(excel=True, sep=None,index=False))

    st.dataframe(itau)

    itau = to_excel(itau)

    st.download_button(label="Download",data=itau,file_name='itau.xlsx')
    

except Exception as e:
    st.error(e)    
       
    
except:

    pass


# itaucard:

try:


    itau_card_file = st.file_uploader("Jogue aqui o arquivo .xls Itaucard")

    itau_card_file = pd.read_excel(itau_card_file)

    itau_card = itau_card_file.iloc[itau_card_file.loc[itau_card_file['Logotipo Itaú'] == 'data'].index[0]:].drop(columns='Unnamed: 2') #Localiza primeiros registros baseado na coluna "data"

    itau_card = itau_card.dropna().dropna().drop_duplicates().reset_index(drop=True)

    itau_card = itau_card.rename(columns=itau_card.iloc[0])

    itau_card = itau_card.iloc[1:]

    itau_card['valor'] = itau_card['valor'].astype('str').str.replace('.',',')

    st.button(label="Copy",key=2,on_click=itau_card.to_clipboard(excel=True, sep=None,index=False))    

    st.dataframe(itau_card)

    itau_card = to_excel(itau_card)

    st.download_button(label="Download",data=itau_card,file_name='itaucard.xlsx')


except Exception as e:
    st.error(e)    
       
    
except:

    pass


## Nubank


st.title('Nubank')


try:

    string  = st.text_area(f'Texto da fatura Nubank')

    string = string.replace('\t','\n') # Padroniza para tornar possível criar uma lista com split('\n')

    three_split = np.array_split(string.split('\n'),len(string.split('\n'))/3) # dado que quero 3 colunas divide tamanho da lista e retorna o que preciso

    nubank_parcial = pd.DataFrame(three_split,columns=['data','descrição','valor'])

    nubank_parcial = nubank_parcial[nubank_parcial.descrição != 'Pagamento recebido']
    
    st.button(label="Copy",key=3,on_click=nubank_parcial.to_clipboard(excel=True, sep=None,index=False))    

    st.dataframe(nubank_parcial)

    nubank_parcial = to_excel(nubank_parcial)

    st.download_button(label="Download",data=nubank_parcial,file_name='nubank_parcial.xlsx')

except Exception as e:
    st.error(e)    
    

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
        
    st.button(label="Copy",key=4,on_click=nubank.to_clipboard(excel=True, sep=None,index=False)) 
    
    st.dataframe(nubank)

    nubank = to_excel(nubank)

    st.download_button(label="Download",data=nubank,file_name='nubank.xlsx')
    

except Exception as e:
    st.error(e)    
       
    
except:

    pass
