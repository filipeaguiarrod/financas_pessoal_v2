import datetime
import pandas as pd

from src.ecommerce_enrichment import (
    enrich_amazon_transactions,
    extract_installment_total,
    is_amazon_transaction,
)
from src.ecommerce_sync import parse_sheet_records


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


def test_parse_sheet_records_normalizes_br_values_and_dates():
    raw = [
        {
            "data": "16/11/2026",
            "origem": "Amazon",
            "pedido_id": "702-6626255-2875465",
            "descricao": "Bosch Jogo De Brocas Madeira Mini...",
            "valor": "33,82",
            "email_id": "1a1e69c4f9954764",
        },
        {
            "data": "15/11/2026",
            "origem": "Amazon",
            "pedido_id": "701-5000372-3110633",
            "descricao": "Grand Theft Auto VI - PlayStation 5",
            "valor": 449.9,
            "email_id": "1a1e188a3e7270d6",
        },
        {
            "data": "",
            "origem": "Amazon",
            "pedido_id": "",
            "descricao": "Linha inválida",
            "valor": "10,00",
            "email_id": "",
        },
    ]
    df = parse_sheet_records(raw)
    assert len(df) == 2
    assert df.loc[0, "data"] == datetime.date(2026, 11, 16)
    assert df.loc[0, "valor"] == 33.82
    assert df.loc[1, "valor"] == 449.90


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
