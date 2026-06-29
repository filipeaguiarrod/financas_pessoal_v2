import unicodedata
import pandas as pd
import logging
from . import classifier

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

_SOURCE_COLORS = {
    'historico': 'color: #1565C0',
    'modelo':    'color: #E65100',
    'rules':     '',
}


def style_classified(df: pd.DataFrame):
    '''Apply color coding to the categoria column based on classification source.
    Returns a Styler if _source is present, otherwise the plain DataFrame.'''
    if '_source' not in df.columns or 'categoria' not in df.columns:
        return df

    source = df['_source'].copy()
    display_df = df.drop(columns=['_source'])

    def _color_categoria(col):
        return source.map(_SOURCE_COLORS).fillna('')

    return display_df.style.apply(_color_categoria, subset=['categoria'])


def transform_xp(xp_file):
    """ 
    Input: xp_raw.csv, cols = ['Data', 'Estabelecimento', 'Portador', 'Valor', 'Parcela']
    Output: xp, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    """
    xp_raw = pd.read_csv(xp_file, sep=';', encoding='utf-8')
    xp = xp_raw.copy()
    xp['Valor'] = xp['Valor'].str.replace('R\$', '', regex=True)
    xp = xp.loc[xp['Estabelecimento'] != 'Pagamentos Validos Normais']
    
    return xp_raw, xp


def classify_xp(xp):
    """
    Input: xp, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: xp_class, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64'] 
    """
    xp_class = classify_complete(xp)
    xp_class['Valor'] = xp_class['Valor'].apply(lambda x: round(x, 2))

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
    xp_class_disp['Valor'] = xp_class_disp['Valor'].str.replace('.', ',')
    try:
         xp_class_disp = xp_class_disp.drop(columns=['Parcela', 'Portador']).copy()
    except:
        pass
    
    return xp_class_disp


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


def transform_partial_nu(nubank_html: str) -> pd.DataFrame:
    # Recebe uma string com html e transforma em dataframe,
    # copiado direto do site da nubank
    df = pd.read_html(nubank_html, encoding='utf-8')

    df2 = df[0].dropna(how='all')
    df2[0] = df2[0].fillna(method='ffill')
    df2 = df2[[0, 3, 4]]

    df2 = df2.rename(columns={
        0: 'Data',
        3: 'Estabelecimento',
        4: 'Valor'
    })
    
    df2['Valor'] = df2['Valor'].str.replace('R\$', '', regex=True)

    # Eliminando pagamento anterior
    df2 = df2.loc[df2['Estabelecimento'] != 'Pagamento recebido']
     
    return df2


def parse_nubank_amount(val) -> float:
    """Converte o valor do Nubank para float, aceitando tanto '.' quanto ',' como separador decimal.
    
    Exemplos:
    - 34.86 -> 34.86
    - 34,86 -> 34.86
    - 1,234.56 -> 1234.56 (if thousands separator is used)
    - 1.234,56 -> 1234.56 (if thousands separator is used)
    """
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if not val_str:
        return 0.0
    
    val_str = val_str.replace('R$', '').strip()
    
    # Handle case where both dot and comma are present
    if ',' in val_str and '.' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'):
            # Comma is the decimal separator (e.g. 1.234,56)
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            # Dot is the decimal separator (e.g. 1,234.56)
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        # Only comma is present (e.g. 34,86)
        val_str = val_str.replace(',', '.')
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def transform_nubank(nu_file):
    nubank_raw = pd.read_csv(nu_file)

    nubank = nubank_raw.copy()
    nubank['title'] = nubank['title'].str.replace(r' - Parcela.*', '', case=False, regex=True).str.strip()
    nubank['amount'] = nubank['amount'].apply(parse_nubank_amount)
    nubank = nubank[nubank.title != 'Pagamento recebido']
    nubank = nubank.rename(columns={
        'date': 'Data',
        'title': 'Estabelecimento',
        'amount': 'Valor'
    })

    return nubank


def classify_complete(df, numeric_col='Valor', cat_col='Estabelecimento'):
    '''
    Full classification pipeline: rules → historical DB → ML model.
    Input: df, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: df, ['categoria', '_source', 'Data', 'Estabelecimento', 'Valor']
    '''
    df = df.copy()
    df['categoria'] = None
    df['_source'] = None

    logging.info('Classificando através das regras do usuário...')
    df = classifier.rules_classifier(df, cat_col=cat_col)
    logging.info('Classificando através do banco de dados...')
    df = classifier.primary_classifier(df, numeric_col=numeric_col, cat_col=cat_col)
    logging.info('Classificando através do modelo...')
    df = classifier.secondary_classifier(df, numeric_col=numeric_col)
    logging.info('Classificado com sucesso.')

    df = df.drop(columns=['valor_round'], errors='ignore')

    try:
        return df[['categoria', '_source', 'Data', cat_col, numeric_col]]
    except KeyError:
        return df[['categoria', '_source', cat_col, numeric_col]]
