import os
import logging
from dotenv import load_dotenv
import pandas as pd
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Configuração básica do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
   dotenv_path = os.path.abspath(".env")
   load_dotenv(dotenv_path=dotenv_path)
except:
   pass


class InstallmentAgent:
    def __init__(self, 
                 provider: Literal["openai", "google"] = "google", 
                 model_name: str = "gemini-3-flash-preview"):
        """
        Inicializa o analisador financeiro com o provedor escolhido.
        """
        if provider == "openai":
            self.llm = ChatOpenAI(
                model=model_name, 
                temperature=0, 
                api_key = os.environ.get('OPENAI_API_KEY')
            )
        else:
            self.llm = ChatGoogleGenerativeAI(
                model=model_name, 
                temperature=0, 
                api_key = os.environ.get('GOOGLE_API_KEY')
            )
            
    def prompt_template(self) -> ChatPromptTemplate:

        prompt = ChatPromptTemplate.from_messages([
            ("user", """
        Atue como um analista financeiro especialista em Python e processamento de dados.
        Eu vou te enviar um arquivo JSON de fatura de cartão de crédito e preciso que você gere um relatório de parcelamentos 
        futuros seguindo estas regras estritas:

        Identificação de Parcelas:

        - Procure por padrões de parcelamento nas colunas (ex: '2 de 3', 'Parcela 1/10', ou colunas que indiquem a parcela atual e o total).
        - Podem existir colunas que indiquem o número da parcela. Se sim, utilize essas informações para identificar o número da parcela atual e o total de parcelas.
        Cálculo de Projeção:

        - Considere que a fatura atual é o mês de referência (se o arquivo for de Março/2026, a primeira coluna da tabela deve ser 03/2026).
        - Para cada item parcelado, projete o valor fixo nos meses subsequentes até que a última parcela seja quitada.

        Formatação da Saída:
        Retorne uma tabela em json para posterior conversão via pandas, onde:

        - A primeira coluna deve ser a Descrição (Estabelecimento + indicador da parcela, ex: 'Amazon (4/10)').
        - As colunas seguintes devem ser os meses e anos (MM/AAAA).
        - Adicione uma linha final de TOTAL MENSAL somando todas as parcelas de cada mês.

        Limpeza de Dados:

        - Remova transações que não são parceladas (onde não há 'X de Y' ou 'X/Y').
        - Ignore pagamentos de fatura ou créditos, focando apenas em despesas parceladas.

        {format_instructions}

        DADOS DE ENTRADA:
        {dados_json}
        """)
        ])

        return prompt

    def generate_report_df(self, df: pd.DataFrame) -> pd.DataFrame:
        logging.info("Iniciando geração do relatório...")
        
        # IMPORTANTE: Não limpe as colunas de texto antes deste passo!
        input_json = df.to_json(orient="records", force_ascii=False)

        parser = JsonOutputParser()
        prompt = self.prompt_template().partial(
            format_instructions=parser.get_format_instructions()
        )

        chain = prompt | self.llm | parser
        
        try:
            resultado = chain.invoke({"dados_json": input_json})
            
            # --- Lógica de Desempacotamento Robusto ---
            lista_final = []
            if isinstance(resultado, dict):
                # Se o LLM insistir em encapsular em uma chave 'table' ou similar
                for key in ['table', 'data', 'items', 'report']:
                    if key in resultado and isinstance(resultado[key], list):
                        lista_final = resultado[key]
                        break
                if not lista_final:
                    lista_final = [resultado] # Caso seja um único objeto
            else:
                lista_final = resultado

            if not lista_final or (len(lista_final) == 1 and "TOTAL MENSAL" in str(lista_final[0])):
                logging.warning("Nenhuma parcela encontrada nos dados.")
                return pd.DataFrame()

            return pd.DataFrame(lista_final)
            
        except Exception as e:
            logging.error(f"Erro na execução da Chain: {e}")
            return pd.DataFrame()