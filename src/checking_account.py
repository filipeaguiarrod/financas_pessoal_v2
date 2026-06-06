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


def transform_itau(itau_file) -> pd.DataFrame:
    """Lê o XLS do Itau e retorna DataFrame com lançamentos limpos.

    Saída:
        data        (str) data do lançamento
        lançamento  (str) descrição
        ag./origem  (str) agência de origem
        valor (R$)  (str) valor formatado com vírgula
    """
    itau_file.seek(0)
    itau = pd.read_excel(itau_file)

    def _ascii_upper(s: str) -> str:
        # Remove non-ASCII chars before comparing — handles encoding variants
        # e.g. DISPONÍVEL and DISPONÃVEL both become DISPONVEL
        return ''.join(c for c in str(s) if c.isascii()).upper().strip()

    sujeiras = {
        _ascii_upper(s) for s in [
            'SALDO ANTERIOR', 'REND PAGO APLIC AUT MAIS',
            'SDO CTA/APL AUTOMATICAS', 'SALDO DO DIA',
            'SALDO TOTAL DISPONÍVEL DIA', 'REND PAGO APLIC AUT APR',
        ]
    }

    try:
        inicio = itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0] + 1
        fim = itau.loc[itau['Logotipo Itaú'] == 'lançamentos futuros'].index[0]
        itau = itau.iloc[inicio:fim, 0:4]
    except Exception:
        inicio = itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0] + 1
        itau = itau.iloc[inicio:, 0:4]

    itau.columns = ['data', 'lançamento', 'ag./origem', 'valor (R$)']
    itau = itau.loc[~itau['lançamento'].apply(lambda x: _ascii_upper(x) in sujeiras)]
    itau['valor (R$)'] = itau['valor (R$)'].astype('str').str.replace('.', ',')
    itau['ag./origem'] = 'ITAU'

    return itau


def classify_checking_account(df, cat_col='lançamento', numeric_col='valor (R$)'):
    '''
    Classify checking account transactions using rules + historical DB only (no ML model).
    Input: df from transform_itau() — cols ['data', 'lançamento', 'ag./origem', 'valor (R$)']
    Output: same df + ['categoria', '_source']
    '''
    df = df.copy()
    df['categoria'] = None
    df['_source'] = None

    logging.info('Conta corrente: classificando através das regras do usuário...')
    df = classifier.rules_classifier(df, cat_col=cat_col)
    logging.info('Conta corrente: classificando através do histórico...')
    df = classifier.primary_classifier(df, numeric_col=numeric_col, cat_col=cat_col, table='checking_account')
    logging.info('Conta corrente: classificação concluída.')

    df = df.drop(columns=['valor_round'], errors='ignore')
    df['categoria'] = df['categoria'].fillna("")
    other_cols = [c for c in df.columns if c not in ('categoria', '_source')]
    return df[['categoria', '_source'] + other_cols]


def transform_bradesco(bradesco_file) -> pd.DataFrame:
    """Lê o CSV do Bradesco e retorna DataFrame com lançamentos limpos no mesmo formato do Itaú.

    Saída:
        data        (str) data do lançamento (DD/MM/AAAA)
        lançamento  (str) descrição
        ag./origem  (str) documento/origem
        valor (R$)  (str) valor formatado com vírgula
    """
    import re

    # Lê o conteúdo do arquivo
    content = ""
    try:
        bradesco_file.seek(0)
        content = bradesco_file.read().decode('utf-8')
    except Exception:
        bradesco_file.seek(0)
        content = bradesco_file.read().decode('latin-1')

    lines = content.splitlines()
    logging.info(f"Bradesco Upload: Conteudo lido ({len(content)} bytes), {len(lines)} linhas.")
    logging.info(f"Bradesco Primeiras 5 linhas: {lines[:5]}")

    parsed_rows = []
    last_row = None

    # Padrão de data: DD/MM/YY ou DD/MM/YYYY
    date_pattern = re.compile(r'^\d{2}/\d{2}/\d{2,4}$')

    def clean_val(val_str):
        if not val_str:
            return 0.0
        val_str = val_str.replace('"', '').strip()
        if not val_str:
            return 0.0
        val_str = val_str.replace('.', '').replace(',', '.')
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    sujeiras = {
        'SALDO ANTERIOR', 'TOTAL DO DIA', 'TOTAL', 'SALDO INVEST FÁCIL',
        'SALDO INVEST FACIL', 'ÚLTIMOS LANÇAMENTOS', 'ULTIMOS LANCAMENTOS'
    }

    match_count = 0
    for line_idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(';')]
        if len(parts) < 2:
            continue

        date_str = parts[0]

        # Verifica se começa com uma data válida
        if date_pattern.match(date_str):
            history = parts[1]

            # Verifica se é lixo
            upper_history = ''.join(c for c in history if c.isascii()).upper().strip()
            if any(s in upper_history for s in sujeiras):
                continue

            docto = parts[2] if len(parts) > 2 else ""

            # Créditos / Débitos
            credito_str = parts[3] if len(parts) > 3 else ""
            debito_str = parts[4] if len(parts) > 4 else ""

            credito = clean_val(credito_str)
            debito = clean_val(debito_str)

            # Débito precisa ser negativo (costuma já ter o menos no Bradesco)
            if debito > 0:
                debito = -debito
            elif debito == 0.0 and credito == 0.0:
                # Pula linhas sem valores monetários
                continue

            val = credito if credito != 0.0 else debito

            # Normaliza a data para DD/MM/AAAA
            date_parts = date_str.split('/')
            if len(date_parts[2]) == 2:
                date_str = f"{date_parts[0]}/{date_parts[1]}/20{date_parts[2]}"

            last_row = {
                'data': date_str,
                'lançamento': history,
                'ag./origem': docto,
                'valor': val
            }
            parsed_rows.append(last_row)
            match_count += 1

        elif date_str == "" and len(parts) > 1 and parts[1] != "":
            # Linha de continuação de descrição
            desc = parts[1]
            upper_desc = ''.join(c for c in desc if c.isascii()).upper().strip()
            if any(s in upper_desc for s in sujeiras):
                continue

            if last_row is not None:
                last_row['lançamento'] += f" - {desc}"

    logging.info(f"Bradesco Upload: Linhas que deram match com data: {match_count}. Linhas parseadas final: {len(parsed_rows)}")

    # Cria o DataFrame
    df = pd.DataFrame(parsed_rows)
    if df.empty:
        return pd.DataFrame(columns=['data', 'lançamento', 'ag./origem', 'valor (R$)'])

    df['valor (R$)'] = df['valor'].map(lambda x: f"{x:.2f}".replace('.', ','))
    df = df.drop(columns=['valor'])
    df['ag./origem'] = 'BRAD'

    return df[['data', 'lançamento', 'ag./origem', 'valor (R$)']]

