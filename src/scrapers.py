from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import logging
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def extract_shoppe_data(html_string: str) -> pd.DataFrame:
    """Extrai os dados de compras da Shopee a partir de HTML usando heurísticas resilientes em multi-camadas."""
    compras_shoppe = {'descricao': [], 'loja': [], 'preco': [], 'status': [], 'url_detalhes': []}

    if not html_string or not str(html_string).strip():
        return pd.DataFrame(compras_shoppe)

    logging.info("Iniciando a extração de dados do Shopee...")
    soup = BeautifulSoup(html_string, 'html.parser')

    # Identificação dos cards de compra (camada 1: classes novas e legadas)
    div_elements = soup.find_all('div', class_='R5DdXs')
    if not div_elements:
        div_elements = soup.find_all('div', class_='YL_VlX')

    # Camada 2: busca por estrutura de links de pedidos (/user/purchase/order/ ou /user/purchase/cancellation/)
    if not div_elements:
        order_links = soup.find_all('a', href=re.compile(r'/user/purchase/(?:order|cancellation)/'))
        seen_parents = set()
        for link in order_links:
            parent = link
            for _ in range(8):
                parent = parent.parent
                if not parent:
                    break
                if parent.find('section') and ('Total do Pedido' in parent.text or 'Total' in parent.text):
                    if id(parent) not in seen_parents:
                        seen_parents.add(id(parent))
                        div_elements.append(parent)
                    break

    # Camada 3: fallback para cópia de elementos isolados no DevTools
    if not div_elements:
        item_sections = soup.find_all('div', class_=['xMT86T', 'wHltjF'])
        if item_sections:
            div_elements = item_sections
        elif soup.find('span', class_=['LNTevg', 'DWVWOJ']) or soup.find('a', attrs={'aria-label': 'Ir para Detalhes do Produto'}):
            div_elements = [soup]

    logging.info(f"Encontrados {len(div_elements)} elementos de compra no Shopee. Processando cada um...")

    for div in div_elements:
        try:
            # 1. Descrição do produto
            span_desc = div.find('span', class_=['LNTevg', 'DWVWOJ'])
            if not span_desc:
                desc_container = div.find('div', class_='wHltjF')
                if desc_container:
                    span_desc = desc_container.find('span') or desc_container

            if not span_desc:
                link_prod = div.find('a', attrs={'aria-label': 'Ir para Detalhes do Produto'}) or div.find('a', href=re.compile(r'/user/purchase/order/'))
                if link_prod:
                    img = link_prod.find('img', alt=True)
                    if img and img.get('alt') and img['alt'] != 'Imagem do produto':
                        descricao = img['alt'].strip()
                    else:
                        textos = [t.strip() for t in link_prod.stripped_strings if len(t.strip()) > 5 and not t.strip().startswith('R$')]
                        descricao = textos[0] if textos else "Não encontrada"
                else:
                    descricao = "Não encontrada"
            else:
                descricao = span_desc.text.strip()

            # 2. Nome da loja
            div_loja = div.find('div', class_=['QM3Kte', 'UDaMW3'])
            if not div_loja:
                shop_section = div.find('section')
                if shop_section:
                    shop_link = shop_section.find('a', href=re.compile(r'entryPoint=OrderDetail'))
                    if shop_link and shop_link.parent:
                        for sibling in shop_link.parent.find_all(['div', 'span']):
                            txt = sibling.text.strip()
                            if txt and txt.lower() not in ['chat', 'ver página da loja', 'lojas oficiais', 'preferred seller']:
                                div_loja = sibling
                                break
            loja = div_loja.text.strip() if div_loja else "Não encontrada"

            # 3. Preço
            div_preco = div.find('div', class_=['XTSMWc', 't7TQaf'])
            if not div_preco:
                div_preco = div.find('div', class_='olCh0b') or div.find('span', class_='Z0dmZq')
            if not div_preco:
                preco_match = re.search(r'R\$\s*[\d\.,]+', div.text)
                preco = preco_match.group(0).strip() if preco_match else "Não encontrado"
            else:
                preco = div_preco.text.strip()
                if "Total do Pedido:" in preco:
                    preco = preco.replace("Total do Pedido:", "").strip()

            # 4. Status
            div_status = div.find('div', class_=['tGTmka', 'bv3eJE', 'aNTw0A'])
            status = div_status.text.strip() if div_status else "Não encontrado"

            # 5. URL de detalhes
            link_detalhes = div.find('a', attrs={'aria-label': 'Ir para Detalhes do Produto'})
            if not link_detalhes:
                link_detalhes = div.find('a', class_=['lXbYsi', 'wHltjF']) or div.find('a', href=re.compile(r'/user/purchase/order/'))

            if link_detalhes and link_detalhes.has_attr('href'):
                href = link_detalhes['href']
                url_detalhes = href if href.startswith('http') else ("https://shopee.com.br" + href)
            else:
                url_detalhes = "Sem link disponível"

            compras_shoppe['descricao'].append(descricao)
            compras_shoppe['loja'].append(loja)
            compras_shoppe['preco'].append(preco)
            compras_shoppe['status'].append(status)
            compras_shoppe['url_detalhes'].append(url_detalhes)

        except Exception as e_item:
            logging.warning(f"Erro ao processar item individual da Shopee: {e_item}")

    logging.info(f"Compras Shopee extraídas com sucesso: {len(compras_shoppe['descricao'])} itens.")
    return pd.DataFrame(compras_shoppe)


