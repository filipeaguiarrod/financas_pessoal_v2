import datetime
import pandas as pd

from src.ecommerce_enrichment import (
    enrich_amazon_transactions,
    extract_installment_total,
    is_amazon_transaction,
    style_enriched,
)


def _fake_classifier(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    cats = []
    sources = []
    for estab in out["Estabelecimento"]:
        low = str(estab).lower()
        if "brocas" in low:
            cats.append("Casa / Ferramentas")
            sources.append("modelo")
        elif "grand theft auto" in low:
            cats.append("Lazer / Games")
            sources.append("modelo")
        else:
            cats.append("Outros")
            sources.append("modelo")
    out["categoria"] = cats
    out["_source"] = sources
    return out


def test_custom_store_patterns_match():
    assert is_amazon_transaction("AMZN DIGITAL", store_patterns="AMAZON,AMZN")
    assert not is_amazon_transaction("MAGALU", store_patterns="AMAZON,AMZN")
    assert is_amazon_transaction("MAGALU", store_patterns="AMAZON,MAGALU")


def test_amazon_detection_and_installment_extraction():
    assert is_amazon_transaction("AMAZON BR")
    assert is_amazon_transaction("AMZN MKTP BR")
    assert is_amazon_transaction("AMAZON.COM.BR - Parcela 1/3")
    assert not is_amazon_transaction("IFD*SPOLETO")
    assert not is_amazon_transaction("SHOPEE *LOJA")

    assert extract_installment_total("AMAZON BR - Parcela 1/3") == 3
    assert extract_installment_total("AMAZON BR 2/5") == 5
    assert extract_installment_total("AMAZON BR") is None


def test_enrich_amazon_transactions_direct_installment_ambiguous_and_no_match():
    orders_df = pd.DataFrame([
        {
            "data": datetime.date(2026, 11, 15),
            "origem": "Amazon",
            "pedido_id": "702-6626255-2875465",
            "descricao": "Bosch Jogo De Brocas Madeira Mini",
            "valor": 33.82,
        },
        {
            "data": datetime.date(2026, 11, 15),
            "origem": "Amazon",
            "pedido_id": "701-5000372-3110633",
            "descricao": "Grand Theft Auto VI - PlayStation 5",
            "valor": 449.90,
        },
        {
            "data": datetime.date(2026, 10, 18),
            "origem": "Amazon",
            "pedido_id": "701-3112898-5369846",
            "descricao": "Nescafe Dolce Gusto, Espresso",
            "valor": 17.90,
        },
        {
            "data": datetime.date(2026, 10, 18),
            "origem": "Amazon",
            "pedido_id": "701-3112898-5369846",
            "descricao": "Dolce Gusto Nescafe Lungo",
            "valor": 17.90,
        },
    ])

    invoice_df = pd.DataFrame([
        {"categoria": "Compras", "_source": "modelo", "Data": "2026-11-17", "Estabelecimento": "AMAZON BR", "Valor": 33.82},
        {"categoria": "Compras", "_source": "modelo", "Data": "2026-11-16", "Estabelecimento": "AMAZON BR - Parcela 1/3", "Valor": 149.97},
        {"categoria": "Compras", "_source": "modelo", "Data": "2026-10-19", "Estabelecimento": "AMAZON.COM.BR", "Valor": 17.90},
        {"categoria": "Compras", "_source": "modelo", "Data": "2026-11-10", "Estabelecimento": "AMAZON BR", "Valor": 99.99},
        {"categoria": "Restaurante", "_source": "rules", "Data": "2026-11-10", "Estabelecimento": "IFD*SPOLETO", "Valor": 54.00},
    ])

    enriched, ambig = enrich_amazon_transactions(
        invoice_df,
        orders_df,
        classify_fn=_fake_classifier,
    )

    assert enriched.loc[0, "match_status"] == "matched"
    assert "Bosch Jogo De Brocas Madeira Mini" in enriched.loc[0, "Estabelecimento"]
    assert enriched.loc[0, "categoria"] == "Casa / Ferramentas"

    assert enriched.loc[1, "match_status"] == "matched"
    assert "Grand Theft Auto VI - PlayStation 5" in enriched.loc[1, "Estabelecimento"]
    assert enriched.loc[1, "categoria"] == "Lazer / Games"

    assert enriched.loc[2, "match_status"] == "ambiguo"
    assert 2 in ambig and len(ambig[2]) == 2

    assert enriched.loc[3, "match_status"] == "sem_match"
    assert enriched.loc[4, "match_status"] == "nao_amazon"
    assert enriched.loc[4, "categoria"] == "Restaurante"


def test_style_enriched_hides_internal_columns_and_applies_colors():
    df = pd.DataFrame([
        {
            "categoria": "Casa / Ferramentas",
            "_source": "modelo",
            "match_status": "matched",
            "Data": "2026-11-17",
            "Estabelecimento": "AMAZON BR — Broca",
            "Valor": "33,82",
        },
        {
            "categoria": "Compras",
            "_source": "historico",
            "match_status": "sem_match",
            "Data": "2026-11-10",
            "Estabelecimento": "AMAZON BR",
            "Valor": "99,99",
        },
    ])
    styler = style_enriched(df)
    assert list(styler.data.columns) == ["categoria", "Data", "Estabelecimento", "Valor"]
    html = styler.to_html()
    assert "#2E7D32" in html
    assert "#C62828" in html
    assert "#1565C0" in html


def test_raw_df_installments_implicit_divisor_refund_and_combo():
    orders_df = pd.DataFrame([
        {
            "data": datetime.date(2026, 11, 9),
            "origem": "Amazon",
            "pedido_id": "701-4252700-0123455",
            "descricao": "G-Tech BSP11, Aparelho de Pressão",
            "valor": 84.98,
        },
        {
            "data": datetime.date(2026, 10, 15),
            "origem": "Amazon",
            "pedido_id": "701-5000372-3110633",
            "descricao": "Grand Theft Auto VI - PlayStation 5",
            "valor": 449.90,
        },
        {
            "data": datetime.date(2026, 10, 29),
            "origem": "Amazon",
            "pedido_id": "701-0786509-5249835",
            "descricao": "Petisco Dreamies",
            "valor": 19.85,
        },
        {
            "data": datetime.date(2026, 10, 18),
            "origem": "Amazon",
            "pedido_id": "702-0395393-7509050",
            "descricao": "Head & Shoulders",
            "valor": 17.64,
        },
        {
            "data": datetime.date(2026, 10, 18),
            "origem": "Amazon",
            "pedido_id": "701-3112898-5369846",
            "descricao": "Nescafe Dolce Gusto",
            "valor": 17.90,
        },
    ])

    invoice_df = pd.DataFrame([
        {"categoria": None, "_source": None, "Data": "2026-11-09", "Estabelecimento": "Amazon", "Valor": 42.49},
        {"categoria": None, "_source": None, "Data": "2026-11-15", "Estabelecimento": "Amazon", "Valor": 149.97},
        {"categoria": None, "_source": None, "Data": "2026-11-01", "Estabelecimento": "Amazon Credito - NuPay", "Valor": -19.85},
        {"categoria": None, "_source": None, "Data": "2026-10-20", "Estabelecimento": "Amazon Credito - NuPay", "Valor": 35.54},
    ])

    raw_df = pd.DataFrame([
        {"title": "Amazon - Parcela 1/2", "Parcela": ""},
        {"title": "Amazon", "Parcela": "2 de 3"},
        {"title": "Amazon Credito - NuPay", "Parcela": ""},
        {"title": "Amazon Credito - NuPay", "Parcela": ""},
    ])

    enriched, _ = enrich_amazon_transactions(
        invoice_df,
        orders_df,
        raw_df=raw_df,
        classify_fn=_fake_classifier,
    )

    assert enriched.loc[0, "match_status"] == "matched"
    assert "G-Tech BSP11" in enriched.loc[0, "Estabelecimento"]

    assert enriched.loc[1, "match_status"] == "matched"
    assert "Grand Theft Auto VI" in enriched.loc[1, "Estabelecimento"]

    assert enriched.loc[2, "match_status"] == "matched"
    assert "[Estorno] Petisco Dreamies" in enriched.loc[2, "Estabelecimento"]

    assert enriched.loc[3, "match_status"] == "matched"
    assert "Head & Shoulders + Nescafe Dolce Gusto" in enriched.loc[3, "Estabelecimento"]

    # Mesmo sem raw_df, o divisor implícito 84.98 / 2 casa 42.49
    enriched_no_raw, _ = enrich_amazon_transactions(
        invoice_df.iloc[[0]],
        orders_df,
        classify_fn=_fake_classifier,
    )
    assert enriched_no_raw.loc[0, "match_status"] == "matched"
    assert "G-Tech BSP11" in enriched_no_raw.loc[0, "Estabelecimento"]
