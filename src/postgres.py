# Bibliotecas
import pandas as pd
import os
from dotenv import load_dotenv
## SQL 
from sqlalchemy import create_engine, text
from sqlalchemy.types import Text, Date, Float, Integer

# Procura arquivo local de env se não espera externo
try:
   dotenv_path = os.path.abspath(".env")
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

   def query_to_df(self, query):
      query = text(query)
      result = self.connection.execute(query)
      df_query = pd.DataFrame(result.fetchall(), columns=result.keys())
      return df_query

   def get_schema_summary(self) -> str:
      """
      Inspeciona o banco de dados e retorna uma descrição detalhada das tabelas
      e colunas disponíveis no schema para subsidiar o prompt da IA.
      """
      schema = self.db_schema or 'financials'
      try:
         query = f"""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = '{schema}'
            ORDER BY table_name, ordinal_position;
         """
         df_cols = self.query_to_df(query)
         if not df_cols.empty:
            summary_lines = [f"Schema ativo: {schema}"]
            for t_name, group in df_cols.groupby('table_name'):
               cols = ", ".join([f"{row['column_name']} ({row['data_type']})" for _, row in group.iterrows()])
               summary_lines.append(f"- Tabela '{schema}.{t_name}': {cols}")
            return "\n".join(summary_lines)
      except Exception:
         pass

      # Fallback com os metadados conhecidos do projeto
      return f"""Schema ativo: {schema}
- Tabela '{schema}.checking_account': data (date), categoria (text), lancamento (text), valor (numeric), created_at (timestamp), dt_competencia (date)
  Descrição: Transações de contas correntes bancárias (Itaú, Bradesco).
- Tabela '{schema}.credit_card': data (date), categoria (text), lancamento (text), valor (numeric), created_at (timestamp), dt_competencia (date)
  Descrição: Faturas e despesas de cartões de crédito (Nubank, XP).
- Tabela '{schema}.user_rules': id (integer), sentenca (text), categoria (text)
  Descrição: Regras de correspondência de categorias configuradas pelo usuário."""

   def connect_postgres(self):
      ''' Create a connection with some postgres database
         returning a engine sqlalchemy connection.
      '''
      conn_string = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
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

   def ensure_rules_table(self):
      self.connection.execute(text(f'''
         CREATE TABLE IF NOT EXISTS {self.db_schema}.user_rules (
            id       SERIAL PRIMARY KEY,
            sentenca TEXT NOT NULL,
            categoria TEXT NOT NULL
         )
      '''))
      self.connection.commit()

   def get_rules(self) -> pd.DataFrame:
      result = self.connection.execute(
         text(f'SELECT id, sentenca, categoria FROM {self.db_schema}.user_rules ORDER BY id')
      )
      return pd.DataFrame(result.fetchall(), columns=result.keys())

   def add_rule(self, sentenca: str, categoria: str):
      self.connection.execute(
         text(f'INSERT INTO {self.db_schema}.user_rules (sentenca, categoria) VALUES (:s, :c)'),
         {'s': sentenca, 'c': categoria}
      )
      self.connection.commit()

   def update_rule(self, rule_id: int, sentenca: str, categoria: str):
      self.connection.execute(
         text(f'UPDATE {self.db_schema}.user_rules SET sentenca=:s, categoria=:c WHERE id=:id'),
         {'s': sentenca, 'c': categoria, 'id': rule_id}
      )
      self.connection.commit()

   def delete_rule(self, rule_id: int):
      self.connection.execute(
         text(f'DELETE FROM {self.db_schema}.user_rules WHERE id=:id'),
         {'id': rule_id}
      )
      self.connection.commit()

   def _schema(self) -> str:
      return self.db_schema or 'financials'

   def ensure_ecommerce_orders_table(self):
      schema = self._schema()
      self.connection.execute(text(f'''
         CREATE TABLE IF NOT EXISTS {schema}.ecommerce_orders (
            id         SERIAL PRIMARY KEY,
            data       DATE NOT NULL,
            origem     TEXT NOT NULL,
            pedido_id  TEXT NOT NULL,
            descricao  TEXT NOT NULL,
            valor      NUMERIC(12, 2) NOT NULL,
            email_id   TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
         )
      '''))
      self.connection.execute(text(f'''
         CREATE INDEX IF NOT EXISTS idx_ecommerce_orders_data
         ON {schema}.ecommerce_orders (data)
      '''))
      self.connection.commit()

   def upsert_ecommerce_orders(self, df: pd.DataFrame) -> int:
      """Insere pedidos de e-commerce de forma idempotente (ignora email_id já existente)."""
      if df is None or df.empty:
         return 0

      self.ensure_ecommerce_orders_table()
      schema = self._schema()
      stmt = text(f'''
         INSERT INTO {schema}.ecommerce_orders (data, origem, pedido_id, descricao, valor, email_id)
         VALUES (:data, :origem, :pedido_id, :descricao, :valor, :email_id)
         ON CONFLICT (email_id) DO NOTHING
      ''')

      records = []
      for _, row in df.iterrows():
         email_id = str(row.get('email_id', '')).strip()
         if not email_id:
            continue
         records.append({
            'data': row['data'],
            'origem': str(row['origem']).strip(),
            'pedido_id': str(row['pedido_id']).strip(),
            'descricao': str(row['descricao']).strip(),
            'valor': round(float(row['valor']), 2),
            'email_id': email_id,
         })

      if not records:
         return 0

      result = self.connection.execute(stmt, records)
      self.connection.commit()
      return int(result.rowcount or 0)

   def get_ecommerce_orders(self, days: int = 120, origem: str | None = None) -> pd.DataFrame:
      """Retorna pedidos de e-commerce armazenados nos últimos `days` dias."""
      self.ensure_ecommerce_orders_table()
      schema = self._schema()
      where_clauses = ["data >= CURRENT_DATE - (:days * INTERVAL '1 day')"]
      params: dict = {'days': int(days)}

      if origem:
         where_clauses.append("LOWER(origem) = LOWER(:origem)")
         params['origem'] = origem.strip()

      query = text(f'''
         SELECT data, origem, pedido_id, descricao, valor, email_id
         FROM {schema}.ecommerce_orders
         WHERE {' AND '.join(where_clauses)}
         ORDER BY data DESC, id DESC
      ''')
      result = self.connection.execute(query, params)
      df_res = pd.DataFrame(result.fetchall(), columns=result.keys())
      if not df_res.empty:
         df_res['valor'] = df_res['valor'].astype(float)
      return df_res
