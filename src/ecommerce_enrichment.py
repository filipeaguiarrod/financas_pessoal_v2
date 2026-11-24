"""Motor de de/para (matching), enriquecimento e reclassificação de compras Amazon na fatura."""

from __future__ import annotations

import datetime
import itertools
import re
from typing import Callable

import pandas as pd
from dateutil.relativedelta import relativedelta

from . import credit_card

AMAZON_PATTERN = re.compile(r"\b(?:amazon|amzn)\b", re.IGNORECASE)
SHOPEE_PATTERN = re.compile(r"\b(?:shopee|shpp)\b", re.IGNORECASE)
MELI_PATTERN = re.compile(r"\b(?:mercado\s*livre|mercadolivre|meli)\b", re.IGNORECASE)
INSTALLMENT_PATTERN = re.compile(
    r"(?:parcela\s+)?(\d{1,2})\s*(?:/|de)\s*(\d{1,2})", re.IGNORECASE
)

ORIGIN_PREFIXES = {
    "amazon": "AMZ",
    "shopee": "Shopee",
    "mercadolivre": "MELI",
    "mercado livre": "MELI",
    "meli": "MELI",
}


def format_enriched_establishment(origem: str | None, descricao: str) -> str:
    """Formata o estabelecimento enriquecido de forma curta: 'AMZ - ...', 'Shopee - ...', 'MELI - ...'."""
    norm = str(origem or "").strip().lower()
    prefix = ORIGIN_PREFIXES.get(norm)
    if not prefix:
        if "amazon" in norm or "amzn" in norm:
            prefix = "AMZ"
        elif "shopee" in norm or "shpp" in norm:
            prefix = "Shopee"
        elif "mercado" in norm or "meli" in norm:
            prefix = "MELI"
        else:
            prefix = str(origem or "").strip() or "Ecommerce"
    return f"{prefix} - {str(descricao).strip()}"


def detect_ecommerce_origin(estabelecimento: str) -> str | None:
    """Identifica a origem de e-commerce ('amazon', 'shopee', 'mercadolivre') pelo descritivo da fatura."""
    if not estabelecimento:
        return None
    text = str(estabelecimento).replace(".", " ").replace("*", " ")
    if AMAZON_PATTERN.search(text):
        return "amazon"
    if SHOPEE_PATTERN.search(text):
        return "shopee"
    if MELI_PATTERN.search(text):
        return "mercadolivre"
    return None


def _filter_orders_by_origin(orders_df: pd.DataFrame, origin: str | None) -> pd.DataFrame:
    if orders_df is None or orders_df.empty:
        return pd.DataFrame(columns=["data", "origem", "pedido_id", "descricao", "valor"])
    if not origin:
        return orders_df.copy()
    orig_col = orders_df["origem"].astype(str).str.lower()
    if origin == "amazon":
        return orders_df[orig_col.str.contains("amazon|amzn", na=False)].copy()
    if origin == "shopee":
        return orders_df[orig_col.str.contains("shopee|shpp", na=False)].copy()
    if origin == "mercadolivre":
        return orders_df[orig_col.str.contains("mercado|meli", na=False)].copy()
    return orders_df[orig_col.str.contains(re.escape(origin), na=False)].copy()


def is_amazon_transaction(estabelecimento: str, store_patterns: str | None = None) -> bool:
    """Retorna True se o lançamento da fatura indicar compra na Amazon (ou padrões configurados)."""
    if not estabelecimento:
        return False
    text = str(estabelecimento).replace(".", " ").replace("*", " ")
    if store_patterns:
        tokens = [re.escape(p.strip()) for p in str(store_patterns).split(",") if p.strip()]
        if tokens:
            pat = re.compile(r"\b(?:" + "|".join(tokens) + r")\b", re.IGNORECASE)
            return bool(pat.search(text))
    return bool(AMAZON_PATTERN.search(text))


def extract_installment_info(text: str) -> tuple[int, int] | None:
    """Extrai (parcela_atual, total_parcelas) de textos como 'Parcela 1/2' ou '2 de 3'."""
    if not text:
        return None
    match = INSTALLMENT_PATTERN.search(str(text))
    if not match:
        return None
    curr, total = int(match.group(1)), int(match.group(2))
    return (curr, total) if total > 1 and 1 <= curr <= total else None


def extract_installment_total(estabelecimento: str) -> int | None:
    """Extrai o total de parcelas (Y de X/Y) quando presente no descritivo."""
    info = extract_installment_info(estabelecimento)
    return info[1] if info else None


