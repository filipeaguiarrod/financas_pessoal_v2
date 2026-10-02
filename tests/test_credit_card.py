from pathlib import Path
import pandas as pd
import pytest
from src import credit_card

INPUTS_DIR = Path(__file__).parent.parent / "data" / "ground_truth" / "parcelas" / "inputs"


def test_detect_bank_nubank():
    df = pd.DataFrame(columns=['date', 'title', 'amount'])
    assert credit_card.detect_bank(df) == 'nubank'

    df_cat = pd.DataFrame(columns=['date', 'category', 'title', 'amount'])
    assert credit_card.detect_bank(df_cat) == 'nubank'


def test_detect_bank_xp():
    df = pd.DataFrame(columns=['Data', 'Estabelecimento', 'Valor'])
    assert credit_card.detect_bank(df) == 'xp'

    df_full = pd.DataFrame(columns=['Data', 'Estabelecimento', 'Portador', 'Valor', 'Parcela'])
    assert credit_card.detect_bank(df_full) == 'xp'


def test_detect_bank_unknown():
    df = pd.DataFrame(columns=['col1', 'col2', 'col3'])
    with pytest.raises(ValueError, match="Schema de fatura não reconhecido"):
        credit_card.detect_bank(df)


def test_parse_xp_amount():
    assert credit_card.parse_xp_amount("R$ 284,76") == 284.76
    assert credit_card.parse_xp_amount("284,76") == 284.76
    assert credit_card.parse_xp_amount("1.284,76") == 1284.76
    assert credit_card.parse_xp_amount("-R$ 50,00") == -50.00
    assert credit_card.parse_xp_amount(100.5) == 100.5
    assert credit_card.parse_xp_amount("") == 0.0
    assert credit_card.parse_xp_amount(None) == 0.0


def test_process_credit_card_invoice_nubank():
    nu_file = INPUTS_DIR / "nu-fatura-2026-05-02.csv"
    assert nu_file.exists()

    result = credit_card.process_credit_card_invoice(nu_file)
    assert result.bank == 'nubank'
    assert result.bank_name == 'Nubank'
    assert result.has_installments is True
    assert list(result.df.columns) == ['Data', 'Estabelecimento', 'Valor']
    assert len(result.df) > 0
    assert result.total_amount > 0
    assert isinstance(result.total_amount, float)
    # Check that 'Pagamento recebido' is filtered out if it existed
    assert not (result.df['Estabelecimento'] == 'Pagamento recebido').any()


def test_process_credit_card_invoice_xp():
    xp_file = INPUTS_DIR / "xp-fatura-2026-05-05.csv"
    assert xp_file.exists()

    result = credit_card.process_credit_card_invoice(xp_file)
    assert result.bank == 'xp'
    assert result.bank_name == 'XP Investimentos'
    assert result.has_installments is True
    assert list(result.df.columns) == ['Data', 'Estabelecimento', 'Valor']
    assert len(result.df) > 0
    assert result.total_amount > 0
    assert isinstance(result.total_amount, float)
    # Check that 'Pagamentos Validos Normais' is filtered out
    assert not (result.df['Estabelecimento'] == 'Pagamentos Validos Normais').any()


def test_format_display_df():
    df = pd.DataFrame({
        'Data': ['01/01/2026'],
        'Estabelecimento': ['Loja X'],
        'Valor': [1234.56]
    })
    disp = credit_card.format_display_df(df)
    assert disp['Valor'].iloc[0] == '1234,56'
