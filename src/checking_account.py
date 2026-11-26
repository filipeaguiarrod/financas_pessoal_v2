import logging
import re
import unicodedata
import pandas as pd
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


def _ascii_upper(s: str) -> str:
    # Remove non-ASCII chars before comparing — handles encoding variants
    # e.g. DISPONÍVEL and DISPONÃVEL both become DISPONVEL
    return ''.join(c for c in str(s) if c.isascii()).upper().strip()


_ITAU_SUJEIRAS = {
    _ascii_upper(s) for s in [
        'SALDO ANTERIOR', 'REND PAGO APLIC AUT MAIS',
        'SDO CTA/APL AUTOMATICAS', 'SALDO DO DIA',
        'SALDO TOTAL DISPONÍVEL DIA', 'REND PAGO APLIC AUT APR',
    ]
}


def _is_itau_sujeira(text: str) -> bool:
    x_upper = _ascii_upper(text)
    if x_upper in _ITAU_SUJEIRAS:
        return True
    if any(s in x_upper for s in ('REND PAGO APLIC AUT MAIS', 'REND PAGO APLIC AUT APR')):
        return True
    if 'PAG BOLETO BANCO XP' in x_upper:
        return True
    if 'PIX QRS NU PAGAMENT' in x_upper:
        return True
    return False


def _is_pdf_file(file_obj) -> bool:
    """Detecta se o arquivo é PDF pelo nome ou pelos magic bytes (%PDF)."""
    name = str(getattr(file_obj, "name", "") or "").lower()
    if name.endswith(".pdf"):
        return True
    if isinstance(file_obj, str):
        return file_obj.lower().endswith(".pdf")
    if hasattr(file_obj, "read") and hasattr(file_obj, "seek"):
        pos = file_obj.tell() if hasattr(file_obj, "tell") else 0
        file_obj.seek(0)
        head = file_obj.read(5)
        file_obj.seek(pos)
        if isinstance(head, bytes):
            return head.startswith(b"%PDF")
        if isinstance(head, str):
            return head.startswith("%PDF")
    return False


