import re
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta


def parse_brl(value: str) -> float:
    """Converte string no formato BRL (ex: 'R$ 1.234,56') para float."""
    cleaned = re.sub(r'R\$', '', str(value))
    cleaned = cleaned.strip().replace('.', '').replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def load_csv(filepath) -> pd.DataFrame:
    """Carrega CSV tentando separador vírgula e, se insuficiente, ponto-e-vírgula."""
    df = pd.read_csv(filepath, sep=',', encoding='utf-8')
    if len(df.columns) >= 3:
        return df
    if hasattr(filepath, 'seek'):
        filepath.seek(0)
    return pd.read_csv(filepath, sep=';', encoding='utf-8')


def detect_bank(df: pd.DataFrame) -> str:
    """Identifica o banco pelo schema de colunas do DataFrame."""
    cols = set(df.columns)
    if {'date', 'title', 'amount'}.issubset(cols):
        return 'nubank'
    if {'Data', 'Estabelecimento', 'Parcela', 'Valor'}.issubset(cols):
        return 'xp'
    raise ValueError(f"Schema não reconhecido. Colunas: {list(df.columns)}")


def parse_dates(raw: pd.DataFrame, bank: str) -> pd.Series:
    """Converte a coluna de data do banco para pd.Series de datetime."""
    if bank == 'nubank':
        return pd.to_datetime(raw['date'], errors='coerce')
    return pd.to_datetime(raw['Data'], format='%d/%m/%Y', errors='coerce')


def extract_invoice_month(raw: pd.DataFrame, bank: str) -> datetime:
    """Retorna o primeiro dia do mês de referência da fatura."""
    max_date = parse_dates(raw, bank).max()
    return datetime(max_date.year, max_date.month, 1)


def parse_nubank(raw: pd.DataFrame) -> pd.DataFrame:
    """Extrai parcelas do padrão Nubank '- Parcela X/Y' e devolve tabela padronizada.

    Espelha transform_nubank em src/banks.py — mesmo padrão verb_bank.

    Saída:
        estabelecimento        (str)   nome do estabelecimento sem sufixo de parcela
        parcelas_pagas         (int)   número da parcela atual
        qtd_parcelas           (int)   total de parcelas do parcelamento
        qtd_parcelas_faltantes (int)   parcelas ainda a vencer (inclusive a atual)
        valor                  (float) valor de cada parcela
    """
    pattern = re.compile(r'- Parcela (\d+)/(\d+)')

    rows = []
    for _, row in raw.iterrows():
        title = str(row['title'])
        m = pattern.search(title)
        if not m:
            continue
        parcelas_pagas = int(m.group(1))
        qtd_parcelas = int(m.group(2))
        estabelecimento = pattern.sub('', title).strip().rstrip(' -').strip()
        rows.append({
            'estabelecimento': estabelecimento,
            'parcelas_pagas': parcelas_pagas,
            'qtd_parcelas': qtd_parcelas,
            'qtd_parcelas_faltantes': qtd_parcelas - parcelas_pagas + 1,
            'valor': float(row['amount']),
        })

    return pd.DataFrame(rows)


def parse_xp(raw: pd.DataFrame) -> pd.DataFrame:
    """Extrai parcelas do padrão XP 'X de Y' e devolve tabela padronizada.

    Espelha transform_xp em src/banks.py — mesmo padrão verb_bank.

    Saída:
        estabelecimento        (str)   nome do estabelecimento
        parcelas_pagas         (int)   número da parcela atual
        qtd_parcelas           (int)   total de parcelas do parcelamento
        qtd_parcelas_faltantes (int)   parcelas ainda a vencer (inclusive a atual)
        valor                  (float) valor de cada parcela
    """
    df = raw.copy()
    df = df[df['Estabelecimento'] != 'Pagamentos Validos Normais']
    df = df[df['Parcela'] != '-']

    pattern = re.compile(r'(\d+) de (\d+)')

    rows = []
    for _, row in df.iterrows():
        m = pattern.search(str(row['Parcela']))
        if not m:
            continue
        parcelas_pagas = int(m.group(1))
        qtd_parcelas = int(m.group(2))
        rows.append({
            'estabelecimento': row['Estabelecimento'],
            'parcelas_pagas': parcelas_pagas,
            'qtd_parcelas': qtd_parcelas,
            'qtd_parcelas_faltantes': qtd_parcelas - parcelas_pagas + 1,
            'valor': parse_brl(row['Valor']),
        })

    return pd.DataFrame(rows)


