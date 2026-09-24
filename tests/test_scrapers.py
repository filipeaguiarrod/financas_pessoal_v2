import pandas as pd
import pytest
from src.scrapers import extract_shoppe_data, extract_amazon_data


SHOPEE_HTML_SAMPLE = """
<div class="fkIi86"><div style="display: contents;">
<main aria-role="tabpanel">
<div class="R5DdXs">
    <div><div class="xMT86T">
        <section>
            <h3 class="a11y-hidden">Seção de Loja do Pedido</h3>
            <div class="yC6Gym">
                <div class="iFSUny">
                    <div class="QM3Kte" tabindex="0">Tubarão Epis</div>
                </div>
                <div class="aNTw0A"><div class="tGTmka" tabindex="0">Preparando</div></div>
            </div>
        </section>
        <section>
            <h3 class="a11y-hidden">Seção da Lista de Itens no pedido</h3>
            <a aria-label="Ir para Detalhes do Produto" href="/user/purchase/order/243967267100764?type=6">
                <div class="wHltjF">
                    <span class="LNTevg" tabindex="0">Kit 5 Respirador Descartável PFF2 Com Válvula</span>
                </div>
                <div class="d53ucJ">
                    <div class="V98FFV"><span class="Z0dmZq">R$16,89</span></div>
                </div>
            </a>
        </section>
    </div></div>
    <div class="AsN_Jh">
        <div class="olCh0b">
            <label class="zdmgVu">Total do Pedido:</label>
            <div class="XTSMWc" tabindex="0" aria-label="Total do Pedido: R$16,61">R$16,61</div>
        </div>
    </div>
</div>
<div class="R5DdXs">
    <div><div class="xMT86T">
        <section>
            <h3 class="a11y-hidden">Seção de Loja do Pedido</h3>
            <div class="yC6Gym">
                <div class="iFSUny">
                    <div class="QM3Kte" tabindex="0">Titanium Metais</div>
                </div>
                <div class="aNTw0A"><div class="tGTmka" tabindex="0">A caminho</div></div>
            </div>
        </section>
        <section>
            <h3 class="a11y-hidden">Seção da Lista de Itens no pedido</h3>
            <a aria-label="Ir para Detalhes do Produto" href="/user/purchase/order/243647465169759?type=6">
                <div class="wHltjF">
                    <span class="LNTevg" tabindex="0">Torneira Com Filtro De Parede Preto Flexível</span>
                </div>
            </a>
        </section>
    </div></div>
    <div class="AsN_Jh">
        <div class="olCh0b">
            <label class="zdmgVu">Total do Pedido:</label>
            <div class="XTSMWc" tabindex="0">R$163,90</div>
        </div>
    </div>
</div>
</main>
</div></div>
"""

SHOPEE_LEGACY_SAMPLE = """
<div class="YL_VlX">
    <span class="DWVWOJ">Produto Legado Shopee</span>
    <div class="UDaMW3">Loja Antiga</div>
    <div class="t7TQaf">R$ 55,00</div>
    <div class="bv3eJE">Entregue</div>
    <a class="lXbYsi" href="/order/legacy123">Detalhes</a>
</div>
"""

AMAZON_HTML_SAMPLE = """
<div class="order-card js-order-card" data-csa-c-type="widget" data-csa-c-content-id="amzn1.yourorders.order-card">
    <div class="order-header">
        <li class="order-header__header-list-item">
            <span class="a-color-secondary a-text-caps">Pedido realizado</span>
            <span class="a-size-base a-color-secondary aok-break-word">22 de setembro de 2026</span>
        </li>
        <li class="order-header__header-list-item">
            <span class="a-color-secondary a-text-caps">Total</span>
            <span class="a-size-base a-color-secondary aok-break-word">R$&nbsp;122,97</span>
        </li>
        <div class="yohtmlc-order-id">
            <span class="a-color-secondary">702-4387586-7534631</span>
        </div>
    </div>
    <div class="yohtmlc-product-title">
        <a class="a-link-normal" href="/dp/B0FPZ6TPNG?ref=ppx_yo2ov_dt_b_fed_asin_title">
            Kit 3 Promun Defense Boost Cat 3ML
        </a>
    </div>
</div>
<div class="order-card js-order-card">
    <div class="order-header">
        <div class="a-column a-span3">
            <span class="a-color-secondary a-text-caps">Pedido realizado</span>
            <span class="a-size-base aok-break-word">15 de agosto de 2026</span>
        </div>
        <div class="a-column a-span2">
            <span class="a-color-secondary a-text-caps">Total</span>
            <span class="a-size-base aok-break-word">R$&nbsp;45,00</span>
        </div>
    </div>
    <div class="yohtmlc-product-title">
        <a class="a-link-normal" href="/dp/B07H45XJ2D">
            Nescafe Dolce Gusto Espresso
        </a>
    </div>
</div>
"""

