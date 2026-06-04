from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_shoppe(html_string: str) -> pd.DataFrame:
    compras_shoppe = {'descricao': [], 'loja': [], 'preco': [], 'status': [], 'url_detalhes': []}

    logging.info("Iniciando a extração de dados do Shopee...")

    # Parse the HTML content
    soup = BeautifulSoup(html_string, 'html.parser')

    logging.info("HTML do Shopee parseado com sucesso. Extraindo informações...")

    # Lista de compras 
    div_elements = soup.find_all('div', class_='YL_VlX')

    logging.info(f"Encontrados {len(div_elements)} elementos de compra no Shopee. Processando cada um...")

    # Extrai os resultados
    for div in div_elements:
        
        # Extrações seguras: verifica se a tag existe antes de extrair .text
        span_desc = div.find('span', class_='DWVWOJ')
        descricao = span_desc.text.strip() if span_desc else "Não encontrada"
        
        div_loja = div.find('div', class_='UDaMW3')
        loja = div_loja.text.strip() if div_loja else "Não encontrada"
        
        div_preco = div.find('div', class_='t7TQaf')
        preco = div_preco.text.strip() if div_preco else "Não encontrado"
        
        div_status = div.find('div', class_="bv3eJE")
        status = div_status.text.strip() if div_status else "Não encontrado"
        
        # Correção da URL: busca o novo padrão ou faz fallback para o antigo
        link_detalhes = div.find('a', attrs={'aria-label': 'Ir para Detalhes do Produto'})
        if not link_detalhes:
            # Caso não ache pelo aria-label, tenta pela classe antiga
            link_detalhes = div.find('a', class_="lXbYsi")
            
        if link_detalhes and link_detalhes.has_attr('href'):
            url_detalhes = "https://shopee.com.br" + link_detalhes['href']
        else:
            url_detalhes = "Sem link disponível"

        # Adiciona os dados ao dicionário
        compras_shoppe['descricao'].append(descricao)
        compras_shoppe['loja'].append(loja)
        compras_shoppe['preco'].append(preco)
        compras_shoppe['status'].append(status)
        compras_shoppe['url_detalhes'].append(url_detalhes)

    logging.info(f"Compras extraidas com sucesso: {len(compras_shoppe['descricao'])} itens.")
    
    config = {
        "descricao": st.column_config.TextColumn("Descrição", width="medium"),
        "loja": st.column_config.TextColumn("Loja", width="medium"),
        "preco": st.column_config.TextColumn("Preço", width="small"),
        "status": st.column_config.TextColumn("Status", width="small"),
        "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large")
    }
        
    # Create a DataFrame from the dictionary
    df = pd.DataFrame(compras_shoppe)
    return st.dataframe(df, column_config=config, row_height=100, hide_index=True)


def parse_amazon(html_string:str) -> pd.DataFrame:
        
    compras_amazon = {'descricao':[], 'data':[], 'preco':[], 'url_detalhes':[]}
    # Parse the HTML content
    soup = BeautifulSoup(html_string, 'html.parser')

    # Find all div elements with class "YL_VlX"
    div_elements = soup.find_all('div', class_="order-card js-order-card")

    # Print the results
    for div in div_elements:

        try:
            data, preco = div.find_all('span',class_='a-size-base a-color-secondary aok-break-word')
            data,preco = data.text, preco.text.replace('\xa0',' ')
        except:
            data,preco,_ = div.find_all('span',class_='a-color-secondary value')
            data,preco = data.text.strip(),preco.text.strip()

        
        url,_,_,descricao = div.find_all('a',class_="a-link-normal")[:4]
        url,descricao = "https://www.amazon.com.br"+url['href'],descricao.text.strip()

        # Append dicionario:
        compras_amazon['data'].append(data)
        compras_amazon['preco'].append(preco)
        compras_amazon['url_detalhes'].append(url)
        compras_amazon['descricao'].append(descricao)

    logging.info(f"Compras extraidas com sucesso: {compras_amazon}")

    config = {
    "descricao": st.column_config.TextColumn("Descrição", width="medium"),
    "data": st.column_config.TextColumn("Data", width="medium"),
    "preco": st.column_config.TextColumn("Preço", width="small"),
    "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large")
            }
    df = pd.DataFrame(compras_amazon)

    return st.dataframe(df, column_config=config,row_height=100,hide_index=True)


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