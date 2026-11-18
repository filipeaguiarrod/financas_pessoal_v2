"""Sincronização de pedidos de e-commerce do Google Sheets privado para o PostgreSQL."""

from __future__ import annotations

import logging
import os
from typing import Any

import gspread
import pandas as pd
from dotenv import load_dotenv

from . import postgres as ps

load_dotenv(dotenv_path=os.path.abspath(".env"))

logger = logging.getLogger(__name__)


def _parse_br_amount(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return round(float(val), 2)

    s = str(val).replace("R$", "").replace("\xa0", "").strip()
    if not s:
        return None

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _parse_date(val: Any):
    if val is None or str(val).strip() == "":
        return None
    s = str(val).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return pd.to_datetime(s, format=fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def parse_sheet_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Normaliza registros brutos da aba Pedidos_Ecommerce em DataFrame pronto para o Postgres."""
    columns = ["data", "origem", "pedido_id", "descricao", "valor", "email_id"]
    if not records:
        return pd.DataFrame(columns=columns)

    rows = []
    for rec in records:
        norm = {str(k).strip().lower(): v for k, v in rec.items()}
        dt = _parse_date(norm.get("data"))
        val = _parse_br_amount(norm.get("valor"))
        email_id = str(norm.get("email_id") or "").strip()
        descricao = str(norm.get("descricao") or "").strip()
        origem = str(norm.get("origem") or "").strip()
        pedido_id = str(norm.get("pedido_id") or "").strip()

        if dt is None or val is None or val <= 0 or not email_id or not descricao:
            continue

        rows.append({
            "data": dt,
            "origem": origem or "Amazon",
            "pedido_id": pedido_id,
            "descricao": descricao,
            "valor": val,
            "email_id": email_id,
        })

    return pd.DataFrame(rows, columns=columns)


def fetch_orders_from_sheets() -> pd.DataFrame:
    """Lê a aba de pedidos de e-commerce no Google Sheets usando a Service Account configurada no .env."""
    sa_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "").strip()
    sheet_id = os.environ.get("ECOMMERCE_SHEET_ID", "").strip()
    tab_name = os.environ.get("ECOMMERCE_SHEET_TAB", "Pedidos_Ecommerce").strip() or "Pedidos_Ecommerce"

    if not sa_path or not os.path.exists(sa_path):
        raise FileNotFoundError(
            "Credencial da Service Account não encontrada. Verifique GOOGLE_SERVICE_ACCOUNT_PATH no .env."
        )
    if not sheet_id:
        raise ValueError("ECOMMERCE_SHEET_ID não configurado no .env.")

    client = gspread.service_account(filename=sa_path)
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(tab_name)
    records = worksheet.get_all_records()
    return parse_sheet_records(records)


def sync_ecommerce_orders_to_db(psql: ps.PostgresUploader | None = None) -> dict[str, int]:
    """Sincroniza os pedidos do Google Sheets para a tabela ecommerce_orders no Postgres."""
    df_orders = fetch_orders_from_sheets()
    uploader = psql or ps.PostgresUploader()
    inserted = uploader.upsert_ecommerce_orders(df_orders)
    logger.info("Sincronização de e-commerce concluída: %d lidos, %d novos inseridos.", len(df_orders), inserted)
    return {"total_sheet": int(len(df_orders)), "inserted": int(inserted)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    summary = sync_ecommerce_orders_to_db()
    print(f"Sync concluído: {summary['total_sheet']} registros lidos, {summary['inserted']} novos inseridos.")
