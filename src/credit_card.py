import unicodedata
from dataclasses import dataclass
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


def load_csv(filepath) -> pd.DataFrame:
    """Carrega CSV tentando separador vírgula e, se insuficiente, ponto-e-vírgula."""
    if hasattr(filepath, 'seek'):
        filepath.seek(0)
    try:
        df = pd.read_csv(filepath, sep=',', encoding='utf-8')
    except Exception:
        if hasattr(filepath, 'seek'):
            filepath.seek(0)
        df = pd.read_csv(filepath, sep=',', encoding='latin-1')

    if len(df.columns) >= 3:
        return df

    if hasattr(filepath, 'seek'):
        filepath.seek(0)
    try:
        return pd.read_csv(filepath, sep=';', encoding='utf-8')
    except Exception:
        if hasattr(filepath, 'seek'):
            filepath.seek(0)
        return pd.read_csv(filepath, sep=';', encoding='latin-1')


def detect_bank(df: pd.DataFrame) -> str:
    """Identifica o banco/emissor pelo schema de colunas do DataFrame."""
    cols = set(df.columns)
    if {'date', 'title', 'amount'}.issubset(cols):
        return 'nubank'
    if {'Data', 'Estabelecimento', 'Valor'}.issubset(cols):
        return 'xp'
    raise ValueError(f"Schema de fatura não reconhecido. Colunas encontradas: {list(df.columns)}")


BANK_NAMES = {
    'nubank': 'Nubank',
    'xp': 'XP Investimentos',
}


def parse_xp_amount(val) -> float:
    """Converte valor da fatura XP para float com 2 casas decimais."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return round(float(val), 2)
    val_str = str(val).replace('R$', '').replace('\xa0', '').strip()
    if not val_str:
        return 0.0

    negative = False
    if val_str.startswith('-') or (val_str.startswith('(') and val_str.endswith(')')):
        negative = True
        val_str = val_str.strip('-()').strip()

    if ',' in val_str and '.' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'):
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')

    try:
        num = float(val_str)
        return round(-num if negative else num, 2)
    except ValueError:
        return 0.0


def transform_xp(xp_file):
    """ 
    Input: xp_raw.csv (ou DataFrame), cols = ['Data', 'Estabelecimento', 'Portador', 'Valor', 'Parcela']
    Output: xp, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    """
    if isinstance(xp_file, pd.DataFrame):
        xp_raw = xp_file.copy()
    else:
        xp_raw = load_csv(xp_file)

    xp = xp_raw.copy()
    xp['Valor'] = xp['Valor'].astype(str).str.replace(r'R\$', '', regex=True)
    xp = xp.loc[xp['Estabelecimento'] != 'Pagamentos Validos Normais']
    
    return xp_raw, xp


def classify_xp(xp):
    """
    Input: xp, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: xp_class, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64'] 
    """
    xp_class = classify_complete(xp)
    xp_class['Valor'] = xp_class['Valor'].apply(lambda x: round(float(x), 2))

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
    
    df2['Valor'] = df2['Valor'].str.replace(r'R\$', '', regex=True)

    # Eliminando pagamento anterior
    df2 = df2.loc[df2['Estabelecimento'] != 'Pagamento recebido']
     
    return df2


def parse_nubank_amount(val) -> float:
    """Converte o valor do Nubank para float, aceitando tanto '.' quanto ',' como separador decimal."""
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
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def transform_nubank(nu_file):
    if isinstance(nu_file, pd.DataFrame):
        nubank_raw = nu_file.copy()
    else:
        nubank_raw = load_csv(nu_file)

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


@dataclass
class CardInvoiceResult:
    """Resultado estruturado e padronizado do processamento de uma fatura de cartão."""
    bank: str
    bank_name: str
    df: pd.DataFrame
    raw_df: pd.DataFrame
    total_amount: float
    has_installments: bool


def process_credit_card_invoice(file_or_df) -> CardInvoiceResult:
    """Lê e processa fatura de cartão de crédito detectando automaticamente o banco (Nubank, XP).
    
    Retorna CardInvoiceResult contendo:
    - bank: 'nubank' ou 'xp'
    - bank_name: 'Nubank' ou 'XP Investimentos'
    - df: DataFrame normalizado com colunas ['Data', 'Estabelecimento', 'Valor'] (Valor como float64)
    - raw_df: DataFrame original preservado (para análise de parcelas ou auditoria)
    - total_amount: float soma dos lançamentos da fatura
    - has_installments: booleano indicando suporte ao módulo de parcelas
    """
    if isinstance(file_or_df, pd.DataFrame):
        raw = file_or_df.copy()
    else:
        raw = load_csv(file_or_df)

    bank = detect_bank(raw)
    bank_name = BANK_NAMES.get(bank, bank.upper())

    if bank == 'nubank':
        raw_df = raw.copy()
        clean_df = transform_nubank(raw_df)
        clean_df['Valor'] = clean_df['Valor'].astype('float64')
        clean_df = clean_df[['Data', 'Estabelecimento', 'Valor']].reset_index(drop=True)
    elif bank == 'xp':
        raw_df, xp_clean = transform_xp(raw)
        clean_df = xp_clean.copy()
        clean_df['Valor'] = clean_df['Valor'].apply(parse_xp_amount)
        clean_df = clean_df[['Data', 'Estabelecimento', 'Valor']].reset_index(drop=True)
    else:
        raise ValueError(f"Banco '{bank}' não suportado.")

    total = round(float(clean_df['Valor'].sum()), 2)
    has_installments = bank in ('nubank', 'xp')

    return CardInvoiceResult(
        bank=bank,
        bank_name=bank_name,
        df=clean_df,
        raw_df=raw_df,
        total_amount=total,
        has_installments=has_installments,
    )


def classify_invoice(df: pd.DataFrame) -> pd.DataFrame:
    """Classifica as transações da fatura e formata os valores numéricos com 2 casas decimais."""
    df_class = classify_complete(df, numeric_col='Valor', cat_col='Estabelecimento')
    df_class['Valor'] = df_class['Valor'].apply(lambda x: round(float(x), 2))
    return df_class


def format_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Formata o DataFrame para exibição amigável ao usuário (Valor com padrão brasileiro R$ com vírgula)."""
    disp = df.copy()
    if 'Valor' in disp.columns:
        disp['Valor'] = disp['Valor'].apply(
            lambda x: f"{x:.2f}".replace('.', ',') if isinstance(x, (int, float)) else str(x).replace('.', ',')
        )
    return disp
