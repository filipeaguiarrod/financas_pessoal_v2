from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import re

def extract_shoppe_data(html_string: str) -> pd.DataFrame:
    """Extrai os dados de compras da Shopee a partir de HTML usando heurísticas resilientes."""
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
                        textos = [t.strip() for t in link_prod.stripped_strings if len(t.strip()) > 10 and not t.strip().startswith('R$')]
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
                total_label = div.find(lambda el: el.name == 'label' and 'total do pedido' in el.text.lower())
                if total_label and total_label.parent:
                    val_el = total_label.parent.find(lambda el: 'R$' in el.text)
                    if val_el:
                        div_preco = val_el
            if not div_preco:
                item_price = div.find('span', class_='Z0dmZq') or div.find('div', class_='V98FFV')
                if item_price:
                    div_preco = item_price

            if div_preco:
                preco_match = re.search(r'R\$\s*[\d\.,]+', div_preco.text)
                preco = preco_match.group(0).replace('\xa0', ' ').strip() if preco_match else div_preco.text.strip()
            else:
                match_total = re.search(r'Total do Pedido:\s*(R\$\s*[\d\.,]+)', div.text, re.IGNORECASE)
                if match_total:
                    preco = match_total.group(1).replace('\xa0', ' ').strip()
                else:
                    preco = "Não encontrado"

            # 4. Status do pedido
            div_status = div.find('div', class_=['tGTmka', 'bv3eJE'])
            if not div_status:
                status_regex = re.compile(r'\b(Preparando|A caminho|Finalizado|Cancelado|Reembolso|A Pagar|Pedido entregue)\b', re.IGNORECASE)
                match_status = status_regex.search(div.text)
                status = match_status.group(0).capitalize() if match_status else "Não encontrado"
            else:
                status = div_status.text.strip()

            # 5. Link para detalhes
            link_detalhes = div.find('a', attrs={'aria-label': 'Ir para Detalhes do Produto'})
            if not link_detalhes:
                link_detalhes = div.find('a', class_="lXbYsi")
            if not link_detalhes:
                link_detalhes = div.find('a', href=re.compile(r'/user/purchase/(?:order|cancellation)/\d+'))

            if link_detalhes and link_detalhes.has_attr('href'):
                href = link_detalhes['href']
                url_detalhes = "https://shopee.com.br" + href if href.startswith('/') else href
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
    div_elements = soup.find_all('div', class_="order-card")
    if not div_elements:
        div_elements = soup.find_all('div', class_="js-order-card")
    if not div_elements:
        div_elements = soup.find_all('div', attrs={'data-csa-c-content-id': 'amzn1.yourorders.order-card'})
    if not div_elements:
        headers = soup.find_all('div', class_='order-header')
        div_elements = [h.parent for h in headers if h.parent]

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


def parse_mercadolivre(html_string: str) -> pd.DataFrame:
    import re
    compras_ml = {'descricao': [], 'data': [], 'preco': [], 'url_detalhes': []}
    soup = BeautifulSoup(html_string, 'html.parser')
    
    div_elements = soup.find_all('div', class_='list-item')
    
    for div in div_elements:
        title_elem = div.find('a', class_='list-item__link')
        descricao = title_elem.text.strip() if title_elem else ""
        if not descricao:
            continue
            
        if descricao in compras_ml['descricao']:
            continue
            
        # Extração simplificada de status e datas
        intro_elem = div.find('p', class_='list-item__intro')
        intro_txt = intro_elem.text.strip() if intro_elem else ""
        
        date_elem_p = div.find('p', class_='list-item__title')
        date_txt = date_elem_p.text.strip() if date_elem_p else ""
        
        # Simplifica: "Chegou no dia 27 de maio" -> "27 de maio" ou "Você cancelou a compra" -> "Cancelado"
        data = ""
        if "cancelou" in intro_txt.lower() or "cancelou" in date_txt.lower():
            data = "Cancelado"
        else:
            match = re.search(r'Chegou (?:no dia )?(.+)', date_txt, re.IGNORECASE)
            if match:
                data = match.group(1)
            else:
                data = date_txt if date_txt else (intro_txt if intro_txt else "-")
                
        # Mercado Livre não fornece preços no histórico de listagem geral
        preco = "-"
        
        url = title_elem['href'] if title_elem and title_elem.has_attr('href') else "Sem link disponível"
        if url.startswith('/'):
            url = "https://www.mercadolivre.com.br" + url
            
        compras_ml['descricao'].append(descricao)
        compras_ml['data'].append(data)
        compras_ml['preco'].append(preco)
        compras_ml['url_detalhes'].append(url)
        
    config = {
        "descricao": st.column_config.TextColumn("Descrição", width="medium"),
        "data": st.column_config.TextColumn("Data", width="medium"),
        "preco": st.column_config.TextColumn("Preço", width="small"),
        "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large")
    }
    df = pd.DataFrame(compras_ml)
    return st.dataframe(df, column_config=config, row_height=100, hide_index=True)