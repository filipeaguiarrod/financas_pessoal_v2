import pandas as pd
from . import classifier


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