def _get_raw_installment_info(raw_df: pd.DataFrame | None, row_idx: int, fallback_text: str) -> tuple[int, int] | None:
    """Recupera (parcela_atual, total_parcelas) do raw_df (Nubank 'title' ou XP 'Parcela')."""
    info = extract_installment_info(fallback_text)
    if info or raw_df is None or row_idx not in raw_df.index:
        return info

    raw_row = raw_df.loc[row_idx]
    for col in ("Parcela", "title", "Estabelecimento"):
        if col in raw_df.columns:
            info = extract_installment_info(str(raw_row.get(col, "")))
            if info:
                return info
    return None


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


def _search_in_window(
    target_date: datetime.date,
    targets: list[tuple[float, float]],
    amazon_orders: pd.DataFrame,
    days_before: int,
    days_after: int,
    is_refund: bool = False,
    implicit_divisors: bool = False,
) -> list[dict]:
    candidates: list[dict] = []
    seen_keys: set[tuple] = set()

    for _, order in amazon_orders.iterrows():
        ord_date = _to_date(order.get("data"))
        if ord_date is None:
            continue

        delta_days = (target_date - ord_date).days
        if not (-days_before <= delta_days <= days_after):
            continue

        ord_val = round(float(order.get("valor", 0.0)), 2)
        matched_diff = None

        for target_val, tol in targets:
            diff = abs(ord_val - target_val)
            if diff <= tol:
                matched_diff = diff
                break

        if matched_diff is None and implicit_divisors and targets:
            base_val, tol = targets[0]
            if base_val > 0 and ord_val > base_val:
                for k in range(2, 13):
                    if abs((ord_val / k) - base_val) <= tol:
                        matched_diff = round(abs((ord_val / k) - base_val), 2)
                        break

        if matched_diff is None:
            continue

        pedido_id = str(order.get("pedido_id", "")).strip()
        descricao = str(order.get("descricao", "")).strip()
        if is_refund:
            descricao = f"[Estorno] {descricao}"
        key = (pedido_id, descricao, ord_val)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        candidates.append({
            "origem": str(order.get("origem", "")).strip(),
            "pedido_id": pedido_id,
            "descricao": descricao,
            "valor": ord_val,
            "data": ord_date,
            "delta_days": abs(delta_days),
            "valor_diff": round(matched_diff, 2),
        })

    candidates.sort(key=lambda c: (c["delta_days"], c["valor_diff"]))
    return candidates


def _find_combo_candidates(
    target_date: datetime.date,
    target_val: float,
    amazon_orders: pd.DataFrame,
    days_before: int,
    days_after: int,
    tol: float,
) -> list[dict]:
    """Tenta casar uma cobrança única com a soma de 2 a 4 pedidos na mesma janela."""
    window_orders = []
    for _, order in amazon_orders.iterrows():
        ord_date = _to_date(order.get("data"))
        if ord_date is None:
            continue
        delta_days = (target_date - ord_date).days
        if -days_before <= delta_days <= days_after:
            window_orders.append({
                "origem": str(order.get("origem", "")).strip(),
                "pedido_id": str(order.get("pedido_id", "")).strip(),
                "descricao": str(order.get("descricao", "")).strip(),
                "valor": round(float(order.get("valor", 0.0)), 2),
                "data": ord_date,
            })

    if len(window_orders) < 2 or len(window_orders) > 15:
        return []

    combos: list[dict] = []
    for size in range(2, min(4, len(window_orders)) + 1):
        for comb in itertools.combinations(window_orders, size):
            total = round(sum(item["valor"] for item in comb), 2)
            diff = abs(total - target_val)
            if diff <= tol:
                combos.append({
                    "origem": comb[0].get("origem", ""),
                    "pedido_id": ", ".join(dict.fromkeys(i["pedido_id"] for i in comb if i["pedido_id"])),
                    "descricao": " + ".join(i["descricao"] for i in comb),
                    "valor": total,
                    "data": max(i["data"] for i in comb),
                    "delta_days": abs((target_date - max(i["data"] for i in comb)).days),
                    "valor_diff": round(diff, 2),
                })
        if combos:
            break

    combos.sort(key=lambda c: (c["delta_days"], c["valor_diff"]))
    return combos


