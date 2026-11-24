"""Cliente HTTP para buscar faturas CSV mais recentes (XP e Nubank) no financas_backend."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.abspath(".env"))

DEFAULT_FINANCAS_API_URL = "http://localhost:7555"
SUPPORTED_BANKS = ("xp", "nubank")


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
