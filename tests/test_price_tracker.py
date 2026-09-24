import pandas as pd
import pytest
from src.price_tracker_service import (
    extract_asin,
    calculate_distribution_stats,
    get_products_summary_df,
    resolve_product_url,
)

def test_extract_asin():
    url1 = "https://www.amazon.com.br/dp/B07YXF387Y"
    url2 = "https://www.amazon.com.br/gp/product/B07YXF387Y?ref=ppx_pt2_dt_b_prod_image"
    url3 = "https://www.amazon.com.br/Product-Title/dp/B07YXF387Y/ref=sr_1_1"
    url4 = "https://www.amazon.com.br/dp/b07yxf387y"
    url_invalid = "https://www.amazon.com.br/invalid-link-without-asin"

    assert extract_asin(url1) == "B07YXF387Y"
    assert extract_asin(url2) == "B07YXF387Y"
    assert extract_asin(url3) == "B07YXF387Y"
    assert extract_asin(url4) == "B07YXF387Y"
    assert extract_asin(url_invalid) is None

def test_resolve_product_url():
    # Full valid URL provided
    assert resolve_product_url(
        url="https://www.amazon.com.br/dp/B07YXF387Y",
        asin="B07YXF387Y"
    ) == "https://www.amazon.com.br/dp/B07YXF387Y"

    # Fallback to ASIN when URL is empty or None
    assert resolve_product_url(
        url=None,
        asin="B07YXF387Y"
    ) == "https://www.amazon.com.br/dp/B07YXF387Y"

    assert resolve_product_url(
        url="",
        asin="b07yxf387y"
    ) == "https://www.amazon.com.br/dp/B07YXF387Y"

    # Fallback to ASIN when URL is not a valid http link
    assert resolve_product_url(
        url="not_a_url",
        asin="B07YXF387Y"
    ) == "https://www.amazon.com.br/dp/B07YXF387Y"

    # Both empty
    assert resolve_product_url(url=None, asin=None) == ""
    assert resolve_product_url(url="", asin="") == ""

def test_calculate_distribution_stats():
    # Empty dataframe
    assert calculate_distribution_stats(pd.DataFrame()) == {}

    # Valid dataframe
    df = pd.DataFrame({
        "price": [10.0, 20.0, 30.0, 40.0, 50.0]
    })
    stats = calculate_distribution_stats(df)
    assert stats["min_price"] == 10.0
    assert stats["max_price"] == 50.0
    assert stats["mean_price"] == 30.0
    assert stats["median_price"] == 30.0
    assert stats["current_price"] == 50.0
    assert "recommendation" in stats
    assert "status_tag" in stats

    # Test with simulated value near min
    stats_low = calculate_distribution_stats(df, test_val=12.0)
    assert stats_low["percentile"] <= 25.0
    assert "Oportunidade" in stats_low["recommendation"]

    # Test with simulated value near max
    stats_high = calculate_distribution_stats(df, test_val=48.0)
    assert stats_high["percentile"] >= 75.0
    assert "Preço Alto" in stats_high["recommendation"]

def test_get_products_summary_df_structure():
    df = get_products_summary_df()
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        required_cols = [
            "asin", "name", "category", "is_active", "url",
            "min_price", "mean_price", "max_price",
            "latest_price", "latest_scraped_at", "total_samples"
        ]
        for col in required_cols:
            assert col in df.columns
