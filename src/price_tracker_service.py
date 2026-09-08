"""Serviço de gerenciamento de produtos e consulta de histórico de preços para o Streamlit."""
import re
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from sqlalchemy import text
from src.postgres import PostgresUploader

def extract_asin(url: str) -> Optional[str]:
    """Extrai o código ASIN (10 caracteres alfanuméricos) da URL da Amazon."""
    patterns = [
        r"/(?:dp|gp/product)/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
        r"asin=([A-Z0-9]{10})",
    ]
    for p in patterns:
        m = re.search(p, url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None

def add_product_to_db(name: str, url: str, category: str = "Geral", is_active: bool = True) -> Dict[str, Any]:
    """Cadastra ou atualiza o produto diretamente na tabela scrapers.amazon_products no PostgreSQL."""
    asin = extract_asin(url)
    if not asin:
        raise ValueError("Não foi possível identificar o código ASIN na URL informada.")

    clean_url = f"https://www.amazon.com.br/dp/{asin}"
    uploader = PostgresUploader()

    query = text("""
        INSERT INTO scrapers.amazon_products (asin, name, url, category, is_active, created_at)
        VALUES (:asin, :name, :url, :category, :is_active, NOW())
        ON CONFLICT (asin) DO UPDATE SET
            name = EXCLUDED.name,
            url = EXCLUDED.url,
            category = EXCLUDED.category,
            is_active = EXCLUDED.is_active;
    """)

    params = {
        "asin": asin,
        "name": name.strip(),
        "url": clean_url,
        "category": category.strip() if category else "Geral",
        "is_active": is_active,
    }

    with uploader.engine.begin() as conn:
        conn.execute(query, params)

    return {"asin": asin, "name": name, "url": clean_url, "category": category}

def toggle_product_status(asin: str, is_active: bool):
    """Ativa ou pausa o rastreamento de um produto no banco."""
    uploader = PostgresUploader()
    query = text("UPDATE scrapers.amazon_products SET is_active = :is_active WHERE asin = :asin;")
    with uploader.engine.begin() as conn:
        conn.execute(query, {"is_active": is_active, "asin": asin})

def get_tracked_products_df() -> pd.DataFrame:
    """Busca todos os produtos cadastrados no PostgreSQL (scrapers.amazon_products)."""
    try:
        uploader = PostgresUploader()
        query = "SELECT asin, name, url, category, is_active, created_at FROM scrapers.amazon_products ORDER BY name ASC;"
        df = uploader.query_to_df(query)
        return df
    except Exception as e:
        print(f"Erro ao consultar amazon_products: {e}")
        return pd.DataFrame()

def get_price_history_df(asin: str) -> pd.DataFrame:
    """Busca o histórico de preços completo de um produto no PostgreSQL."""
    try:
        uploader = PostgresUploader()
        query = f"""
            SELECT id, asin, scraped_at, price, currency, availability, rating, reviews_count
            FROM scrapers.amazon_price_history
            WHERE asin = '{asin}' AND price IS NOT NULL
            ORDER BY scraped_at ASC;
        """
        df = uploader.query_to_df(query)
        if not df.empty:
            df["scraped_at"] = pd.to_datetime(df["scraped_at"])
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.dropna(subset=["price"])
        return df
    except Exception as e:
        print(f"Erro ao consultar amazon_price_history: {e}")
        return pd.DataFrame()

def calculate_distribution_stats(df_history: pd.DataFrame, test_val: Optional[float] = None) -> Dict[str, Any]:
    """Calcula estatísticas de distribuição e avalia a posição de um preço."""
    if df_history.empty or "price" not in df_history.columns:
        return {}

    prices = df_history["price"].values
    min_p = float(np.min(prices))
    max_p = float(np.max(prices))
    mean_p = float(np.mean(prices))
    median_p = float(np.median(prices))
    std_p = float(np.std(prices))
    current_p = float(prices[-1])

    eval_price = float(test_val) if test_val is not None and test_val > 0 else current_p

    # Percentil: percentual de registros históricos que custaram MENOS que o preço avaliado
    percentile = float((prices < eval_price).mean() * 100.0)

    if percentile <= 20.0:
        recommendation = "Oportunidade Excepcional! Próximo à mínima histórica."
        badge = "🟢"
    elif percentile <= 45.0:
        recommendation = "Bom Preço! Abaixo da média histórica."
        badge = "🟡"
    elif percentile <= 75.0:
        recommendation = "Preço Médio / Regular."
        badge = "🟠"
    else:
        recommendation = "Preço Alto! Próximo à máxima histórica."
        badge = "🔴"

    return {
        "min_price": min_p,
        "max_price": max_p,
        "mean_price": mean_p,
        "median_price": median_p,
        "std_price": std_p,
        "current_price": current_p,
        "eval_price": eval_price,
        "percentile": percentile,
        "cheaper_than_pct": 100.0 - percentile,
        "recommendation": f"{badge} {recommendation}",
    }
