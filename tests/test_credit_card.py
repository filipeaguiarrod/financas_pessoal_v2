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


def test_process_credit_card_invoice_nubank_with_refunds():
    import io
    csv_data = (
        'date,title,amount\n'
        '2026-09-24,Ifd*Farma Popular,"61,88"\n'
        '2026-09-22,Amazon Credito - NuPay,"122,97"\n'
        '2026-09-22,Amazonmktplc*Megaecomm,"74,99"\n'
        '2026-09-22,Amazon Credito AMZ - NuPay,"35,80"\n'
        '2026-09-21,Google Youtube,"26,90"\n'
        '2026-09-21,Mercado Oba Oba Ltda M,"6,72"\n'
        '2026-09-20,Amazon Credito AMZ - NuPay,"- 36,51"\n'
        '2026-09-20,Amazon Credito AMZ - NuPay,"107,27"\n'
        '2026-09-17,Vivo Lite*Vivo Easy,"38,00"\n'
        '2026-09-13,Amazon Credito AMZ - NuPay,"36,51"\n'
        '2026-09-13,Uber - NuPay,"19,90"\n'
        '2026-09-13,Google Medium,"16,99"\n'
        '2026-09-12,Mlp *Kabum-Kabum - Parcela 1/8,"26,25"\n'
        '2026-09-11,Amazon - Parcela 1/12,"33,38"\n'
        '2026-09-10,Mp *Aliexpress - Parcela 1/4,"38,10"\n'
        '2026-09-10,Amazon Credito AMZ - NuPay,"29,99"\n'
        '2026-09-10,Mlp *Kabum-Kabum - Parcela 1/10,"60,01"\n'
        '2026-09-09,Ebn *Playstation,"19,99"\n'
        '2026-09-08,Mlp *Kabum-Kabum,"4.097,06"\n'
        '2026-09-08,Amazon BR III - NuPay,"- 157,04"\n'
        '2026-09-08,Amazon BR III - NuPay,"157,04"\n'
        '2026-09-02,Smart Fit Parque Migue,"129,90"\n'
        '2026-09-02,Amazon BR III - NuPay,"98,63"\n'
        '2026-08-31,Pagamento recebido,"- 1.704,28"\n'
        '2026-08-31,Google One,"48,49"\n'
        '2026-08-29,Dl*Uberrides,"11,06"\n'
        '2026-08-29,Dl*Uberrides,"8,80"\n'
        '2026-08-29,NuTag*AYA7I00,"31,00"\n'
        '2026-08-29,Dl*Uberrides,"10,00"\n'
        '2026-08-26,Amazon - Parcela 3/5,"33,99"\n'
        '2026-08-26,Amazon Marketplace - Parcela 2/2,"44,36"\n'
        '2026-08-26,Amazon - Parcela 5/6,"51,31"\n'
    )
    df = pd.read_csv(io.StringIO(csv_data))
    result = credit_card.process_credit_card_invoice(df)

    assert result.bank == 'nubank'
    assert result.total_amount == 5283.74

    # Verify refunds are present with negative values
    refunds = result.df[result.df['Valor'] < 0]
    assert len(refunds) == 2
    assert -36.51 in refunds['Valor'].values
    assert -157.04 in refunds['Valor'].values
    # Check that previous invoice payment was filtered out
    assert not (result.df['Estabelecimento'] == 'Pagamento recebido').any()

