# Bibliotecas
import json
import pandas as pd
import os
from dotenv import load_dotenv
## SQL 
from sqlalchemy import create_engine, text
from sqlalchemy.types import Text, Date, Float

# Procura arquivo local de env se não espera externo
try:
   dotenv_path = os.path.abspath(".env.local")
   load_dotenv(dotenv_path=dotenv_path)
except:
   pass

class PostgresUploader:
   def __init__(self):
      self.db_user = os.environ.get('DB_USER')
      self.db_password = os.environ.get('DB_PASSWORD')
      self.db_host = os.environ.get('DB_HOST')
      self.db_port = os.environ.get('DB_PORT')
      self.db_name = os.environ.get('DB_NAME')
      self.db_schema = os.environ.get('DB_SCHEMA')
      self.engine = self.connect_postgres()
      self.connection = self.engine.connect()

      
      # Print for debugging purposes
      #clear
      # print("DB_USER:", self.db_user)
      #clear
      # print("DB_PASSWORD:", self.db_password)
      #clear
      # print("DB_HOST:", self.db_host)
      #clear
      # print("DB_PORT:", self.db_port)
      #clear
      # print("DB_NAME:", self.db_name)
      #clear
      # print("DB_SCHEMA:", self.db_schema)

   def query_to_df(self,query):

      query = text(query)

      # Perform the query
      result = self.connection.execute(query)

      df_query = pd.DataFrame(result.fetchall(), columns=result.keys())

      return df_query


   def connect_postgres(self):

      ''' Create a connection with some postgres database
         returning a engine sqlalchemy connection.
      '''

      # Create the connection string to postgres
      conn_string = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
      # Create SQLAlchemy engine
      engine = create_engine(conn_string)

      return engine

   def postgres_upload_table(self, df, table_name, if_exists):
      
      df.columns = ['categoria', 'data', 'lancamento', 'valor']
      df['valor'] = df['valor'].astype('string') 
      df['valor'] = df['valor'].str.replace(',', '.')
      df['valor'] = df['valor'].astype('float64')

      dtype = {
         'categoria': Text(),
         'data': Date(),
         'lancamento': Text(),
         'valor': Float()
      }

      df.to_sql(table_name, 
                  self.engine, 
                  schema = self.db_schema, 
                  if_exists=if_exists,
                  dtype=dtype, 
                  index=False)