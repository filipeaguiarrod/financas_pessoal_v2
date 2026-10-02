import pytest
import pandas as pd
from datetime import date
from src.reconciler import (
    parse_amount,
    parse_date,
    normalize_establishment,
    parse_sheets_data,
    reconcile_transactions,
    to_sheets_tsv,
)


def test_parse_amount():
    assert parse_amount('54,14') == 54.14
    assert parse_amount('98,65') == 98.65
    assert parse_amount('26,0') == 26.0
    assert parse_amount('26,00') == 26.0
    assert parse_amount('R$ 1.234,56') == 1234.56
    assert parse_amount('1,234.56') == 1234.56
    assert parse_amount(45.5) == 45.5
    assert parse_amount(None) == 0.0
    assert parse_amount('') == 0.0


def test_parse_date_formats():
    d1, s1 = parse_date('01/09/2026')
    assert d1 == date(2026, 9, 1)
    assert s1 == '01/09/2026'

    d2, s2 = parse_date('16 ago.', default_year=2026)
    assert d2 == date(2026, 8, 16)
    assert s2 == '16/08/2026'

    d3, s3 = parse_date('18 set.', default_year=2026)
    assert d3 == date(2026, 9, 18)
    assert s3 == '18/09/2026'

    d4, s4 = parse_date('2026-09-20')
    assert d4 == date(2026, 9, 20)
    assert s4 == '20/09/2026'


def test_normalize_establishment():
    assert normalize_establishment('MP *SHELLBOX') == 'mpshellbox'
    assert normalize_establishment('MP*AKIRAPASTEL') == 'mpakirapastel'
    assert normalize_establishment('PET LOVE*OR10172856553') == 'petloveor10172856553'
    assert normalize_establishment('  ÁGUA & GÁS!!  ') == 'aguagas'


def test_parse_sheets_tsv():
    tsv = (
        "Restaurante\t01/09/2026\t99FOOD *SPOLETO - SHOPPIN\t54,14\n"
        "Combustível\t01/09/2026\tMP *SHELLBOX\t98,65\n"
        "\t18 set.\tIFD*TMC COMERCIO DE PI\t130,43\n"
    )
    df = parse_sheets_data(tsv, default_year=2026)
    assert len(df) == 3
    assert df.loc[0, 'categoria'] == 'Restaurante'
    assert df.loc[0, 'Valor'] == 54.14
    assert df.loc[1, 'categoria'] == 'Combustível'
    assert df.loc[2, 'categoria'] is None
    assert df.loc[2, 'Valor'] == 130.43
    assert df.loc[2, 'Estabelecimento'] == 'IFD*TMC COMERCIO DE PI'


def test_parse_sheets_vertical_stream():
    vertical_text = """
Combustível
01/09/2026
MP *SHELLBOX
98,65
Restaurante
01/09/2026
MP*AKIRAPASTEL
26,00
18 set.
IFD*TMC COMERCIO DE PI
130,43
"""
    df = parse_sheets_data(vertical_text, default_year=2026)
    assert len(df) == 3
    assert df.loc[0, 'categoria'] == 'Combustível'
    assert df.loc[0, 'Estabelecimento'] == 'MP *SHELLBOX'
    assert df.loc[1, 'categoria'] == 'Restaurante'
    assert df.loc[1, 'Valor'] == 26.0
    assert df.loc[2, 'categoria'] is None
    assert df.loc[2, 'Estabelecimento'] == 'IFD*TMC COMERCIO DE PI'
    assert df.loc[2, 'Valor'] == 130.43


def test_reconciliation_preserves_user_edits_and_fills_empty():
    # Base Validada do Sheets:
    # 1. MP*ALIEXPRESS com FERRAMENTAS editado pelo usuário
    # 2. IFD*TMC COMERCIO DE PI com categoria vazia
    df_sheets = pd.DataFrame([
        {'categoria': 'FERRAMENTAS', 'Data': '17 ago.', 'Estabelecimento': 'MP*ALIEXPRESS', 'Valor': 48.04},
        {'categoria': None, 'Data': '18 set.', 'Estabelecimento': 'IFD*TMC COMERCIO DE PI', 'Valor': 130.43},
    ])

    # Fatura Nova Classificada:
    # 1. MP*ALIEXPRESS veio como "Outros"
    # 2. IFD*TMC COMERCIO DE PI veio classificado como "RESTAURANTE"
    # 3. KZEN SUSHI é lançamento novo (não estava no Sheets)
    df_fatura = pd.DataFrame([
        {'categoria': 'Outros', 'Data': '17/08/2026', 'Estabelecimento': 'MP*ALIEXPRESS', 'Valor': 48.04},
        {'categoria': 'RESTAURANTE', 'Data': '18/09/2026', 'Estabelecimento': 'IFD*TMC COMERCIO DE PI', 'Valor': 130.43},
        {'categoria': 'RESTAURANTE', 'Data': '24/09/2026', 'Estabelecimento': 'KZEN SUSHI', 'Valor': 442.0},
    ])

    df_res, stats = reconcile_transactions(df_sheets, df_fatura, default_year=2026)

    assert stats['total'] == 3
    assert stats['mantidos'] == 1
    assert stats['preenchidos'] == 1
    assert stats['novos'] == 1

    # Verifica se FERRAMENTAS foi preservado (e NÃO sobrescrito por Outros)
    aliexpress = df_res[df_res['Estabelecimento'] == 'MP*ALIEXPRESS'].iloc[0]
    assert aliexpress['categoria'] == 'FERRAMENTAS'
    assert aliexpress['_status'] == 'Mantido do Sheets'

    # Verifica se IFD*TMC COMERCIO DE PI foi preenchido com RESTAURANTE
    ifood = df_res[df_res['Estabelecimento'] == 'IFD*TMC COMERCIO DE PI'].iloc[0]
    assert ifood['categoria'] == 'RESTAURANTE'
    assert ifood['_status'] == 'Preenchido da Fatura'

    # Verifica se KZEN SUSHI foi adicionado como novo lançamento
    kzen = df_res[df_res['Estabelecimento'] == 'KZEN SUSHI'].iloc[0]
    assert kzen['categoria'] == 'RESTAURANTE'
    assert kzen['_status'] == 'Novo da Fatura'


def test_reconciliation_handles_duplicates():
    # Duas compras idênticas no mesmo dia
    df_sheets = pd.DataFrame([
        {'categoria': 'ALIMENTAÇÃO', 'Data': '30/08/2026', 'Estabelecimento': 'CRISTAL', 'Valor': 16.0},
        {'categoria': None, 'Data': '30/08/2026', 'Estabelecimento': 'CRISTAL', 'Valor': 8.0},
    ])

    df_fatura = pd.DataFrame([
        {'categoria': 'ALIMENTAÇÃO', 'Data': '30/08/2026', 'Estabelecimento': 'CRISTAL', 'Valor': 16.0},
        {'categoria': 'ALIMENTAÇÃO', 'Data': '30/08/2026', 'Estabelecimento': 'CRISTAL', 'Valor': 8.0},
    ])

    df_res, stats = reconcile_transactions(df_sheets, df_fatura, default_year=2026)
    assert stats['total'] == 2
    assert stats['mantidos'] == 1
    assert stats['preenchidos'] == 1


def test_to_sheets_tsv():
    df = pd.DataFrame([
        {'categoria': 'Restaurante', 'Data': '01/09/2026', 'Estabelecimento': '99FOOD', 'Valor': 54.14},
    ])
    tsv = to_sheets_tsv(df)
    assert "Restaurante\t01/09/2026\t99FOOD\t54,14\n" in tsv
