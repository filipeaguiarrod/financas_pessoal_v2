import re
import unicodedata
import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Tuple, Dict, Any, Optional

MONTH_MAP_PT = {
    'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12
}


def normalize_establishment(text: Any) -> str:
    """Normaliza o nome do estabelecimento para comparação."""
    if text is None or pd.isna(text):
        return ""
    s = str(text).strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower()
    # Remove pontuações e múltiplos espaços
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def parse_amount(val: Any) -> float:
    """Converte valor para float positivo ou negativo com 2 casas decimais.
    Trata '54,14', 'R$ 98,65', '26.0', '26,00', etc.
    """
    if val is None or pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return round(float(val), 2)

    val_str = str(val).strip()
    if not val_str:
        return 0.0

    val_str = val_str.replace('R$', '').replace('\xa0', '').strip()
    # Identifica sinal negativo
    negative = False
    if val_str.startswith('-') or (val_str.startswith('(') and val_str.endswith(')')):
        negative = True
        val_str = val_str.strip('-()').strip()

    # Trata separador de milhar e decimal
    if ',' in val_str and '.' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'):
            # 1.234,56
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            # 1,234.56
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        # 54,14
        val_str = val_str.replace(',', '.')

    try:
        num = float(val_str)
        if negative:
            num = -num
        return round(num, 2)
    except ValueError:
        return 0.0


def parse_date(date_val: Any, default_year: Optional[int] = None) -> Tuple[Optional[date], str]:
    """Interpreta data em diversos formatos e retorna (date_obj, display_str).
    Formatos suportados:
    - '01/09/2026' ou '01/09/26'
    - '2026-09-01'
    - '16 ago.' ou '16 ago' ou '18 set.'
    """
    if date_val is None or pd.isna(date_val):
        return None, ""

    if isinstance(date_val, (datetime, pd.Timestamp)):
        d = date_val.date()
        return d, d.strftime('%d/%m/%Y')
    if isinstance(date_val, date):
        return date_val, date_val.strftime('%d/%m/%Y')

    s = str(date_val).strip().lower()
    s = s.replace('.', '').strip()

    if not default_year:
        default_year = datetime.now().year

    # 1. Formato DD/MM/YYYY ou DD/MM/YY
    match_slash = re.match(r'^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$', s)
    if match_slash:
        day = int(match_slash.group(1))
        month = int(match_slash.group(2))
        yr_part = match_slash.group(3)
        if yr_part:
            year = int(yr_part)
            if year < 100:
                year += 2000
        else:
            year = default_year
        try:
            d = date(year, month, day)
            return d, d.strftime('%d/%m/%Y')
        except ValueError:
            pass

    # 2. Formato YYYY-MM-DD
    match_iso = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if match_iso:
        try:
            d = date(int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3)))
            return d, d.strftime('%d/%m/%Y')
        except ValueError:
            pass

    # 3. Formato '16 ago' ou '18 set' ou '16 de ago'
    match_pt = re.match(r'^(\d{1,2})(?:\s+de)?\s+([a-z]{3})(?:\s+(\d{2,4}))?$', s)
    if match_pt:
        day = int(match_pt.group(1))
        mon_str = match_pt.group(2)
        yr_str = match_pt.group(3)
        if mon_str in MONTH_MAP_PT:
            month = MONTH_MAP_PT[mon_str]
            year = int(yr_str) if yr_str else default_year
            if yr_str and year < 100:
                year += 2000
            try:
                d = date(year, month, day)
                return d, d.strftime('%d/%m/%Y')
            except ValueError:
                pass

    return None, str(date_val).strip()


def is_date_like(val: str) -> bool:
    """Verifica se uma string parece uma data."""
    s = val.strip().lower().replace('.', '')
    if re.match(r'^\d{1,2}/\d{1,2}(?:/\d{2,4})?$', s):
        return True
    if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', s):
        return True
    if re.match(r'^\d{1,2}(?:\s+de)?\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)(?:\s+\d{2,4})?$', s):
        return True
    return False


def is_amount_like(val: str) -> bool:
    """Verifica se uma string parece um valor monetário."""
    s = val.strip().replace('R$', '').replace('\xa0', '').strip()
    if not s:
        return False
    # Remove sinal negativo ou parênteses com espaço opcional
    if s.startswith('-') or (s.startswith('(') and s.endswith(')')):
        s = s.strip('-()').strip()
    # Padrão: números com vírgula ou ponto decimal, suportando separador de milhar (ex: 1.234,56 ou 1,234.56 ou 36,51)
    return bool(re.match(r'^\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?$|^\d+(?:[.,]\d{1,2})?$', s))