def _parse_br_amount(val_str: str) -> float | None:
    cleaned = str(val_str or "").replace("R$", "").replace("\xa0", "").strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_heading(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def transform_itau_pdf(pdf_file) -> pd.DataFrame:
    """Lê o PDF de extrato conta corrente do Itaú (exportado do app) e extrai apenas lançamentos efetivados.

    Ignora cabeçalho de saldos/limites, 'Lançamentos futuros', linhas de saldo diário e 'Posição consolidada'.
    Concatena tipo + descrição como '<Lançamentos> - <Descrição>' (ex.: 'PIX ENVIADO - NOME').
    """
    import pdfplumber

    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)

    date_re = re.compile(r"^\d{2}/\d{2}/\d{4}$")

    # Limites horizontais padrão (atualizados dinamicamente pelo cabeçalho da tabela no PDF)
    col_bounds = {
        "lanc": 95.0,
        "desc": 250.0,
        "valor": 405.0,
        "saldo": 490.0,
    }

    in_lancamentos = False
    stop_parsing = False
    parsed_rows: list[dict[str, str | float]] = []
    current_tx: dict[str, str] | None = None

    def _flush_current():
        nonlocal current_tx
        if current_tx is None:
            return
        tipo = " ".join(current_tx["tipo"].split()).strip()
        desc = " ".join(current_tx["desc"].split()).strip()
        val_num = _parse_br_amount(current_tx["valor"])
        if val_num is not None:
            if tipo and desc:
                lancamento = f"{tipo} - {desc}"
            else:
                lancamento = desc or tipo
            if lancamento and not _is_itau_sujeira(desc) and not _is_itau_sujeira(lancamento):
                parsed_rows.append({
                    "data": current_tx["data"],
                    "lançamento": lancamento,
                    "ag./origem": "ITAU",
                    "valor (R$)": f"{val_num:.2f}".replace(".", ","),
                })
        current_tx = None

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            if stop_parsing:
                break

            words = page.extract_words(keep_blank_chars=False, use_text_flow=False) or []
            lines_by_y: dict[float, list[dict]] = {}
            for w in words:
                y = round(float(w["top"]), 1)
                matched_y = next((ky for ky in lines_by_y if abs(ky - y) <= 2.5), None)
                if matched_y is None:
                    lines_by_y[y] = []
                    matched_y = y
                lines_by_y[matched_y].append(w)

            for y in sorted(lines_by_y):
                row_words = sorted(lines_by_y[y], key=lambda item: float(item["x0"]))
                full_line_text = " ".join(w["text"] for w in row_words).strip()
                norm_line = _normalize_heading(full_line_text)

                # Marcadores de fim da seção de lançamentos
                if norm_line.startswith("posicao consolidada") or norm_line == "limites" or norm_line == "aviso":
                    _flush_current()
                    stop_parsing = True
                    break

                # Início da seção 'Lançamentos' (ignorando 'Lançamentos futuros')
                if norm_line == "lancamentos":
                    in_lancamentos = True
                    continue

                if not in_lancamentos:
                    continue

                # Cabeçalho da tabela (pode repetir em cada página)
                if norm_line.startswith("data lancamentos descricao"):
                    _flush_current()
                    for w in row_words:
                        wt = _normalize_heading(w["text"])
                        x0 = float(w["x0"])
                        if wt == "lancamentos":
                            col_bounds["lanc"] = x0 - 5.0
                        elif wt == "descricao":
                            col_bounds["desc"] = x0 - 5.0
                        elif wt == "valor":
                            col_bounds["valor"] = x0 - 15.0
                        elif wt == "saldo":
                            col_bounds["saldo"] = x0 - 15.0
                    continue

                # Separa palavras por coluna
                date_parts: list[str] = []
                tipo_parts: list[str] = []
                desc_parts: list[str] = []
                valor_parts: list[str] = []
                saldo_parts: list[str] = []

                for w in row_words:
                    x0 = float(w["x0"])
                    txt = w["text"]
                    if x0 < col_bounds["lanc"]:
                        date_parts.append(txt)
                    elif x0 < col_bounds["desc"]:
                        tipo_parts.append(txt)
                    elif x0 < col_bounds["valor"]:
                        desc_parts.append(txt)
                    elif x0 < col_bounds["saldo"]:
                        valor_parts.append(txt)
                    else:
                        saldo_parts.append(txt)

                date_str = " ".join(date_parts).strip()
                tipo_str = " ".join(tipo_parts).strip()
                desc_str = " ".join(desc_parts).strip()
                valor_str = " ".join(valor_parts).strip()
                saldo_str = " ".join(saldo_parts).strip()

                if date_re.match(date_str):
                    _flush_current()
                    # Linha de saldo diário: tem data e saldo, mas não tem valor na coluna Valor (R$)
                    if not valor_str and saldo_str:
                        continue
                    if not valor_str and not tipo_str and not desc_str:
                        continue
                    current_tx = {
                        "data": date_str,
                        "tipo": tipo_str,
                        "desc": desc_str,
                        "valor": valor_str,
                    }
                elif current_tx is not None:
                    # Linha de continuação de 'Lançamentos' e/ou 'Descrição'
                    if tipo_str:
                        current_tx["tipo"] = f"{current_tx['tipo']} {tipo_str}".strip()
                    if desc_str:
                        current_tx["desc"] = f"{current_tx['desc']} {desc_str}".strip()
                    if valor_str and not current_tx["valor"]:
                        current_tx["valor"] = valor_str

    _flush_current()

    if not parsed_rows:
        return pd.DataFrame(columns=['data', 'lançamento', 'ag./origem', 'valor (R$)'])

    # O PDF do Itaú vem do mais recente para o mais antigo; inverter preserva a ordem cronológica crescente
    parsed_rows.reverse()
    return pd.DataFrame(parsed_rows, columns=['data', 'lançamento', 'ag./origem', 'valor (R$)'])


def _transform_itau_excel(itau_file) -> pd.DataFrame:
    """Lê o XLS legado do Itaú e retorna DataFrame com lançamentos limpos."""
    itau_file.seek(0)
    itau = pd.read_excel(itau_file)

    try:
        inicio = itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0] + 1
        fim = itau.loc[itau['Logotipo Itaú'] == 'lançamentos futuros'].index[0]
        itau = itau.iloc[inicio:fim, 0:4]
    except Exception:
        inicio = itau.loc[itau['Logotipo Itaú'] == 'lançamentos'].index[0] + 1
        itau = itau.iloc[inicio:, 0:4]

    itau.columns = ['data', 'lançamento', 'ag./origem', 'valor (R$)']
    itau = itau.loc[~itau['lançamento'].apply(_is_itau_sujeira)]
    itau['valor (R$)'] = itau['valor (R$)'].astype('str').str.replace('.', ',')
    itau['ag./origem'] = 'ITAU'

    return itau


