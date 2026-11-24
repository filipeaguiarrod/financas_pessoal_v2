"""Testes unitários para o cliente de busca automática de faturas no backend."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src import credit_card, invoice_client, reconciler


def _mock_response(status_code: int = 200, json_data=None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


def test_fetch_latest_xp_invoice_integrates_with_credit_card_pipeline():
    xp_csv = (
        "Data;Estabelecimento;Portador;Valor;Parcela\n"
        "10/11/2026;SUPERMERCADO TESTE;TITULAR;R$ 120,50;-\n"
        "11/11/2026;Pagamentos Validos Normais;TITULAR;R$ -100,00;-\n"
    )
    resp = _mock_response(
        200,
        json_data={
            "bank": "xp",
            "source": "google_drive",
            "filename": "xp_2026_11.csv",
            "date": "2026-11-23T22:00:00Z",
            "csv_content": xp_csv,
        },
    )

    with patch("src.invoice_client.requests.get", return_value=resp) as mock_get:
        remote = invoice_client.fetch_latest_invoice("xp", api_url="http://backend.local:7555")

    mock_get.assert_called_once_with("http://backend.local:7555/invoices/xp/latest", timeout=30)
    assert remote.bank == "xp"
    assert remote.filename == "xp_2026_11.csv"

    invoice = credit_card.process_credit_card_invoice(remote.to_bytes_io())
    assert invoice.bank == "xp"
    assert invoice.total_amount == 120.50
    assert len(invoice.df) == 1


def test_fetch_latest_nubank_invoice_integrates_with_credit_card_pipeline():
    nu_csv = (
        "date,title,amount\n"
        "2026-11-15,Cafeteria Central,24.90\n"
        "2026-11-16,Pagamento recebido,-500.00\n"
    )
    resp = _mock_response(
        200,
        json_data={
            "bank": "nubank",
            "source": "gmail",
            "filename": "Nubank_2026-11-23.csv",
            "date": "2026-11-23T23:16:00+00:00",
            "csv_content": nu_csv,
        },
    )

    with patch("src.invoice_client.requests.get", return_value=resp):
        remote = invoice_client.fetch_latest_invoice("nubank", api_url="http://backend.local:7555")

    invoice = credit_card.process_credit_card_invoice(remote.to_bytes_io())
    assert invoice.bank == "nubank"
    assert invoice.total_amount == 24.90
    assert len(invoice.df) == 1


def test_fetch_latest_invoice_rejects_unsupported_bank():
    with pytest.raises(ValueError, match="não suportado"):
        invoice_client.fetch_latest_invoice("inter")


def test_fetch_latest_invoice_handles_connection_error():
    with patch(
        "src.invoice_client.requests.get",
        side_effect=requests.exceptions.ConnectionError("offline"),
    ):
        with pytest.raises(invoice_client.InvoiceClientError, match="Não foi possível conectar"):
            invoice_client.fetch_latest_invoice("xp", api_url="http://backend.local:7555")


def test_fetch_latest_invoice_propagates_backend_detail():
    resp = _mock_response(503, json_data={"detail": "XP_DRIVE_FOLDER_ID não configurado"})
    with patch("src.invoice_client.requests.get", return_value=resp):
        with pytest.raises(invoice_client.InvoiceClientError, match="XP_DRIVE_FOLDER_ID"):
            invoice_client.fetch_latest_invoice("xp", api_url="http://backend.local:7555")


def test_fetch_sheets_card_block_integrates_with_reconciler():
    resp = _mock_response(
        200,
        json_data={
            "bank": "xp",
            "mes": "novembro",
            "range": "G4:J98",
            "max_rows": 95,
            "rows": [
                ["Restaurante", "10/11/2026", "PADARIA CENTRAL", "32,50"],
            ],
        },
    )
    with patch("src.invoice_client.requests.get", return_value=resp) as mock_get:
        df_sheets, meta = invoice_client.fetch_sheets_card_block(
            "xp", "novembro", api_url="http://backend.local:7555"
        )

    mock_get.assert_called_once_with(
        "http://backend.local:7555/sheets/card-block",
        params={"bank": "xp", "mes": "novembro"},
        timeout=30,
    )
    assert meta["range"] == "G4:J98"
    assert len(df_sheets) == 1

    import pandas as pd
    df_fatura = pd.DataFrame([
        {"categoria": "Outros", "Data": "10/11/2026", "Estabelecimento": "PADARIA CENTRAL", "Valor": 32.50},
        {"categoria": "Mercado", "Data": "12/11/2026", "Estabelecimento": "SUPERMERCADO", "Valor": 110.00},
    ])
    df_rec, stats = reconciler.reconcile_transactions(df_sheets, df_fatura)
    assert stats["mantidos"] == 1
    assert stats["novos"] == 1
    assert df_rec.loc[df_rec["Estabelecimento"] == "PADARIA CENTRAL", "categoria"].iloc[0] == "Restaurante"


def test_write_sheets_card_block_formats_br_currency_and_posts():
    import pandas as pd

    df_rec = pd.DataFrame([
        {"categoria": "Restaurante", "Data": "10/11/2026", "Estabelecimento": "PADARIA", "Valor": 32.5},
    ])
    resp = _mock_response(
        200,
        json_data={
            "status": "success",
            "bank": "nubank",
            "mes": "novembro",
            "range": "G99:J200",
            "written_rows": 1,
        },
    )
    with patch("src.invoice_client.requests.post", return_value=resp) as mock_post:
        res = invoice_client.write_sheets_card_block(
            "nubank", "novembro", df_rec, api_url="http://backend.local:7555"
        )

    assert res["written_rows"] == 1
    mock_post.assert_called_once_with(
        "http://backend.local:7555/sheets/card-block",
        json={
            "bank": "nubank",
            "mes": "novembro",
            "rows": [["Restaurante", "10/11/2026", "PADARIA", "32,50"]],
        },
        timeout=30,
    )
