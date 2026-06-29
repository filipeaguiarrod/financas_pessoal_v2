import io
import pandas as pd
import pytest
from src.credit_card import parse_nubank_amount
from src.checking_account import transform_bradesco


def test_parse_nubank_amount():
    # Standard dot separator
    assert parse_nubank_amount("34.86") == 34.86
    assert parse_nubank_amount(34.86) == 34.86
    
    # Comma separator
    assert parse_nubank_amount("34,86") == 34.86
    
    # Currency symbols and spaces
    assert parse_nubank_amount("R$ 34,86") == 34.86
    assert parse_nubank_amount(" R$ 34.86 ") == 34.86
    
    # Thousands and decimal separators
    assert parse_nubank_amount("1.234,56") == 1234.56
    assert parse_nubank_amount("1,234.56") == 1234.56
    
    # Negative values
    assert parse_nubank_amount("-34.86") == -34.86
    assert parse_nubank_amount("-34,86") == -34.86
    
    # Invalid or empty values
    assert parse_nubank_amount(None) == 0.0
    assert parse_nubank_amount("") == 0.0
    assert parse_nubank_amount("invalid") == 0.0


def test_transform_bradesco_filters_rent_inv_facil():
    # CSV content simulating Bradesco statement:
    # date;history;docto;credito;debito
    csv_content = (
        "29/06/26;SALDO ANTERIOR;0;0,00;0,00\n"  # should be ignored as sujeira
        "29/06/26;RENT.INV.FACIL;123;0,00;100,00\n"  # should be ignored as RENT.INV.FACIL
        "29/06/26;RENTAB.INVEST FACILCRED;124;0,00;100,00\n"  # should be ignored as RENTAB.INVEST
        "29/06/26;COMPRA SUPERMERCADO;125;0,00;50,00\n"  # should be kept
        "29/06/26;PIX RECEBIDO;126;200,00;0,00\n"  # should be kept
    )
    
    file_mock = io.BytesIO(csv_content.encode('utf-8'))
    
    df = transform_bradesco(file_mock)
    
    # Verify shape and contents
    assert len(df) == 2
    
    # The two kept rows should be COMPRA SUPERMERCADO and PIX RECEBIDO
    descriptions = df['lançamento'].tolist()
    assert "COMPRA SUPERMERCADO" in descriptions
    assert "PIX RECEBIDO" in descriptions
    
    # Verify values
    values = df['valor (R$)'].tolist()
    assert "-50,00" in values
    assert "200,00" in values
