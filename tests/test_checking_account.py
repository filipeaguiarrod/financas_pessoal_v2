"""Testes unitários para parsing de extratos de conta corrente (Itaú PDF e Bradesco CSV) e consolidação."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from src import checking_account


def _make_word(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + len(text) * 5.0, "top": top}


def _mock_pdf_with_pages(pages_words: list[list[dict]]):
    mock_pdf = MagicMock()
    mock_pages = []
    for words in pages_words:
        page = MagicMock()
        page.extract_words.return_value = words
        mock_pages.append(page)
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False
    return mock_pdf


def test_transform_itau_pdf_extracts_only_lancamentos_and_filters_balances_and_future():
    page1_words = [
        # Cabeçalho + lançamentos futuros (devem ser ignorados)
        _make_word("Extrato", 39.7, 285.0),
        _make_word("Lançamentos", 39.7, 369.0),
        _make_word("futuros", 158.0, 369.0),
        _make_word("06/12/2026", 39.7, 467.0),
        _make_word("PIX", 99.9, 467.0),
        _make_word("AGENDADO", 118.0, 467.0),
        _make_word("FUTURO", 256.2, 467.0),
        _make_word("-50,00", 434.0, 467.0),
        # Início da seção Lançamentos
        _make_word("Lançamentos", 39.7, 516.0),
        _make_word("Data", 39.7, 558.0),
        _make_word("Lançamentos", 99.9, 558.0),
        _make_word("Descrição", 256.2, 558.0),
        _make_word("Valor", 416.3, 558.0),
        _make_word("(R$)", 445.5, 558.0),
        _make_word("Saldo", 500.1, 558.0),
        _make_word("(R$)", 530.7, 558.0),
        # Transação 1 com descrição em 2 linhas
        _make_word("26/11/2026", 39.7, 586.0),
        _make_word("PIX", 99.9, 586.0),
        _make_word("ENVIADO", 118.0, 586.0),
        _make_word("LOJA", 256.2, 586.0),
        _make_word("EXEMPLO", 290.0, 586.0),
        _make_word("-150,00", 430.0, 586.0),
        _make_word("LTDA", 256.2, 603.0),
        # Linha de saldo diário (deve ser ignorada)
        _make_word("25/11/2026", 39.7, 654.0),
        _make_word("1.497,28", 512.0, 654.0),
        # Transação 2 (crédito)
        _make_word("25/11/2026", 39.7, 679.0),
        _make_word("PIX", 99.9, 679.0),
        _make_word("RECEBIDO", 118.0, 679.0),
        _make_word("CLIENTE", 256.2, 679.0),
        _make_word("20,00", 439.0, 679.0),
        # Rendimento automático (sujeira -> ignorado)
        _make_word("17/11/2026", 39.7, 756.0),
        _make_word("RENDIMENTOS", 99.9, 756.0),
        _make_word("REND", 256.2, 756.0),
        _make_word("PAGO", 286.0, 756.0),
        _make_word("APLIC", 317.0, 756.0),
        _make_word("AUT", 349.0, 756.0),
        _make_word("0,01", 447.0, 756.0),
        _make_word("MAIS", 256.2, 772.0),
    ]

    page2_words = [
        # Posição consolidada (deve parar imediatamente)
        _make_word("Posição", 39.7, 40.0),
        _make_word("consolidada", 90.0, 40.0),
        _make_word("15/11/2026", 39.7, 80.0),
        _make_word("NAO", 99.9, 80.0),
        _make_word("DEVE", 256.2, 80.0),
        _make_word("-999,00", 430.0, 80.0),
    ]

    fake_buf = io.BytesIO(b"%PDF-1.4 fake")
    fake_buf.name = "shareFile.pdf"

    with patch("pdfplumber.open", return_value=_mock_pdf_with_pages([page1_words, page2_words])):
        df = checking_account.transform_itau(fake_buf)

    assert list(df.columns) == ["data", "lançamento", "ag./origem", "valor (R$)"]
    assert len(df) == 2
    # Ordem cronológica crescente (25/11 antes de 26/11)
    assert df.iloc[0]["data"] == "25/11/2026"
    assert df.iloc[0]["lançamento"] == "PIX RECEBIDO - CLIENTE"
    assert df.iloc[0]["ag./origem"] == "ITAU"
    assert df.iloc[0]["valor (R$)"] == "20,00"

    assert df.iloc[1]["data"] == "26/11/2026"
    assert df.iloc[1]["lançamento"] == "PIX ENVIADO - LOJA EXEMPLO LTDA"
    assert df.iloc[1]["valor (R$)"] == "-150,00"


def test_transform_bradesco_stops_before_lancamentos_periodicos():
    csv_text = (
        "Extrato de: Ag: 670 | Conta: 12345-6;;;;;\n"
        "Data;Histórico;Docto.;Crédito (R$);Débito (R$);Saldo (R$)\n"
        "03/11/2026;RENTAB.INVEST FACILCRED*;1;0,09; ;1.000,09\n"
        "05/11/2026;PIX ENVIADO;647349; ;2.350,00;934,94\n"
        "13/11/2026;TRANSF SALDO C/SAL P/CC;1302374;8.221,50; ;9.156,44\n"
        ";;;;;\n"
        "Os dados acima tem como base 26/11/2026 às 14:55 e estão sujeitos a alterações.;;;;;\n"
        "Lançamentos periódicos;;;;;\n"
        "Data;Histórico;Docto.;Crédito (R$);Débito (R$);\n"
        "10/12/2026;DEBITO FUTURO;999; ;100,00;\n"
    )
    buf = io.BytesIO(csv_text.encode("utf-8"))
    df = checking_account.transform_bradesco(buf)

    assert len(df) == 2
    assert list(df["ag./origem"]) == ["BRAD", "BRAD"]
    assert df.iloc[0]["lançamento"] == "PIX ENVIADO"
    assert df.iloc[0]["valor (R$)"] == "-2350,00"
    assert df.iloc[1]["lançamento"] == "TRANSF SALDO C/SAL P/CC"
    assert df.iloc[1]["valor (R$)"] == "8221,50"