def parse_shoppe(html_string: str) -> pd.DataFrame:
    df = extract_shoppe_data(html_string)
    config = {
        "descricao": st.column_config.TextColumn("Descrição", width="medium"),
        "loja": st.column_config.TextColumn("Loja", width="medium"),
        "preco": st.column_config.TextColumn("Preço", width="small"),
        "status": st.column_config.TextColumn("Status", width="small"),
        "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large")
    }
    return st.dataframe(df, column_config=config, row_height=100, hide_index=True)


def extract_amazon_data(html_string: str) -> pd.DataFrame:
    """Extrai os dados de compras da Amazon a partir de HTML usando heurísticas resilientes."""
    compras_amazon = {'descricao': [], 'data': [], 'preco': [], 'url_detalhes': []}

    if not html_string or not str(html_string).strip():
        return pd.DataFrame(compras_amazon)

    logging.info("Iniciando a extração de dados da Amazon...")
    soup = BeautifulSoup(html_string, 'html.parser')

    # Identificação dos cards de pedido
    div_elements = soup.find_all('div', class_=re.compile(r'\border-card\b'))
    if not div_elements:
        div_elements = soup.find_all('div', class_="js-order-card")
    if not div_elements:
        div_elements = soup.find_all('div', attrs={'data-csa-c-content-id': re.compile(r'order-card')})
    if not div_elements:
        headers = soup.find_all('div', class_='order-header')
        div_elements = [h.parent for h in headers if h.parent]

    # Fallback para elementos de pedido isolados copiados no DevTools
    if not div_elements:
        if soup.find('div', class_='yohtmlc-product-title') or soup.find('a', href=re.compile(r'/dp/[A-Z0-9]+')):
            div_elements = [soup]

    logging.info(f"Encontrados {len(div_elements)} cards de pedido da Amazon. Processando...")

    for div in div_elements:
        try:
            # 1. Data e Preço do cabeçalho
            data = "Não encontrada"
            preco = "Não encontrado"

            header_items = div.find_all('li', class_='order-header__header-list-item') or div.find_all('div', class_='a-column')
            for item in header_items:
                label = item.find('span', class_='a-color-secondary')
                if label:
                    label_text = label.text.strip().lower()
                    if 'pedido realizado' in label_text or 'data' in label_text:
                        val = item.find('span', class_='aok-break-word') or item.find_all('span', class_='a-color-secondary')[-1]
                        if val and val != label:
                            data = val.text.strip()
                    elif 'total' in label_text:
                        val = item.find('span', class_='aok-break-word') or item.find_all('span', class_='a-color-secondary')[-1]
                        if val and val != label:
                            preco = val.text.strip().replace('\xa0', ' ')

            if data == "Não encontrada" or preco == "Não encontrado":
                container = div.find('div', class_='order-header') or div
                spans = container.find_all('span', class_=['a-size-base', 'a-color-secondary', 'value'])
                for sp in spans:
                    sp_text = sp.text.strip().replace('\xa0', ' ')
                    if preco == "Não encontrado" and re.search(r'R\$\s*[\d\.,]+', sp_text):
                        preco = sp_text
                    elif data == "Não encontrada" and re.search(r'\d{1,2}\s+de\s+[a-zçA-Z]+\s+de\s+\d{4}', sp_text):
                        data = sp_text

            # 2. Produtos do pedido
            product_titles = div.find_all('div', class_='yohtmlc-product-title')
            found_products = []

            if product_titles:
                for p_div in product_titles:
                    a_elem = p_div.find('a')
                    if a_elem and a_elem.text.strip():
                        desc = a_elem.text.strip()
                        href = a_elem.get('href', '')
                        url = "https://www.amazon.com.br" + href if href.startswith('/') else href
                        found_products.append((desc, url))

            if not found_products:
                dp_links = div.find_all('a', href=re.compile(r'/dp/[A-Z0-9]+'))
                seen_urls = set()
                for a_link in dp_links:
                    desc = a_link.text.strip()
                    href = a_link.get('href', '')
                    clean_href = href.split('?')[0] if href else ''
                    if clean_href in seen_urls:
                        continue
                    if desc and len(desc) > 3:
                        seen_urls.add(clean_href)
                        url = "https://www.amazon.com.br" + href if href.startswith('/') else href
                        found_products.append((desc, url))

            if not found_products:
                details_link = div.find('a', href=re.compile(r'/order-details'))
                href = details_link.get('href', '') if details_link else ''
                url = "https://www.amazon.com.br" + href if href.startswith('/') else (href or "Sem link disponível")
                found_products.append(("Item sem descrição", url))

            for desc, url in found_products:
                compras_amazon['descricao'].append(desc)
                compras_amazon['data'].append(data)
                compras_amazon['preco'].append(preco)
                compras_amazon['url_detalhes'].append(url)

        except Exception as e_item:
            logging.warning(f"Erro ao processar pedido individual da Amazon: {e_item}")

    logging.info(f"Compras Amazon extraídas com sucesso: {len(compras_amazon['descricao'])} itens.")
    return pd.DataFrame(compras_amazon)


