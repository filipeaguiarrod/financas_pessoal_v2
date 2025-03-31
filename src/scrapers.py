from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_shoppe(html_string:str) -> pd.DataFrame:
    compras_shoppe = {'descricao':[],'loja':[], 'preco':[], 'status':[], 'url_detalhes':[]}

    # Parse the HTML content
    soup = BeautifulSoup(html_string, 'html.parser')

    # Lista de compras 
    div_elements = soup.find_all('div', class_='YL_VlX')

    # logging.log the results
    for div in div_elements:

        # Extract the text from each div element
        descricao = div.find('span', class_='DWVWOJ').text
        loja = div.find('div', class_='UDaMW3').text
        preco = div.find('div', class_='t7TQaf').text
        url_detalhes = "https://shopee.com.br" + div.find('a',class_="lXbYsi")['href']
        # Extract the status from the SVG icon
        status = div.find('div', class_="bv3eJE").text

        # Append the extracted data to the dictionary
        
        compras_shoppe['preco'].append(preco)
        compras_shoppe['descricao'].append(descricao)
        compras_shoppe['loja'].append(loja)
        compras_shoppe['url_detalhes'].append(url_detalhes)
        compras_shoppe['status'].append(status)

    logging.info(f"Compras extraidas com sucesso: {compras_shoppe}")
    
    config = {
        "descricao": st.column_config.TextColumn("Descrição", width="medium"),
        "loja": st.column_config.TextColumn("Loja", width="medium"),
        "preco": st.column_config.TextColumn("Preço", width="small"),
        "status": st.column_config.TextColumn("Status", width="small"),
        "url_detalhes": st.column_config.LinkColumn("Link para detalhes", width="large")
    }
        
    # Create a DataFrame from the dictionary
    df = pd.DataFrame(compras_shoppe)
    return st.dataframe(df, column_config=config,row_height=100,hide_index=True)


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