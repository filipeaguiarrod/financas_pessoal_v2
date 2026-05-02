import pandas as pd
import logging
from . import classifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

_SOURCE_COLORS = {
    'historico': 'background-color: #1565C0; color: white',
    'modelo':    'background-color: #E65100; color: white',
    'rules':     '',
}

def style_classified(df: pd.DataFrame):
    '''Apply color coding to the categoria column based on classification source.
    Returns a Styler if _source is present, otherwise the plain DataFrame.'''
    if '_source' not in df.columns or 'categoria' not in df.columns:
        return df

    def _apply(d):
        styles = pd.DataFrame('', index=d.index, columns=d.columns)
        styles['categoria'] = d['_source'].map(_SOURCE_COLORS).fillna('')
        return styles

    return df.style.apply(_apply, axis=None).hide(['_source'], axis='columns')

def transform_xp(xp_file):

    """ 
    Input: xp_raw.csv, cols = ['Data', 'Estabelecimento', 'Portador', 'Valor', 'Parcela']
    Output: xp, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'

    """
    xp_raw = pd.read_csv(xp_file,sep=';',encoding='utf-8')
    xp = xp_raw.copy()
    xp['Valor'] = xp['Valor'].str.replace('R\$', '', regex=True)
    xp = xp.loc[xp['Estabelecimento']!='Pagamentos Validos Normais']
    
    return xp_raw, xp

def classify_xp(xp):

    """
    Input: xp, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: xp_class, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64'] 
    """
    xp_class = classifier.classify_complete(xp)
    xp_class['Valor'] = xp_class['Valor'].apply(lambda x: round(x,2))

    return xp_class

def display_xp(xp_class):

    """
    Input: xp_class, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64']
    (or)
    Input: xp_class, ['categoria', 'Data', 'Estabelecimento','Parcela','Portador', 'Valor'], types=['object','object','object','float64']
    Output: xp_class_disp, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','str'] 
    """

    xp_class_disp = xp_class.copy()
    xp_class_disp['Valor'] = xp_class_disp['Valor'].astype('str')
    xp_class_disp['Valor'] = xp_class_disp['Valor'].str.replace('.',',')
    try:
         xp_class_disp = xp_class_disp.drop(columns=['Parcela','Portador']).copy()
    except:
        pass
    
    return xp_class_disp

def transform_itau(itau_file) -> pd.DataFrame:
    """Lê o XLS do Itau e retorna DataFrame com lançamentos limpos.

    Saída:
        data        (str) data do lançamento
        lançamento  (str) descrição
        ag./origem  (str) agência de origem
        valor (R$)  (str) valor formatado com vírgula
    """
    itau = pd.read_excel(itau_file)

    sujeiras = [
        'SALDO ANTERIOR', 'REND PAGO APLIC AUT MAIS',
        'SDO CTA/APL AUTOMATICAS', 'SALDO DO DIA',
        'SALDO TOTAL DISPONÃVEL DIA', 'REND PAGO APLIC AUT APR',
    ]

    try:
        inicio = itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0] + 1
        fim = itau.loc[itau['Logotipo Itaú'] == 'lançamentos futuros'].index[0]
        itau = itau.iloc[inicio:fim, 0:4]
    except Exception:
        inicio = itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0] + 1
        itau = itau.iloc[inicio:, 0:4]

    itau.columns = ['data', 'lançamento', 'ag./origem', 'valor (R$)']
    itau = itau.loc[~itau['lançamento'].isin(sujeiras)]
    itau['valor (R$)'] = itau['valor (R$)'].astype('str').str.replace('.', ',')

    return itau


def transform_itaucard(itau_card_file) -> pd.DataFrame:
    """Lê o XLS do Itaucard e retorna DataFrame com lançamentos limpos.

    Saída:
        data   (str) data do lançamento
        lançamento (str) descrição
        valor  (str) valor formatado com vírgula
    """
    df = pd.read_excel(itau_card_file)
    logging.info(f"Arquivo Itaucard carregado. Shape: {df.shape}")

    inicio = df.loc[df['Logotipo Itaú'] == 'data'].index[0]
    itau_card = df.iloc[inicio:].drop(columns='Unnamed: 2')
    itau_card = itau_card.dropna().drop_duplicates().reset_index(drop=True)
    itau_card = itau_card.rename(columns=itau_card.iloc[0]).iloc[1:]
    itau_card['valor'] = itau_card['valor'].astype('str').str.replace('.', ',')

    return itau_card


def transform_partial_nu(nubank_html:str)->pd.DataFrame:
    # Recebe uma string com html e transforma em dataframe,
    # copiado direto do site da nubank

    df = pd.read_html(nubank_html,encoding='utf-8')

    df2 = df[0].dropna(how='all')
    df2[0] = df2[0].fillna(method='ffill')
    df2 = df2[[0,3,4]]

    df2 = df2.rename(columns={
        0:'Data',
        3:'Estabelecimento',
        4:'Valor'
        })
    
    df2['Valor'] = df2['Valor'].str.replace('R\$', '', regex=True)

    #Eliminando pagamento anterior
    df2 = df2.loc[df2['Estabelecimento']!='Pagamento recebido']
     
    return df2

def transform_nubank(nu_file):
    nubank_raw = pd.read_csv(nu_file)

    nubank = nubank_raw.copy()
    nubank['title'] = nubank['title'].str.replace(r' - Parcela.*', '', case=False, regex=True).str.strip()
    nubank.amount = nubank.amount.astype('str')
    nubank = nubank[nubank.title != 'Pagamento recebido']
    nubank = nubank.rename(columns={
        'date':'Data',
        'title':'Estabelecimento',
        'amount':'Valor'
        })

    return nubank
   
    