def transform_itau(itau_file) -> pd.DataFrame:
    """Lê o extrato do Itaú (.pdf ou .xls) e retorna DataFrame com lançamentos limpos.

    Saída:
        data        (str) data do lançamento
        lançamento  (str) descrição
        ag./origem  (str) 'ITAU'
        valor (R$)  (str) valor formatado com vírgula
    """
    if _is_pdf_file(itau_file):
        return transform_itau_pdf(itau_file)
    return _transform_itau_excel(itau_file)


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
        'SALDO INVEST FACIL', 'ÚLTIMOS LANÇAMENTOS', 'ULTIMOS LANCAMENTOS',
        'RENT.INV.FACIL', 'RENTAB.INVEST'
    }

    match_count = 0
    for line_idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        norm_line = _normalize_heading(line)
        if norm_line.startswith("lancamentos periodicos") or norm_line.startswith("os dados acima tem como base"):
            break

        parts = [p.strip() for p in line.split(';')]
        if len(parts) < 2:
            continue

        date_str = parts[0]

        # Verifica se começa com uma data válida
        if date_pattern.match(date_str):
            history = parts[1]

            # Verifica se é lixo ou transações indesejadas
            upper_history = ''.join(c for c in history if c.isascii()).upper().strip()
            if any(s in upper_history for s in sujeiras):
                continue
            if 'RENTAB.INVEST FACILCRED' in upper_history:
                continue
            if 'PAG BOLETO BANCO XP' in upper_history:
                continue
            if 'PIX QRS NU PAGAMENT' in upper_history:
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
            if 'RENTAB.INVEST FACILCRED' in upper_desc:
                continue
            if 'PAG BOLETO BANCO XP' in upper_desc:
                continue
            if 'PIX QRS NU PAGAMENT' in upper_desc:
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


def consolidate_checking_accounts(itau_df: pd.DataFrame, bradesco_df: pd.DataFrame) -> pd.DataFrame:
    """Consolida os extratos do Itaú e do Bradesco aplicando regras de filtragem de sujeira.

    Regras aplicadas:
    1. Ignora transações do Bradesco contendo 'Rentab.invest Facilcred*'
    2. Ignora pagamentos de fatura do cartão de crédito (XP e Nubank)
    3. Ignora transferências internas entre Itaú e Bradesco na mesma data com mesmo valor e sinais opostos.
    """
    # 1. Copiar os DataFrames
    itau = itau_df.copy()
    bradesco = bradesco_df.copy()

    # 2. Concatenar
    merged = pd.concat([itau, bradesco], ignore_index=True)
    if merged.empty:
        return merged

    # 3. Colunas auxiliares para filtragem
    merged['_date_obj'] = pd.to_datetime(merged['data'], format='%d/%m/%Y', errors='coerce').dt.date

    def _to_float(val):
        if pd.isna(val):
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        val_str = str(val).strip()
        if ',' in val_str:
            val_str = val_str.replace('.', '').replace(',', '.')
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    merged['_value_float'] = merged['valor (R$)'].apply(_to_float)

    def _normalize_desc(s):
        if pd.isna(s):
            return ""
        s_norm = ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')
        return s_norm.upper().strip()

    merged['_desc_norm'] = merged['lançamento'].apply(_normalize_desc)

    indices_to_drop = set()

    # --- Regra 1 e 2: Filtros de descrição (Rentab.invest, XP, Nubank) ---
    for idx, row in merged.iterrows():
        desc = row['_desc_norm']
        origin = row['ag./origem']

        # Bradesco Rentab.invest Facilcred*
        if origin == 'BRAD' and 'RENTAB.INVEST FACILCRED' in desc:
            indices_to_drop.add(idx)
            continue

        # Pagamento XP
        if 'PAG BOLETO BANCO XP S.A' in desc or 'PAG BOLETO BANCO XP' in desc:
            indices_to_drop.add(idx)
            continue

        # Pagamento Nubank
        if 'PIX QRS NU PAGAMENT' in desc:
            indices_to_drop.add(idx)
            continue

    # --- Regra 3: Transferências internas entre Itaú e Bradesco ---
    grouped = merged.groupby('_date_obj')
    for date_val, group in grouped:
        # Apenas as transações da data atual que ainda não foram marcadas para remoção
        active_group = group[~group.index.isin(indices_to_drop)]
        
        itau_rows = active_group[active_group['ag./origem'] == 'ITAU'].copy()
        bradesco_rows = active_group[active_group['ag./origem'] == 'BRAD'].copy()
        
        used_bradesco_indices = set()
        
        for i_idx, i_row in itau_rows.iterrows():
            i_val = i_row['_value_float']
            if round(i_val, 2) == 0.0:
                continue
            
            # Procurar uma transação do Bradesco com valor oposto
            for b_idx, b_row in bradesco_rows.iterrows():
                if b_idx in used_bradesco_indices:
                    continue
                b_val = b_row['_value_float']
                
                # Se forem opostas (mesmo valor absoluto e sinal contrário)
                if round(i_val + b_val, 2) == 0.0:
                    indices_to_drop.add(i_idx)
                    indices_to_drop.add(b_idx)
                    used_bradesco_indices.add(b_idx)
                    break

    # 4. Remover as linhas indesejadas
    merged_clean = merged.drop(index=indices_to_drop)

    # 5. Ordenar por data (da mais antiga para a mais recente)
    merged_clean = merged_clean.sort_values(by='_date_obj', ascending=True)

    # 6. Remover colunas auxiliares
    merged_clean = merged_clean.drop(columns=['_date_obj', '_value_float', '_desc_norm'])

    return merged_clean