def find_amazon_candidates(
    inv_date: datetime.date | None,
    inv_value: float,
    estabelecimento: str,
    amazon_orders: pd.DataFrame,
    days_before: int = 2,
    days_after: int = 7,
    value_tolerance: float = 0.05,
    installment_tolerance: float = 0.20,
    installment_info: tuple[int, int] | None = None,
) -> list[dict]:
    """Busca pedidos da Amazon candidatos para uma transação da fatura."""
    if amazon_orders is None or amazon_orders.empty or inv_date is None:
        return []

    is_refund = float(inv_value) < 0
    abs_val = round(abs(float(inv_value)), 2)

    info = installment_info or extract_installment_info(estabelecimento)
    targets = [(abs_val, float(value_tolerance))]
    if info and not is_refund:
        targets.append((round(abs_val * info[1], 2), float(installment_tolerance)))

    # 1) Busca direta (valor exato ou parcela X/Y na janela normal)
    candidates = _search_in_window(
        inv_date, targets, amazon_orders, days_before, days_after, is_refund=is_refund
    )
    if candidates:
        return candidates

    # 2) Se for parcela X/Y com X > 1, busca deslocando (X - 1) meses para trás
    if info and info[0] > 1 and not is_refund:
        shifted_date = inv_date - relativedelta(months=info[0] - 1)
        candidates = _search_in_window(
            shifted_date,
            [(round(abs_val * info[1], 2), float(installment_tolerance))],
            amazon_orders,
            days_before,
            days_after,
        )
        if candidates:
            return candidates

    # 3) Fallback: parcela implícita (order.valor / k == abs_val)
    if not is_refund:
        candidates = _search_in_window(
            inv_date,
            [(abs_val, float(value_tolerance))],
            amazon_orders,
            days_before,
            days_after,
            implicit_divisors=True,
        )
        if candidates:
            return candidates

        # 4) Fallback: combo de carrinho (soma de 2 a 4 pedidos na janela)
        return _find_combo_candidates(
            inv_date, abs_val, amazon_orders, days_before, days_after, float(value_tolerance)
        )

    return []


def enrich_amazon_transactions(
    invoice_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    days_before: int = 2,
    days_after: int = 7,
    value_tolerance: float = 0.05,
    installment_tolerance: float = 0.20,
    store_patterns: str | None = None,
    raw_df: pd.DataFrame | None = None,
    classify_fn: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, dict[int, list[dict]]]:
    """Faz de/para de lançamentos Amazon da fatura contra pedidos do banco e reclassifica."""
    df = invoice_df.copy().reset_index(drop=True)
    if "categoria" not in df.columns:
        df["categoria"] = None
    if "_source" not in df.columns:
        df["_source"] = None

    df["match_status"] = "nao_amazon"
    df["pedido_id"] = ""
    df["descricao_produto"] = ""

    if orders_df is None or orders_df.empty:
        all_orders = pd.DataFrame(columns=["data", "origem", "pedido_id", "descricao", "valor"])
    else:
        all_orders = orders_df.copy()

    ambiguous_map: dict[int, list[dict]] = {}
    matched_indices: list[int] = []
    matched_descriptions: list[dict] = []

    for idx, row in df.iterrows():
        estab = str(row.get("Estabelecimento", ""))
        detected_origin = detect_ecommerce_origin(estab)
        matches_custom = bool(store_patterns) and is_amazon_transaction(estab, store_patterns=store_patterns)
        if not detected_origin and not matches_custom:
            continue

        origin_orders = _filter_orders_by_origin(all_orders, detected_origin)
        inv_date = _to_date(row.get("Data"))
        inv_val = round(float(row.get("Valor", 0.0)), 2)
        inst_info = _get_raw_installment_info(raw_df, idx, estab)
        candidates = find_amazon_candidates(
            inv_date=inv_date,
            inv_value=inv_val,
            estabelecimento=estab,
            amazon_orders=origin_orders,
            days_before=days_before,
            days_after=days_after,
            value_tolerance=value_tolerance,
            installment_tolerance=installment_tolerance,
            installment_info=inst_info,
        )

        if not candidates:
            df.at[idx, "match_status"] = "sem_match"
        elif len(candidates) == 1:
            best = candidates[0]
            best_origin = best.get("origem") or detected_origin or "Amazon"
            df.at[idx, "match_status"] = "matched"
            df.at[idx, "pedido_id"] = best["pedido_id"]
            df.at[idx, "descricao_produto"] = best["descricao"]
            df.at[idx, "Estabelecimento"] = format_enriched_establishment(best_origin, best["descricao"])
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
