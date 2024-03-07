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