"""Serviço de gerenciamento de produtos e consulta de histórico de preços para o Streamlit."""
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml
import pandas as pd
import numpy as np
from src.postgres import PostgresUploader

ROOT_DIR = Path(__file__).resolve().parent.parent

def get_products_yaml_path() -> Path:
    """Descobre o caminho do arquivo products.yaml tanto no Windows quanto no Servidor."""
    env_path = os.getenv("SCRAPER_PRODUCTS_YAML")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    # 1. Caminho relativo padrão (projetos irmãos: Projetos/scraper e Projetos/financas_pessoal_v2)
    relative_path = ROOT_DIR.parent / "scraper" / "config" / "products.yaml"
    if relative_path.exists():
        return relative_path

    # 2. Caminho padrão do servidor Linux
    server_path = Path("/home/rodri/projects/scraper/config/products.yaml")
    if server_path.exists():
        return server_path

    return relative_path

def extract_asin(url: str) -> Optional[str]:
    """Extrai o ASIN da URL da Amazon."""
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

def load_products_from_yaml() -> List[Dict[str, Any]]:
    """Lê os produtos cadastrados no arquivo products.yaml."""
    yaml_path = get_products_yaml_path()
    if not yaml_path.exists():
        return []
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("products", [])
    except Exception as e:
        print(f"Erro ao ler products.yaml: {e}")
        return []

def add_product_to_yaml(name: str, url: str, category: str = "Geral", target_price: Optional[float] = None, active: bool = True) -> Dict[str, Any]:
    """Adiciona um novo produto ao arquivo products.yaml."""
    yaml_path = get_products_yaml_path()
    products = load_products_from_yaml()

    asin = extract_asin(url)
    prod_id = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower().strip())
    if asin and not prod_id:
        prod_id = f"prod_{asin.lower()}"

    new_item = {
        "id": prod_id[:30],
        "name": name.strip(),
        "url": url.strip(),
        "category": category.strip() if category else "Geral",
        "target_price": float(target_price) if target_price else None,
        "active": bool(active),
    }

    # Verifica se a URL já existe para atualizar
    existing_idx = next((i for i, p in enumerate(products) if p.get("url") == url.strip() or (asin and extract_asin(p.get("url", "")) == asin)), None)
    if existing_idx is not None:
        products[existing_idx] = new_item
    else:
        products.append(new_item)

    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump({"products": products}, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return new_item

def get_tracked_products_df() -> pd.DataFrame:
    """Busca os produtos cadastrados no PostgreSQL (scrapers.amazon_products)."""
    try:
        uploader = PostgresUploader()
        query = "SELECT asin, name, url, category, target_price, is_active, created_at FROM scrapers.amazon_products ORDER BY name ASC;"
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
    """Calcula estatísticas de distribuição e avalia onde um determinado preço se posiciona."""
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

    # Percentil: % dos preços históricos que foram MENORES que o preço avaliado
    percentile = float((prices < eval_price).mean() * 100.0)

    # Classificação amigável
    if percentile <= 20.0:
        recommendation = "🟢 Oportunidade Excepcional! Próximo à mínima histórica."
        color = "green"
    elif percentile <= 45.0:
        recommendation = "🟡 Bom Preço! Abaixo da média histórica."
        color = "gold"
    elif percentile <= 75.0:
        recommendation = "🟠 Preço Médio / Regular."
        color = "orange"
    else:
        recommendation = "🔴 Preço Alto! Próximo à máxima histórica."
        color = "red"

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
        "recommendation": recommendation,
        "color": color,
    }
