import pandas as pd
import numpy as np
import os
import joblib
from . import postgres as ps
from sqlalchemy import create_engine, text


def connect_query():

    psql = ps.PostgresUploader()
    engine = psql.connect_postgres()
    connection = engine.connect()

    return connection

def primary_classifier(df): 

    '''
    Recebe um dataframe e retorna uma classificação
    simples, baseado em histórico da base de transações
    é super confiável na classificação.
    '''

    connection = connect_query()

    # recebe df
    df['Valor'] = df['Valor'].str.replace('.', '').str.replace(',', '.').astype(float)
    valores = '(' + ', '.join(map(str, df['Valor'].tolist())) + ')'
    estabelecimentos = '(' + ', '.join([f"'{val}'" for val in df['Estabelecimento'].tolist()]) + ')'

    # Define the query using text() construct with parameter binding
    query = text(f'''SELECT DISTINCT * 
                 FROM transactions.credit_card_transactions 
                 WHERE TRUE 
                 AND valor IN {valores} 
                 AND lancamento IN {estabelecimentos}''')
    
    # Perform the query
    result = connection.execute(query)

    # Convert the result to a pandas DataFrame
    labels = pd.DataFrame(result.fetchall(), columns=result.keys())
    labels = labels.drop_duplicates(subset=['lancamento','valor'])

    df_categorias = df.merge(labels,how='left',left_on=['Estabelecimento','Valor'],right_on=['lancamento','valor'])
    df_categorias = df_categorias[['categoria','Data','Estabelecimento','Valor']]
    
    return df_categorias

def secondary_classifier(df_categorias):
    """
    Here is a model that trains over credit card transactions (history)
    """

    df_class_sec = df_categorias.copy()

    # Find the root directory of your project
    script_directory = os.path.dirname(os.path.abspath(__file__))
    root_directory = os.path.dirname(script_directory)
    model_directory = os.path.join(root_directory, 'model')

    # Load the count vectorizer and the logistic classifier
    loaded_cv_path = os.path.join(model_directory, 'count_vectorizer.pkl')
    loaded_model_path = os.path.join(model_directory, 'logistic_classifier.pkl')

    loaded_cv = joblib.load(loaded_cv_path)
    loaded_model = joblib.load(loaded_model_path)

    # Apply the model's predictions
    condition = pd.isnull(df_class_sec['categoria'])
    predictions = loaded_model.predict(loaded_cv.transform(df_class_sec.loc[condition, 'Estabelecimento']))
    predictions_upper = [pred.upper() for pred in predictions]
    df_class_sec.loc[condition, 'categoria'] = predictions_upper


    df_class_sec['Valor'] = df_class_sec['Valor'].astype('string')
    df_class_sec['Valor'] = df_class_sec['Valor'].str.replace('.',',')
    

    return df_class_sec