def parse_sheets_data(raw_text: str, default_year: Optional[int] = None) -> pd.DataFrame:
    """Interpreta texto colado do Google Sheets ou tabela tabulada.
    Suporta:
    1. Formato padrão TSV (tabulado) copiado do Sheets: colunas Categoria, Data, Estabelecimento, Valor
    2. Formato vertical de linhas coladas sequencialmente
    3. CSV (separado por vírgula ou ponto-e-vírgula)
    """
    if not raw_text or not raw_text.strip():
        return pd.DataFrame(columns=['categoria', 'Data', 'Estabelecimento', 'Valor'])

    lines = [line.strip('\r') for line in raw_text.strip().split('\n')]
    lines = [l for l in lines if l.strip()]

    if not lines:
        return pd.DataFrame(columns=['categoria', 'Data', 'Estabelecimento', 'Valor'])

    # Caso 1: Linhas tabuladas (TSV) ou com separador delimitado
    if '\t' in lines[0] or ';' in lines[0] or (',' in lines[0] and not is_amount_like(lines[0])):
        sep = '\t' if '\t' in lines[0] else (';' if ';' in lines[0] else ',')
        rows = []
        for line in lines:
            parts = [p.strip() for p in line.split(sep)]
            if len(parts) >= 3:
                rows.append(parts)

        if rows:
            # Identifica ordem das colunas
            # Possibilidade 1: [Categoria, Data, Estabelecimento, Valor]
            # Possibilidade 2: [Data, Estabelecimento, Valor]
            # Possibilidade 3: [Data, Estabelecimento, Categoria, Valor]
            parsed_rows = []
            for parts in rows:
                if len(parts) == 3:
                    # Data, Estabelecimento, Valor (sem categoria)
                    p_date_obj, p_date_str = parse_date(parts[0], default_year=default_year)
                    p_amount = parse_amount(parts[2])
                    parsed_rows.append({
                        'categoria': None,
                        'Data': p_date_str or parts[0],
                        'Estabelecimento': parts[1],
                        'Valor': p_amount,
                        '_date_obj': p_date_obj
                    })
                elif len(parts) >= 4:
                    # Verifica se o primeiro é data ou se o segundo é data
                    if is_date_like(parts[0]):
                        # [Data, Estabelecimento, Categoria, Valor] ou [Data, Estabelecimento, Valor, ...]
                        p_date_obj, p_date_str = parse_date(parts[0], default_year=default_year)
                        if is_amount_like(parts[3]):
                            cat = parts[2] if parts[2] else None
                            val = parse_amount(parts[3])
                        else:
                            cat = None
                            val = parse_amount(parts[2])
                        parsed_rows.append({
                            'categoria': cat,
                            'Data': p_date_str or parts[0],
                            'Estabelecimento': parts[1],
                            'Valor': val,
                            '_date_obj': p_date_obj
                        })
                    else:
                        # Padrão: [Categoria, Data, Estabelecimento, Valor]
                        cat = parts[0] if parts[0] else None
                        p_date_obj, p_date_str = parse_date(parts[1], default_year=default_year)
                        val = parse_amount(parts[3])
                        parsed_rows.append({
                            'categoria': cat,
                            'Data': p_date_str or parts[1],
                            'Estabelecimento': parts[2],
                            'Valor': val,
                            '_date_obj': p_date_obj
                        })

            df = pd.DataFrame(parsed_rows)
            return df

    # Caso 2: Linhas em fluxo vertical (ex: copiado coluna por coluna ou células verticais)
    # Exemplo:
    # Categoria (opcional) -> Data -> Estabelecimento -> Valor
    records = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        # Se for link ou linha vazia, pula
        if line.startswith('http://') or line.startswith('https://'):
            idx += 1
            continue

        # Verifica se linha é Categoria ou Data
        if is_date_like(line):
            # Categoria em branco!
            cat = None
            date_line = line
            idx += 1
        else:
            cat = line
            idx += 1
            if idx < len(lines) and is_date_like(lines[idx]):
                date_line = lines[idx]
                idx += 1
            else:
                # Não é um padrão reconhecido, avança
                continue

        estab = lines[idx].strip() if idx < len(lines) else ""
        idx += 1

        val_line = lines[idx].strip() if idx < len(lines) else "0"
        idx += 1

        p_date_obj, p_date_str = parse_date(date_line, default_year=default_year)
        p_val = parse_amount(val_line)

        records.append({
            'categoria': cat if cat else None,
            'Data': p_date_str or date_line,
            'Estabelecimento': estab,
            'Valor': p_val,
            '_date_obj': p_date_obj
        })

    return pd.DataFrame(records)