def standardize(raw: pd.DataFrame, bank: str) -> pd.DataFrame:
    """Despacha para parse_nubank ou parse_xp conforme o banco detectado.

    Saída: mesma estrutura de parse_nubank / parse_xp
        estabelecimento, parcelas_pagas, qtd_parcelas, qtd_parcelas_faltantes, valor
    """
    if bank == 'nubank':
        return parse_nubank(raw)
    return parse_xp(raw)


def build_crosstable(df: pd.DataFrame, invoice_month: datetime) -> pd.DataFrame:
    """Converte a tabela de parcelas em crosstable com colunas MM/AAAA por mês futuro.

    Saída:
        estabelecimento        (str)   nome do estabelecimento
        qtd_parcelas_faltantes (int)   parcelas ainda a vencer
        MM/AAAA ...            (float) valor da parcela no mês; NaN se não há cobrança
    """
    max_months = int(df['qtd_parcelas_faltantes'].max())
    month_cols = [
        (invoice_month + relativedelta(months=i)).strftime('%m/%Y')
        for i in range(max_months)
    ]

    result = df[['estabelecimento', 'qtd_parcelas_faltantes', 'valor']].copy().reset_index(drop=True)
    for col in month_cols:
        result[col] = None

    for idx, row in result.iterrows():
        faltantes = int(row['qtd_parcelas_faltantes'])
        cols_to_fill = month_cols[:faltantes]
        result.loc[idx, cols_to_fill] = row['valor']

    result = result.drop(columns=['valor'])
    result[month_cols] = result[month_cols].astype('float64')

    return result


def display_crosstable(df: pd.DataFrame):
    """Ordena por parcelas faltantes, adiciona TOTAL por linha/coluna e aplica estilo cinza nos totais.

    Saída (pd.Styler):
        estabelecimento        (str)   nome do estabelecimento; última linha = 'TOTAL'
        qtd_parcelas_faltantes (int)   parcelas a vencer; vazio na linha de total
        MM/AAAA ...            (float) valor da parcela no mês; vazio se não há cobrança
        TOTAL                  (float) soma dos meses por linha; soma geral na última linha
    """
    month_cols = [c for c in df.columns if c not in ('estabelecimento', 'qtd_parcelas_faltantes')]

    result = df.sort_values('qtd_parcelas_faltantes', ascending=False).reset_index(drop=True)
    result[month_cols] = result[month_cols].round(2)
    result['TOTAL'] = result[month_cols].sum(axis=1).round(2)

    totals = pd.DataFrame([{
        'estabelecimento': 'TOTAL',
        'qtd_parcelas_faltantes': '',
        **{col: round(result[col].sum(), 2) for col in month_cols},
        'TOTAL': round(result['TOTAL'].sum(), 2),
    }])

    result = pd.concat([result, totals], ignore_index=True)

    numeric_cols = month_cols + ['TOTAL']

    def _style(row):
        is_total_row = row['estabelecimento'] == 'TOTAL'
        styles = []
        for col in row.index:
            is_total_col = col == 'TOTAL'
            if is_total_row or is_total_col:
                styles.append('background-color: #d3d3d3; font-weight: bold')
            else:
                styles.append('')
        return styles

    formatter = {col: "{:.2f}" for col in numeric_cols}

    return (
        result.style
        .apply(_style, axis=1)
        .format(formatter, na_rep="")
    )


def merge_pipelines(filepaths) -> pd.DataFrame:
    """Processa múltiplas faturas e retorna crosstable consolidada.

    Saída: mesma estrutura de build_crosstable, cobrindo todos os meses das faturas recebidas.
        estabelecimento        (str)   nome do estabelecimento
        qtd_parcelas_faltantes (int)   parcelas ainda a vencer
        MM/AAAA ...            (float) valor da parcela no mês; NaN se não há cobrança
    """
    dfs_std = []
    invoice_months = []

    for fp in filepaths:
        raw = load_csv(fp)
        bank = detect_bank(raw)
        invoice_months.append(extract_invoice_month(raw, bank))
        dfs_std.append(standardize(raw, bank))

    combined = pd.concat(dfs_std, ignore_index=True)
    return build_crosstable(combined, min(invoice_months))


def pipeline_from_df(raw: pd.DataFrame) -> pd.DataFrame:
    """Executa o pipeline completo de parcelas a partir de um DataFrame já carregado."""
    bank = detect_bank(raw)
    invoice_month = extract_invoice_month(raw, bank)
    df = standardize(raw, bank)
    return build_crosstable(df, invoice_month)


def run_pipeline(filepath) -> pd.DataFrame:
    """Executa o pipeline completo de parcelas a partir de um caminho de arquivo."""
    raw = load_csv(filepath)
    bank = detect_bank(raw)
    invoice_month = extract_invoice_month(raw, bank)
    df = standardize(raw, bank)
    return build_crosstable(df, invoice_month)
