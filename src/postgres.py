# Bibliotecas
import json
import pandas as pd
import os
## SQL 
from sqlalchemy import create_engine, text
from sqlalchemy.types import Text, Date, Float


class PostgresUploader:
   def __init__(self):
      self.json_settings_str = os.environ.get("DB_SETTINGS")
      self.db_settings = self.load_db_settings()
      self.engine = self.connect_postgres()
      self.connection = self.engine.connect()

   
   def load_db_settings(self):
       
      db_settings = json.loads(self.json_settings_str)

      return db_settings

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
      conn_string = f"postgresql://{self.db_settings['db_user']}:{self.db_settings['db_password']}@{self.db_settings['db_host']}:{self.db_settings['db_port']}/{self.db_settings['db_name']}"
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
                  schema = self.db_settings['db_schema'], 
                  if_exists=if_exists,
                  dtype=dtype, 
                  index=False)