AMAZON_LEGACY_SAMPLE = """
<div class="order-card js-order-card">
    <span class="a-size-base a-color-secondary aok-break-word">10 de janeiro de 2025</span>
    <span class="a-size-base a-color-secondary aok-break-word">R$&nbsp;89,90</span>
    <a class="a-link-normal" href="/order-details/1">Link 1</a>
    <a class="a-link-normal" href="/invoice/1">Link 2</a>
    <a class="a-link-normal" href="/dp/B000000001">Link 3</a>
    <div class="yohtmlc-product-title">
        <a class="a-link-normal" href="/dp/B000000001">Livro Clean Code</a>
    </div>
</div>
"""


def test_extract_shoppe_data_new_layout():
    df = extract_shoppe_data(SHOPEE_HTML_SAMPLE)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "descricao" in df.columns
    assert "loja" in df.columns
    assert "preco" in df.columns
    assert "status" in df.columns
    assert "url_detalhes" in df.columns

    # First item
    assert "Kit 5 Respirador" in df.iloc[0]["descricao"]
    assert df.iloc[0]["loja"] == "Tubarão Epis"
    assert df.iloc[0]["preco"] == "R$16,61"
    assert df.iloc[0]["status"] == "Preparando"
    assert "243967267100764" in df.iloc[0]["url_detalhes"]

    # Second item
    assert "Torneira Com Filtro" in df.iloc[1]["descricao"]
    assert df.iloc[1]["loja"] == "Titanium Metais"
    assert df.iloc[1]["preco"] == "R$163,90"
    assert df.iloc[1]["status"] == "A caminho"


def test_extract_shoppe_data_legacy():
    df = extract_shoppe_data(SHOPEE_LEGACY_SAMPLE)
    assert len(df) == 1
    assert df.iloc[0]["descricao"] == "Produto Legado Shopee"
    assert df.iloc[0]["loja"] == "Loja Antiga"
    assert "55,00" in df.iloc[0]["preco"]
    assert df.iloc[0]["status"] == "Entregue"
    assert "legacy123" in df.iloc[0]["url_detalhes"]


def test_extract_shoppe_data_empty():
    df_empty = extract_shoppe_data("")
    assert len(df_empty) == 0
    assert set(df_empty.columns) == {'descricao', 'loja', 'preco', 'status', 'url_detalhes'}

    df_none = extract_shoppe_data(None)
    assert len(df_none) == 0


def test_extract_amazon_data_new_layout():
    df = extract_amazon_data(AMAZON_HTML_SAMPLE)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "descricao" in df.columns
    assert "data" in df.columns
    assert "preco" in df.columns
    assert "url_detalhes" in df.columns

    # Item 1
    assert "Kit 3 Promun Defense" in df.iloc[0]["descricao"]
    assert "22 de setembro de 2026" in df.iloc[0]["data"]
    assert "122,97" in df.iloc[0]["preco"]
    assert "B0FPZ6TPNG" in df.iloc[0]["url_detalhes"]

    # Item 2
    assert "Nescafe Dolce Gusto" in df.iloc[1]["descricao"]
    assert "15 de agosto de 2026" in df.iloc[1]["data"]
    assert "45,00" in df.iloc[1]["preco"]
    assert "B07H45XJ2D" in df.iloc[1]["url_detalhes"]


def test_extract_amazon_data_legacy():
    df = extract_amazon_data(AMAZON_LEGACY_SAMPLE)
    assert len(df) >= 1
    assert "Livro Clean Code" in df.iloc[0]["descricao"]
    assert "10 de janeiro de 2025" in df.iloc[0]["data"]
    assert "89,90" in df.iloc[0]["preco"]


def test_extract_amazon_data_empty():
    df_empty = extract_amazon_data("")
    assert len(df_empty) == 0
    assert set(df_empty.columns) == {'descricao', 'data', 'preco', 'url_detalhes'}

    df_none = extract_amazon_data(None)
    assert len(df_none) == 0
