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
                 FROM transactions.credit_card_transactions 
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

def secondary_classifier(df_categorias,numeric_col='Valor'):
    
    """
    Classify using model trained with historical labels
    Input: df, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64']
    Output: df, ['categoria', 'Data', 'Estabelecimento', 'Valor'], types=['object','object','object','float64']
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
    
    df = primary_classifier(df = df,numeric_col=numeric_col,cat_col=cat_col)
    df1 = secondary_classifier(df,numeric_col=numeric_col)

    return df1