def reconcile_transactions(
    df_sheets: pd.DataFrame,
    df_fatura: pd.DataFrame,
    default_year: Optional[int] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Reconcilia as transações mantendo a Fatura Oficial como a verdade absoluta.

    Regras de Negócio:
    1. A Fatura Oficial é a base canônica ('verdade'): toda transação consolidada
       provém da fatura. O valor total e a quantidade final coincidem 100% com a fatura.
    2. Se a transação da fatura existir na Base Validada (Sheets) e tiver categoria,
       mantém a categoria validada pelo usuário ('Mantido do Sheets').
    3. Se existir no Sheets mas sem categoria (ou categoria vazia), preenche com a
       classificação da fatura ('Preenchido da Fatura').
    4. Se for um lançamento exclusivo da fatura, inclui como novo lançamento ('Novo da Fatura').
    5. Se uma transação do Sheets NÃO existir na fatura, ela é REMOVIDA da consolidação final
       (não foi efetivada na operadora) e registrada em `df_descartados` para conferência.
    6. Trata compras duplicadas / repetidas (mesmo dia, valor e estabelecimento) 1-para-1.

    Retorna:
    (df_reconciled, summary_metrics)
    """
    empty_result_cols = ['categoria', 'Data', 'Estabelecimento', 'Valor', '_status']
    empty_descartados_cols = ['categoria', 'Data', 'Estabelecimento', 'Valor', '_motivo']

    # Caso em que a Fatura está vazia ou nula: como a fatura é a verdade,
    # nada é efetivado na consolidação final e tudo do Sheets vira descartado.
    if df_fatura is None or df_fatura.empty:
        val_antigo = 0.0
        df_descartados = pd.DataFrame(columns=empty_descartados_cols)
        if df_sheets is not None and not df_sheets.empty:
            sheets_work = df_sheets.copy()
            sheets_work['_val_num'] = sheets_work['Valor'].apply(parse_amount)
            val_antigo = round(float(sheets_work['_val_num'].sum()), 2)
            df_descartados = pd.DataFrame({
                'categoria': sheets_work['categoria'].fillna('').astype(str),
                'Data': sheets_work['Data'],
                'Estabelecimento': sheets_work['Estabelecimento'],
                'Valor': sheets_work['_val_num'],
                '_motivo': 'Não encontrado na fatura oficial (não efetivado)'
            })

        return pd.DataFrame(columns=empty_result_cols), {
            'total': 0, 'mantidos': 0, 'preenchidos': 0, 'novos': 0, 'sem_categoria': 0,
            'removidos': len(df_descartados),
            'valor_removido': round(float(df_descartados['Valor'].sum()), 2) if not df_descartados.empty else 0.0,
            'df_descartados': df_descartados,
            'valor_antigo': val_antigo, 'valor_fatura': 0.0, 'valor_novo': 0.0,
            'diff_valor': -val_antigo, 'diff_fatura': 0.0, 'bate_com_fatura': True
        }

    # Prepara cópias de trabalho
    fatura_work = df_fatura.copy()
    sheets_work = df_sheets.copy() if df_sheets is not None and not df_sheets.empty else pd.DataFrame()

    # Se não temos ano padrão, tenta inferir a partir da fatura
    if not default_year and not fatura_work.empty and 'Data' in fatura_work.columns:
        for d in fatura_work['Data']:
            m = re.search(r'(\d{4})', str(d))
            if m:
                default_year = int(m.group(1))
                break

    # Normalizações para casamento na Fatura (Base Canônica)
    if '_date_obj' not in fatura_work.columns:
        fatura_dates = [parse_date(d, default_year=default_year) for d in fatura_work['Data']]
        fatura_work['_date_obj'] = [d[0] for d in fatura_dates]
        fatura_work['Data'] = [d[1] or str(orig) for d, orig in zip(fatura_dates, fatura_work['Data'])]
    fatura_work['_val_num'] = fatura_work['Valor'].apply(parse_amount)
    fatura_work['_estab_norm'] = fatura_work['Estabelecimento'].apply(normalize_establishment)
    if 'categoria' not in fatura_work.columns:
        fatura_work['categoria'] = None

    # Normalizações para casamento no Sheets (Base Anterior)
    if not sheets_work.empty:
        if '_date_obj' not in sheets_work.columns:
            sheets_dates = [parse_date(d, default_year=default_year) for d in sheets_work['Data']]
            sheets_work['_date_obj'] = [d[0] for d in sheets_dates]
            sheets_work['Data'] = [d[1] or str(orig) for d, orig in zip(sheets_dates, sheets_work['Data'])]
        sheets_work['_val_num'] = sheets_work['Valor'].apply(parse_amount)
        sheets_work['_estab_norm'] = sheets_work['Estabelecimento'].apply(normalize_establishment)
        if 'categoria' not in sheets_work.columns:
            sheets_work['categoria'] = None
    else:
        sheets_work = pd.DataFrame(columns=['categoria', 'Data', 'Estabelecimento', 'Valor', '_date_obj', '_val_num', '_estab_norm'])

    # Chaves de casamento e contadores de ocorrência para desambiguação
    fatura_work['_match_key'] = list(zip(
        fatura_work['_date_obj'].astype(str),
        fatura_work['_val_num'],
        fatura_work['_estab_norm']
    ))
    fatura_work['_occ'] = fatura_work.groupby('_match_key').cumcount()
    fatura_work['_full_key'] = list(zip(fatura_work['_match_key'], fatura_work['_occ']))

    if not sheets_work.empty:
        sheets_work['_match_key'] = list(zip(
            sheets_work['_date_obj'].astype(str),
            sheets_work['_val_num'],
            sheets_work['_estab_norm']
        ))
        sheets_work['_occ'] = sheets_work.groupby('_match_key').cumcount()
        sheets_work['_full_key'] = list(zip(sheets_work['_match_key'], sheets_work['_occ']))

    # Mapa do sheets por _full_key para busca rápida e controle de chaves já casadas
    sheets_dict = {}
    sheets_matched_keys = set()
    for idx, row in sheets_work.iterrows():
        sheets_dict[row['_full_key']] = row

    reconciled_rows = []
    stats = {
        'mantidos': 0,
        'preenchidos': 0,
        'novos': 0,
        'sem_categoria': 0
    }

    # Itera sobre a FATURA (Verdade Absoluta): toda linha da fatura existirá na base final
    for idx, f_row in fatura_work.iterrows():
        full_key = f_row['_full_key']
        matched_sheets_row = sheets_dict.get(full_key)

        # Se a chave exata já foi usada por outra linha idêntica, anula
        if matched_sheets_row is not None and matched_sheets_row['_full_key'] in sheets_matched_keys:
            matched_sheets_row = None

        # Fallback de busca: mesmo valor e estabelecimento com proximidade de data (+- 2 dias)
        if matched_sheets_row is None and not sheets_work.empty:
            candidates = sheets_work[
                (sheets_work['_val_num'] == f_row['_val_num']) &
                (sheets_work['_estab_norm'] == f_row['_estab_norm']) &
                (~sheets_work['_full_key'].isin(sheets_matched_keys))
            ]
            if not candidates.empty:
                for _, cand in candidates.iterrows():
                    f_d = f_row['_date_obj']
                    c_d = cand['_date_obj']
                    if f_d and c_d:
                        if abs((f_d - c_d).days) <= 2:
                            matched_sheets_row = cand
                            break
                    else:
                        matched_sheets_row = cand
                        break

        if matched_sheets_row is not None:
            sheets_matched_keys.add(matched_sheets_row['_full_key'])
            user_cat = matched_sheets_row['categoria']
            user_cat_valid = user_cat is not None and not pd.isna(user_cat) and str(user_cat).strip() != ""

            fatura_cat = f_row['categoria']
            fatura_cat_valid = fatura_cat is not None and not pd.isna(fatura_cat) and str(fatura_cat).strip() != ""

            if user_cat_valid:
                final_cat = str(user_cat).strip()
                status = 'Mantido do Sheets'
                stats['mantidos'] += 1
            elif fatura_cat_valid:
                final_cat = str(fatura_cat).strip()
                status = 'Preenchido da Fatura'
                stats['preenchidos'] += 1
            else:
                final_cat = ""
                status = 'Sem Categoria'
                stats['sem_categoria'] += 1

            reconciled_rows.append({
                'categoria': final_cat,
                'Data': f_row['Data'],
                'Estabelecimento': f_row['Estabelecimento'],
                'Valor': f_row['_val_num'],
                '_status': status,
                '_date_obj': f_row['_date_obj']
            })
        else:
            # Lançamento exclusivo da fatura nova (não estava no Sheets)
            fatura_cat = f_row['categoria']
            fatura_cat_valid = fatura_cat is not None and not pd.isna(fatura_cat) and str(fatura_cat).strip() != ""
            final_cat = str(fatura_cat).strip() if fatura_cat_valid else ""
            status = 'Novo da Fatura'
            stats['novos'] += 1
            if not fatura_cat_valid:
                stats['sem_categoria'] += 1

            reconciled_rows.append({
                'categoria': final_cat,
                'Data': f_row['Data'],
                'Estabelecimento': f_row['Estabelecimento'],
                'Valor': f_row['_val_num'],
                '_status': status,
                '_date_obj': f_row['_date_obj']
            })

    # Identifica transações do Sheets que NÃO foram casadas na fatura (não efetivadas)
    descartados_rows = []
    if not sheets_work.empty:
        for idx, s_row in sheets_work.iterrows():
            if s_row['_full_key'] not in sheets_matched_keys:
                s_cat = s_row['categoria']
                cat_str = str(s_cat).strip() if s_cat is not None and not pd.isna(s_cat) else ""
                descartados_rows.append({
                    'categoria': cat_str,
                    'Data': s_row['Data'],
                    'Estabelecimento': s_row['Estabelecimento'],
                    'Valor': s_row['_val_num'],
                    '_motivo': 'Não encontrado na fatura oficial (não efetivado)'
                })

    df_descartados = pd.DataFrame(descartados_rows) if descartados_rows else pd.DataFrame(columns=empty_descartados_cols)

    df_result = pd.DataFrame(reconciled_rows) if reconciled_rows else pd.DataFrame(columns=empty_result_cols)

    # Ordenação por data (se disponível)
    if not df_result.empty and '_date_obj' in df_result.columns:
        df_result['_sort_date'] = df_result['_date_obj'].apply(lambda d: d.isoformat() if d else '9999-12-31')
        df_result = df_result.sort_values(by=['_sort_date', 'Estabelecimento']).reset_index(drop=True)
        df_result = df_result.drop(columns=['_sort_date', '_date_obj'], errors='ignore')

    valor_antigo = round(float(sheets_work['_val_num'].sum()), 2) if not sheets_work.empty and '_val_num' in sheets_work.columns else 0.0
    valor_fatura = round(float(fatura_work['_val_num'].sum()), 2) if not fatura_work.empty and '_val_num' in fatura_work.columns else 0.0
    valor_novo = round(float(df_result['Valor'].sum()), 2) if not df_result.empty and 'Valor' in df_result.columns else 0.0
    diff_valor = round(valor_novo - valor_antigo, 2)
    diff_fatura = round(valor_novo - valor_fatura, 2)
    bate_com_fatura = bool(abs(diff_fatura) < 0.01)

    valor_removido = round(float(df_descartados['Valor'].sum()), 2) if not df_descartados.empty and 'Valor' in df_descartados.columns else 0.0

    stats['total'] = len(df_result)
    stats['removidos'] = len(df_descartados)
    stats['valor_removido'] = valor_removido
    stats['df_descartados'] = df_descartados
    stats['valor_antigo'] = valor_antigo
    stats['valor_fatura'] = valor_fatura
    stats['valor_novo'] = valor_novo
    stats['diff_valor'] = diff_valor
    stats['diff_fatura'] = diff_fatura
    stats['bate_com_fatura'] = bate_com_fatura

    return df_result, stats


def to_sheets_tsv(df: pd.DataFrame, include_header: bool = False) -> str:
    """Exporta o DataFrame para string tabulada (TSV) pronta para copiar e colar no Google Sheets.
    Colunas: Categoria, Data, Estabelecimento, Valor (formatado com vírgula).
    """
    if df is None or df.empty:
        return ""

    out_df = pd.DataFrame()
    out_df['categoria'] = df['categoria'].fillna('').astype(str)
    out_df['Data'] = df['Data'].fillna('').astype(str)
    out_df['Estabelecimento'] = df['Estabelecimento'].fillna('').astype(str)

    # Formata valor com vírgula brasileira (ex: 54,14)
    out_df['Valor'] = df['Valor'].apply(lambda x: f"{x:.2f}".replace('.', ',') if isinstance(x, (int, float)) else str(x))

    tsv_data = out_df.to_csv(sep='\t', index=False, header=include_header, lineterminator='\n')
    return tsv_data
