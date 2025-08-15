import pandas as pd
import numpy as np
import logging
import os
import joblib
from . import postgres as ps
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Configuração básica do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
   dotenv_path = os.path.abspath(".env")
   load_dotenv(dotenv_path=dotenv_path)
except:
   pass


def connect_query():

    psql = ps.PostgresUploader()
    engine = psql.connect_postgres()
    connection = engine.connect()

    return connection

def primary_classifier(df,numeric_col='Valor',cat_col='Estabelecimento'): 

    '''
    Classify using database history of transactions
    Input: df, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: df, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64']
    '''

    connection = connect_query()

    if df[numeric_col].dtype != 'float64':
       df[numeric_col] = df[numeric_col].str.replace(',', '.')
       df[numeric_col] = pd.to_numeric(df[numeric_col], errors='coerce',downcast='float')
       df[numeric_col].fillna(0,inplace=True)

    df[numeric_col] = df[numeric_col].apply(lambda x: round(x,2)) # Assegura arredondamento de 2 igual a base

    #print(df)

    valores = '(' + ', '.join(map(str, df[numeric_col].round(2).tolist())) + ')'
    estabelecimentos = '(' + ', '.join([f"'{val}'" for val in df[cat_col].tolist()]) + ')'

    #print(valores,estabelecimentos)

    # Define the query using text() construct with parameter binding
    query = text(f'''SELECT DISTINCT * 
                 FROM financials.credit_card 
                 WHERE TRUE 
                 AND valor IN {valores} 
                 AND lancamento IN {estabelecimentos}
                 ''')
    
    # Perform the query
    result = connection.execute(query)

    # Convert the result to a pandas DataFrame
    labels = pd.DataFrame(result.fetchall(), columns=result.keys())
    labels = labels.drop_duplicates(subset=['lancamento','valor'])

    df_categorias = df.merge(labels,how='left',left_on=[cat_col,numeric_col],right_on=['lancamento','valor'])

    try:
        df_categorias = df_categorias[['categoria','Data','Estabelecimento',numeric_col]]
    except:
        df_categorias[['categoria','Estabelecimento',numeric_col]]
        
    return df_categorias


def secondary_classifier(df_categorias,model_location='external',numeric_col='Valor'):
    
    """
    Classify using model trained with historical labels
    Input: df, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64']
    model_location: 'local' or 'external'
    Output: df, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64']
    """

    df_class_sec = df_categorias.copy()
    # Apply the model's predictions
    condition = pd.isnull(df_class_sec['categoria'])
    
    if model_location == 'local':
        
        # Find the root directory of your project
        script_directory = os.path.dirname(os.path.abspath(__file__))
        root_directory = os.path.dirname(script_directory)
        model_directory = os.path.join(root_directory, 'model')

        # Load the count vectorizer and the logistic classifier
        loaded_cv_path = os.path.join(model_directory, 'count_vectorizer.pkl')
        loaded_model_path = os.path.join(model_directory, 'logistic_classifier.pkl')

        loaded_cv = joblib.load(loaded_cv_path)
        loaded_model = joblib.load(loaded_model_path)
        predictions = loaded_model.predict(loaded_cv.transform(df_class_sec.loc[condition, 'Estabelecimento']))
    
    elif model_location == 'external':

        url = os.environ.get("CLASSIFICATION_MODEL_API")
        logging.info(f"URL do classificador: {url}")

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json"
        }

        payload = {
                    "lancamentos": df_class_sec.loc[condition, 'Estabelecimento'].tolist()
                  }
        response = requests.post(url, json=payload, headers=headers)

        # Verificando a resposta
        if response.status_code == 200:
            result = response.json()
            print("Classificações recebidas:", result["classifications"])
            predictions = result["classifications"]
        else:
            print(f"Erro: {response.status_code}, {response.text}")


    predictions_upper = [pred.upper() for pred in predictions]
    df_class_sec.loc[condition, 'categoria'] = predictions_upper


    df_class_sec[numeric_col] = df_class_sec[numeric_col].astype('string')
    df_class_sec[numeric_col] = df_class_sec[numeric_col].str.replace(',', '.')
    df_class_sec[numeric_col] = pd.to_numeric(df_class_sec[numeric_col], errors='coerce',downcast='float')
    df_class_sec[numeric_col].fillna(0,inplace=True)
    df_class_sec[numeric_col] = df_class_sec[numeric_col].astype('float64')
    

    return df_class_sec

def classify_complete(df ,numeric_col='Valor',cat_col='Estabelecimento'):

    '''
    Classify using database history and model returning both at the end.
    Input: df, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: df, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64']
    '''
    
    logging.info('Classificando através do banco de dados...')
    df = primary_classifier(df = df,numeric_col=numeric_col,cat_col=cat_col)
    logging.info(f"Banco de dados classificado com sucesso. /n {df.sample()}")
    logging.info('Classificando através do modelo...')
    df1 = secondary_classifier(df,numeric_col=numeric_col)
    logging.info("XP classificado com sucesso.")

    return df1