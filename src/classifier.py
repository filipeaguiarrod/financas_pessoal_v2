import pandas as pd
import numpy as np
import logging
import os
import re
import unicodedata
import joblib
from . import postgres as ps
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, bindparam

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
   dotenv_path = os.path.abspath(".env")
   load_dotenv(dotenv_path=dotenv_path)
except:
   pass


def _normalize(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]', '', text)
    return text


def connect_query():
    psql = ps.PostgresUploader()
    engine = psql.connect_postgres()
    connection = engine.connect()
    return connection


def rules_classifier(df, cat_col='Estabelecimento'):
    '''
    Classify using user-defined hard rules stored in the database.
    Only fills NaN categories. Category case is preserved as-is (not uppercased).
    Tracks source as "rules" when _source column is present.
    '''
    df = df.copy()
    psql = ps.PostgresUploader()
    rules = psql.get_rules()

    if rules.empty:
        return df

    rules['_norm'] = rules['sentenca'].apply(_normalize)
    condition = pd.isnull(df['categoria'])

    for idx in df[condition].index:
        nome_norm = _normalize(str(df.at[idx, cat_col]))
        for _, rule in rules.iterrows():
            if rule['_norm'] in nome_norm:
                df.at[idx, 'categoria'] = rule['categoria']
                if '_source' in df.columns:
                    df.at[idx, '_source'] = 'rules'
                break

    return df


def primary_classifier(df, numeric_col='Valor', cat_col='Estabelecimento'):
    '''
    Classify using database history of transactions.
    Only fills NaN categories. Tracks source as "historico" when _source column is present.
    Input: df, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: df with 'categoria' filled for matched rows
    '''
    _via_pipeline = '_source' in df.columns

    df = df.copy()
    connection = connect_query()

    if df[numeric_col].dtype != 'float64':
        df[numeric_col] = df[numeric_col].str.replace(',', '.')
        df[numeric_col] = pd.to_numeric(df[numeric_col], errors='coerce', downcast='float')
        df[numeric_col].fillna(0, inplace=True)
    df[numeric_col] = df[numeric_col].apply(lambda x: round(x, 2))
    df['valor_round'] = df[numeric_col].round(0)

    if 'categoria' not in df.columns:
        df['categoria'] = None

    condition = pd.isnull(df['categoria'])

    if condition.any():
        unclassified = df.loc[condition]

        query = text('''SELECT DISTINCT
                            categoria,
                            lancamento,
                            ROUND(valor, 0) AS valor_round
                        FROM financials.credit_card
                        WHERE ROUND(valor, 0) IN :valores
                        AND lancamento IN :estabelecimentos
                    ''').bindparams(
            bindparam('valores', expanding=True),
            bindparam('estabelecimentos', expanding=True),
        )
        result = connection.execute(query, {
            'valores': unclassified['valor_round'].tolist(),
            'estabelecimentos': unclassified[cat_col].tolist(),
        })
        labels = pd.DataFrame(result.fetchall(), columns=result.keys())
        labels = labels.drop_duplicates(subset=['lancamento', 'valor_round'])

        merged = unclassified[[cat_col, 'valor_round']].merge(
            labels, how='left',
            left_on=[cat_col, 'valor_round'],
            right_on=['lancamento', 'valor_round'],
        )
        merged.index = unclassified.index

        found = ~pd.isnull(merged['categoria'])
        df.loc[merged.index[found], 'categoria'] = merged.loc[found, 'categoria'].values
        if _via_pipeline:
            df.loc[merged.index[found], '_source'] = 'historico'

    if _via_pipeline:
        return df

    # Standalone call: return with expected columns only
    try:
        return df[['categoria', 'Data', cat_col, numeric_col]]
    except KeyError:
        return df[['categoria', cat_col, numeric_col]]


def secondary_classifier(df_categorias, model_location='external', numeric_col='Valor'):
    """
    Classify using model trained with historical labels.
    Only fills NaN categories. Tracks source as "modelo" when _source column is present.
    Categories are uppercased (existing behavior).
    """
    df_class_sec = df_categorias.copy()
    condition = pd.isnull(df_class_sec['categoria'])

    if condition.any():
        if model_location == 'local':
            script_directory = os.path.dirname(os.path.abspath(__file__))
            root_directory = os.path.dirname(script_directory)
            model_directory = os.path.join(root_directory, 'model')

            loaded_cv = joblib.load(os.path.join(model_directory, 'count_vectorizer.pkl'))
            loaded_model = joblib.load(os.path.join(model_directory, 'logistic_classifier.pkl'))
            predictions = loaded_model.predict(loaded_cv.transform(df_class_sec.loc[condition, 'Estabelecimento']))

        elif model_location == 'external':
            url = os.environ.get("CLASSIFICATION_MODEL_API")
            logging.info(f"URL do classificador: {url}")
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            payload = {"lancamentos": df_class_sec.loc[condition, 'Estabelecimento'].tolist()}
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                predictions = result["classifications"]
            else:
                print(f"Erro: {response.status_code}, {response.text}")

        predictions_upper = [pred.upper() for pred in predictions]
        df_class_sec.loc[condition, 'categoria'] = predictions_upper
        if '_source' in df_class_sec.columns:
            df_class_sec.loc[condition, '_source'] = 'modelo'

    df_class_sec[numeric_col] = df_class_sec[numeric_col].astype('string')
    df_class_sec[numeric_col] = df_class_sec[numeric_col].str.replace(',', '.')
    df_class_sec[numeric_col] = pd.to_numeric(df_class_sec[numeric_col], errors='coerce', downcast='float')
    df_class_sec[numeric_col].fillna(0, inplace=True)
    df_class_sec[numeric_col] = df_class_sec[numeric_col].astype('float64')
    df_class_sec[numeric_col] = df_class_sec[numeric_col].round(2)

    return df_class_sec


def classify_complete(df, numeric_col='Valor', cat_col='Estabelecimento'):
    '''
    Full classification pipeline: rules → historical DB → ML model.
    Input: df, cols = ['Data', 'Estabelecimento', 'Valor'], types = 'object'
    Output: df, ['categoria', '_source', 'Data', 'Estabelecimento', 'Valor']
    '''
    df = df.copy()
    df['categoria'] = None
    df['_source'] = None

    logging.info('Classificando através das regras do usuário...')
    df = rules_classifier(df, cat_col=cat_col)
    logging.info('Classificando através do banco de dados...')
    df = primary_classifier(df, numeric_col=numeric_col, cat_col=cat_col)
    logging.info('Classificando através do modelo...')
    df = secondary_classifier(df, numeric_col=numeric_col)
    logging.info('Classificado com sucesso.')

    df = df.drop(columns=['valor_round'], errors='ignore')

    try:
        return df[['categoria', '_source', 'Data', cat_col, numeric_col]]
    except KeyError:
        return df[['categoria', '_source', cat_col, numeric_col]]
