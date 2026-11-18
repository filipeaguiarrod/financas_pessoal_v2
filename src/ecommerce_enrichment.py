"""Motor de de/para (matching), enriquecimento e reclassificação de compras Amazon na fatura."""

from __future__ import annotations

import datetime
import re
from typing import Callable

import pandas as pd

from . import credit_card

AMAZON_PATTERN = re.compile(r"\b(?:amazon|amzn)\b", re.IGNORECASE)
INSTALLMENT_PATTERN = re.compile(r"(?:parcela\s+)?(\d{1,2})\s*/\s*(\d{1,2})", re.IGNORECASE)


def is_amazon_transaction(estabelecimento: str) -> bool:
    """Retorna True se o lançamento da fatura indicar compra na Amazon."""
    if not estabelecimento:
        return False
    text = str(estabelecimento).replace(".", " ")
    return bool(AMAZON_PATTERN.search(text))


def extract_installment_total(estabelecimento: str) -> int | None:
    """Extrai o total de parcelas (Y de X/Y) quando presente no descritivo."""
    if not estabelecimento:
        return None
    match = INSTALLMENT_PATTERN.search(str(estabelecimento))
    if not match:
        return None
    total = int(match.group(2))
    return total if total > 1 else None


def _to_date(val) -> datetime.date | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def find_amazon_candidates(
    inv_date: datetime.date | None,
    inv_value: float,
    estabelecimento: str,
    amazon_orders: pd.DataFrame,
    days_before: int = 2,
    days_after: int = 7,
) -> list[dict]:
    """Busca pedidos da Amazon candidatos para uma transação da fatura."""
    if amazon_orders is None or amazon_orders.empty or inv_date is None:
        return []

    total_parcelas = extract_installment_total(estabelecimento)
    targets = [(round(float(inv_value), 2), 0.05)]
    if total_parcelas:
        targets.append((round(float(inv_value) * total_parcelas, 2), 0.20))

    candidates: list[dict] = []
    seen_keys: set[tuple] = set()

    for _, order in amazon_orders.iterrows():
        ord_date = _to_date(order.get("data"))
        if ord_date is None:
            continue

        delta_days = (inv_date - ord_date).days
        if not (-days_before <= delta_days <= days_after):
            continue

        ord_val = round(float(order.get("valor", 0.0)), 2)
        matched_diff = None
        for target_val, tol in targets:
            diff = abs(ord_val - target_val)
            if diff <= tol:
                matched_diff = diff
                break

        if matched_diff is None:
            continue

        pedido_id = str(order.get("pedido_id", "")).strip()
        descricao = str(order.get("descricao", "")).strip()
        key = (pedido_id, descricao, ord_val)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        candidates.append({
            "pedido_id": pedido_id,
            "descricao": descricao,
            "valor": ord_val,
            "data": ord_date,
            "delta_days": abs(delta_days),
            "valor_diff": round(matched_diff, 2),
        })

    candidates.sort(key=lambda c: (c["delta_days"], c["valor_diff"]))
    return candidates


def enrich_amazon_transactions(
    invoice_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    days_before: int = 2,
    days_after: int = 7,
    classify_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, dict[int, list[dict]]]:
    """Faz de/para de lançamentos Amazon da fatura contra pedidos do banco e reclassifica.

    Retorna:
    - DataFrame enriquecido com colunas ['categoria', '_source', 'Data', 'Estabelecimento', 'Valor', 'match_status', 'pedido_id', 'descricao_produto']
    - Dicionário {row_index: [candidatos]} para linhas ambíguas.
    """
    df = invoice_df.copy().reset_index(drop=True)
    if "categoria" not in df.columns:
        df["categoria"] = None
    if "_source" not in df.columns:
        df["_source"] = None

    df["match_status"] = "nao_amazon"
    df["pedido_id"] = ""
    df["descricao_produto"] = ""

    if orders_df is None or orders_df.empty:
        amazon_orders = pd.DataFrame(columns=["data", "origem", "pedido_id", "descricao", "valor"])
    else:
        amazon_orders = orders_df[
            orders_df["origem"].astype(str).str.lower().str.contains("amazon", na=False)
        ].copy()

    ambiguous_map: dict[int, list[dict]] = {}
    matched_indices: list[int] = []
    matched_descriptions: list[dict] = []

    for idx, row in df.iterrows():
        estab = str(row.get("Estabelecimento", ""))
        if not is_amazon_transaction(estab):
            continue

        inv_date = _to_date(row.get("Data"))
        inv_val = round(float(row.get("Valor", 0.0)), 2)
        candidates = find_amazon_candidates(
            inv_date=inv_date,
            inv_value=inv_val,
            estabelecimento=estab,
            amazon_orders=amazon_orders,
            days_before=days_before,
            days_after=days_after,
        )

        if not candidates:
            df.at[idx, "match_status"] = "sem_match"
        elif len(candidates) == 1:
            best = candidates[0]
            df.at[idx, "match_status"] = "matched"
            df.at[idx, "pedido_id"] = best["pedido_id"]
            df.at[idx, "descricao_produto"] = best["descricao"]
            df.at[idx, "Estabelecimento"] = f"{estab} — {best['descricao']}"
            matched_indices.append(idx)
            matched_descriptions.append({
                "Data": row.get("Data"),
                "Estabelecimento": best["descricao"],
                "Valor": inv_val,
            })
        else:
            df.at[idx, "match_status"] = "ambiguo"
            ambiguous_map[idx] = candidates

    if matched_indices:
        reclass_input = pd.DataFrame(matched_descriptions)
        reclass_fn = classify_fn or credit_card.classify_invoice
        reclassified = reclass_fn(reclass_input)
        for pos, orig_idx in enumerate(matched_indices):
            df.at[orig_idx, "categoria"] = reclassified.at[pos, "categoria"]
            if "_source" in reclassified.columns:
                df.at[orig_idx, "_source"] = reclassified.at[pos, "_source"]

    return df, ambiguous_map


_MATCH_COLORS = {
    "matched": "color: #2E7D32; font-weight: 600",
    "matched_manual": "color: #2E7D32; font-weight: 600",
    "ambiguo": "color: #E65100; font-weight: 600",
    "sem_match": "color: #C62828",
    "nao_amazon": "",
}


def style_enriched(df: pd.DataFrame):
    """Aplica destaque de cor em Estabelecimento (match_status) e categoria (_source)."""
    source = df["_source"].copy() if "_source" in df.columns else None
    match_status = df["match_status"].copy() if "match_status" in df.columns else None

    drop_cols = [c for c in ("_source", "match_status") if c in df.columns]
    display_df = df.drop(columns=drop_cols)
    styler = display_df.style

    if source is not None and "categoria" in display_df.columns:
        styler = styler.apply(
            lambda _col: source.map(credit_card._SOURCE_COLORS).fillna(""),
            subset=["categoria"],
        )

    if match_status is not None and "Estabelecimento" in display_df.columns:
        styler = styler.apply(
            lambda _col: match_status.map(_MATCH_COLORS).fillna(""),
            subset=["Estabelecimento"],
        )

    return styler
