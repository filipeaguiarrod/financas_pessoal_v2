"""Cliente HTTP para buscar faturas CSV mais recentes (XP e Nubank) no financas_backend."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from . import reconciler

load_dotenv(dotenv_path=os.path.abspath(".env"))

DEFAULT_FINANCAS_API_URL = "http://localhost:7555"
SUPPORTED_BANKS = ("xp", "nubank")
DEFAULT_SHEET_RANGES = {
    "xp": "G4:J98",
    "nubank": "G99:J200",
}


class InvoiceClientError(RuntimeError):
    """Erro amigável ao buscar fatura no financas_backend."""


@dataclass
class RemoteInvoice:
    bank: str
    source: str
    filename: str
    date: str | None
    csv_bytes: bytes

    def to_bytes_io(self) -> io.BytesIO:
        buf = io.BytesIO(self.csv_bytes)
        buf.name = self.filename
        return buf


def get_backend_api_url() -> str:
    """Retorna a URL base do financas_backend configurada em FINANCAS_API_URL."""
    return (
        os.environ.get("FINANCAS_API_URL", DEFAULT_FINANCAS_API_URL).strip().rstrip("/")
        or DEFAULT_FINANCAS_API_URL
    )


def fetch_latest_invoice(
    bank: str,
    *,
    api_url: str | None = None,
    timeout: int = 30,
) -> RemoteInvoice:
    """Solicita ao financas_backend o CSV mais recente para o banco informado ('xp' ou 'nubank')."""
    normalized_bank = bank.strip().lower()
    if normalized_bank not in SUPPORTED_BANKS:
        raise ValueError(
            f"Banco '{bank}' não suportado. Use um de: {', '.join(SUPPORTED_BANKS)}."
        )

    base_url = (api_url or get_backend_api_url()).rstrip("/")
    endpoint = f"{base_url}/invoices/{normalized_bank}/latest"

    try:
        resp = requests.get(endpoint, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        raise InvoiceClientError(
            f"Não foi possível conectar ao financas_backend ({base_url}). "
            "Verifique se o servidor está ativo e se FINANCAS_API_URL está configurado no .env."
        ) from exc

    if resp.status_code != 200:
        detail = ""
        try:
            payload = resp.json()
            detail = str(payload.get("detail") or "")
        except Exception:
            detail = resp.text.strip()
        msg = detail or f"Erro HTTP {resp.status_code} ao buscar fatura {normalized_bank.upper()}."
        raise InvoiceClientError(msg)

    data = resp.json()
    csv_content = data.get("csv_content")
    if not csv_content:
        raise InvoiceClientError(
            f"O backend retornou uma resposta vazia para a fatura {normalized_bank.upper()}."
        )

    return RemoteInvoice(
        bank=str(data.get("bank") or normalized_bank),
        source=str(data.get("source") or "backend"),
        filename=str(data.get("filename") or f"{normalized_bank}.csv"),
        date=data.get("date"),
        csv_bytes=csv_content.encode("utf-8"),
    )


def _extract_error_detail(resp: requests.Response, fallback: str) -> str:
    try:
        payload = resp.json()
        detail = str(payload.get("detail") or "").strip()
        if detail:
            return detail
    except Exception:
        pass
    text = (resp.text or "").strip()
    return text or fallback


def fetch_sheets_card_block(
    bank: str,
    mes: str,
    *,
    api_url: str | None = None,
    timeout: int = 30,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Lê o bloco atual do cartão no Google Sheets via financas_backend."""
    normalized_bank = bank.strip().lower()
    if normalized_bank not in SUPPORTED_BANKS:
        raise ValueError(
            f"Banco '{bank}' não suportado. Use um de: {', '.join(SUPPORTED_BANKS)}."
        )

    base_url = (api_url or get_backend_api_url()).rstrip("/")
    endpoint = f"{base_url}/sheets/card-block"

    try:
        resp = requests.get(
            endpoint,
            params={"bank": normalized_bank, "mes": mes.strip().lower()},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise InvoiceClientError(
            f"Não foi possível conectar ao financas_backend ({base_url}). "
            "Verifique se o servidor está ativo e se FINANCAS_API_URL está configurado."
        ) from exc

    if resp.status_code != 200:
        raise InvoiceClientError(
            _extract_error_detail(
                resp,
                f"Erro HTTP {resp.status_code} ao ler bloco {normalized_bank.upper()} no Sheets.",
            )
        )

    payload = resp.json()
    raw_rows = payload.get("rows") or []

    records = []
    for row in raw_rows:
        padded = list(row[:4]) + [""] * max(0, 4 - len(row))
        cat = str(padded[0]).strip() or None
        dt_str = str(padded[1]).strip()
        estab = str(padded[2]).strip()
        val = reconciler.parse_amount(padded[3])
        records.append({
            "categoria": cat,
            "Data": dt_str,
            "Estabelecimento": estab,
            "Valor": val,
        })

    df_sheets = (
        pd.DataFrame(records, columns=["categoria", "Data", "Estabelecimento", "Valor"])
        if records
        else pd.DataFrame(columns=["categoria", "Data", "Estabelecimento", "Valor"])
    )
    meta = {
        "bank": payload.get("bank", normalized_bank),
        "mes": payload.get("mes", mes.strip().lower()),
        "range": payload.get("range", DEFAULT_SHEET_RANGES.get(normalized_bank, "")),
        "max_rows": int(payload.get("max_rows", 0)),
        "row_count": len(df_sheets),
    }
    return df_sheets, meta


def format_reconciled_rows_for_sheets(df_reconciled: pd.DataFrame) -> list[list[str]]:
    """Converte o DataFrame reconciliado para linhas [categoria, Data, Estabelecimento, Valor_BR]."""
    if df_reconciled is None or df_reconciled.empty:
        return []

    rows: list[list[str]] = []
    for _, row in df_reconciled.iterrows():
        cat = "" if pd.isna(row.get("categoria")) else str(row.get("categoria")).strip()
        dt_str = "" if pd.isna(row.get("Data")) else str(row.get("Data")).strip()
        estab = "" if pd.isna(row.get("Estabelecimento")) else str(row.get("Estabelecimento")).strip()
        val = reconciler.parse_amount(row.get("Valor"))
        val_br = f"{val:.2f}".replace(".", ",")
        rows.append([cat, dt_str, estab, val_br])
    return rows


def write_sheets_card_block(
    bank: str,
    mes: str,
    df_reconciled: pd.DataFrame,
    *,
    api_url: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Envia o bloco reconciliado para gravação direta no Google Sheets via financas_backend."""
    normalized_bank = bank.strip().lower()
    if normalized_bank not in SUPPORTED_BANKS:
        raise ValueError(
            f"Banco '{bank}' não suportado. Use um de: {', '.join(SUPPORTED_BANKS)}."
        )

    base_url = (api_url or get_backend_api_url()).rstrip("/")
    endpoint = f"{base_url}/sheets/card-block"
    rows = format_reconciled_rows_for_sheets(df_reconciled)

    try:
        resp = requests.post(
            endpoint,
            json={
                "bank": normalized_bank,
                "mes": mes.strip().lower(),
                "rows": rows,
            },
            timeout=timeout,
        )
    except requests.exceptions.RequestException as exc:
        raise InvoiceClientError(
            f"Não foi possível conectar ao financas_backend ({base_url}) para gravar no Sheets."
        ) from exc

    if resp.status_code != 200:
        raise InvoiceClientError(
            _extract_error_detail(
                resp,
                f"Erro HTTP {resp.status_code} ao gravar bloco {normalized_bank.upper()} no Sheets.",
            )
        )

    return resp.json()