def parse_amazon(html_string: str) -> pd.DataFrame:
    df = extract_amazon_data(html_string)
    config = {
        "descricao": st.column_config.TextColumn("Descrição", width="medium"),
        "data": st.column_config.TextColumn("Data", width="medium"),
        "preco": st.column_config.TextColumn("Preço", width="small"),
        "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large")
    }
    return st.dataframe(df, column_config=config, row_height=100, hide_index=True)


def extract_mercadolivre_data(html_string: str) -> pd.DataFrame:
    """Extrai os dados de compras do Mercado Livre a partir de HTML usando heurísticas resilientes."""
    compras_ml = {'descricao': [], 'data': [], 'preco': [], 'url_detalhes': []}

    if not html_string or not str(html_string).strip():
        return pd.DataFrame(compras_ml)

    logging.info("Iniciando a extração de dados do Mercado Livre...")
    soup = BeautifulSoup(html_string, 'html.parser')

    # Identificação dos cartões de compra
    div_elements = soup.find_all('div', class_='list-item')
    if not div_elements:
        div_elements = soup.find_all('div', class_=re.compile(r'(?:andes-card|purchase-item|sc-list-item|sc-purchase-item)'))
    if not div_elements:
        links_ml = soup.find_all('a', href=re.compile(r'/MLB-|\/compras\/'))
        seen_parents = set()
        for link in links_ml:
            parent = link.parent
            for _ in range(5):
                if not parent:
                    break
                if parent.name == 'div' and id(parent) not in seen_parents:
                    seen_parents.add(id(parent))
                    div_elements.append(parent)
                    break
                parent = parent.parent

    # Fallback para item isolado copiado no DevTools
    if not div_elements:
        if soup.find('a', class_='list-item__link') or soup.find('a', href=re.compile(r'MLB-|\/compras\/')):
            div_elements = [soup]

    logging.info(f"Encontrados {len(div_elements)} elementos de compra no Mercado Livre. Processando...")

    seen_items = set()
    for div in div_elements:
        try:
            # 1. Título / Descrição
            title_elem = div.find('a', class_=re.compile(r'(?:list-item__link|purchase|item)'))
            if not title_elem:
                title_elem = div.find('a', href=re.compile(r'/MLB-|\/compras\/'))
            if not title_elem:
                title_elem = div.find('span', class_='bf-ui-rich-text') or div.find(['h2', 'h3'])

            descricao = title_elem.text.strip() if title_elem else ""
            if not descricao or len(descricao) < 2:
                continue

            # 2. URL de detalhes
            url = "Sem link disponível"
            if title_elem and title_elem.name == 'a' and title_elem.has_attr('href'):
                url = title_elem['href']
            else:
                a_tag = div.find('a', href=True)
                if a_tag:
                    url = a_tag['href']

            if url.startswith('/'):
                url = "https://www.mercadolivre.com.br" + url

            # Evita duplicatas pelo conjunto (descricao, url)
            dedup_key = (descricao, url)
            if dedup_key in seen_items:
                continue
            seen_items.add(dedup_key)

            # 3. Status e Data
            intro_elem = div.find(['p', 'span', 'div'], class_=re.compile(r'(?:intro|subtitle|status)'))
            intro_txt = intro_elem.text.strip() if intro_elem else ""

            date_elem = div.find(['p', 'span', 'div'], class_=re.compile(r'(?:title|date|time)'))
            date_txt = date_elem.text.strip() if date_elem and date_elem != title_elem else ""

            data = ""
            full_status_text = f"{intro_txt} {date_txt}".lower()
            if "cancelou" in full_status_text or "cancelada" in full_status_text:
                data = "Cancelado"
            elif "entregue" in full_status_text or "chegou" in full_status_text:
                match = re.search(r'Chegou (?:no dia )?(.+)', date_txt, re.IGNORECASE)
                if match:
                    data = match.group(1).strip()
                else:
                    data = date_txt if date_txt else (intro_txt if intro_txt else "Entregue")
            else:
                data = date_txt if date_txt else (intro_txt if intro_txt else "-")

            # 4. Preço (tenta buscar se estiver visível no HTML)
            preco = "-"
            price_elem = div.find(class_=re.compile(r'(?:andes-money-amount|price)'))
            if price_elem:
                preco = price_elem.text.strip()
            else:
                price_match = re.search(r'R\$\s*[\d\.,]+', div.text)
                if price_match:
                    preco = price_match.group(0).strip()

            compras_ml['descricao'].append(descricao)
            compras_ml['data'].append(data)
            compras_ml['preco'].append(preco)
            compras_ml['url_detalhes'].append(url)

        except Exception as e_item:
            logging.warning(f"Erro ao processar item individual do Mercado Livre: {e_item}")

    logging.info(f"Compras Mercado Livre extraídas com sucesso: {len(compras_ml['descricao'])} itens.")
    return pd.DataFrame(compras_ml)


def parse_mercadolivre(html_string: str) -> pd.DataFrame:
    df = extract_mercadolivre_data(html_string)
    config = {
        "descricao": st.column_config.TextColumn("Descrição", width="medium"),
        "data": st.column_config.TextColumn("Data", width="medium"),
        "preco": st.column_config.TextColumn("Preço", width="small"),
        "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large")
    }
    return st.dataframe(df, column_config=config, row_height=100, hide_index=True)