import pandas as pd
import json
import logging
import os 
from dotenv import load_dotenv
from datetime import datetime
from dateutil.relativedelta import relativedelta
from google import genai
import openai

# Configuração básica do logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
   dotenv_path = os.path.abspath(".env")
   load_dotenv(dotenv_path=dotenv_path)
except:
   pass

class LLMAgent:

    def __init__(self, df: pd.DataFrame, temperature: float = 0.0, top_p: float = 0.1):
        """
        Initialize the LLM Agent.

        Args:
            df (pd.DataFrame): The DataFrame with the credit card transactions.
            temperature (float, optional): The temperature of the model. Defaults to 0.0.
            top_p (float, optional): The top_p of the model. Defaults to 0.1.
        """
        self.OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
        self.GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
        self.temperature = temperature
        self.top_p = top_p
        self.csv_as_text = df.to_csv(index=False)
        self.prompt = """
            Você vai receber uma tabela em formato CSV que contém a fatura de um cartão de crédito.

            Essa tabela possui três colunas principais:

            date: a data da transação.
            title: a descrição da transação.
            amount: o valor em reais da transação (positivo para cobranças, negativo para estornos).

            Você pode identificar uma compra parcelada através do "title" que indica se aquela compra foi parcelada,
            por exemplo: "Parcela X/Y" ou "X-Y".

            Retorne a seguinte lista de jsons, cada json para uma transação parcelada identificada:

            compras_parceladas:[{
                                "titulo": "",
                                "calculo_parcelas_restantes": "",
                                "valores_parcelas": ""
                                }]

            - titulo: a descrição da transação.
            - calculo_parcelas_restantes: Estruture porém não fala o cálculo final das parcelas restantes, que deve ser
            se Parcela X/Y ou X-Y ou X de Y ou algo parecido, retorne "Y-X+1"
            - valores_parcelas: contém o valor das parcelas. Os valores das parcelas devem ser iguais para uma mesma compra.
            Esse número sempre existe portanto nunca deve retornar para uma compra um valor nulo.
        """ + f'\nArquivo CSV: {self.csv_as_text}'
    

    def call_openai(self,model="gpt-4o-mini") -> json:

        try:
            logging.info(f"Iniciando chamada para o modelo da OpenAI {model}...")
            
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini", 
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": self.prompt}],
                temperature=self.temperature, 
                top_p=self.top_p, 
            )
            
            logging.info("Resposta recebida do modelo.")
            logging.info(response.text)
            
            json_df = json.loads(response.choices[0].message.content)
            
            return json_df
        
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar JSON: {e}")
        except Exception as e:
            logging.error(f"Erro inesperado: {e}")
    
    
    def call_genai(self,model="gemini-2.5-flash") -> json:

        try:
            logging.info(f"Iniciando chamada para o modelo Gemini {model}...")
            
            model = genai.GenerativeModel(model)
            generation_config = genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=self.temperature,
                top_p=self.top_p,
            )
            
            response = model.generate_content(self.prompt, generation_config=generation_config)
            logging.info("Resposta recebida do modelo.")
            logging.info(response.text)

            json_df = json.loads(response.text)
            return json_df
        
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar JSON: {e}")
        except Exception as e:
            logging.error(f"Erro inesperado: {e}")
        
        return {}  # Retorna um dicionário vazio em caso de erro
    
    def llm_parcelas_analyser(self,llm_agent:str)-> pd.DataFrame:

        """
        Recebe o processamento do LLM e retorna o df analítico das parcelas

        llm_agent:str -> 'openai' ou 'genai'

        Expect a json with the following structure:
        Input: compras_parceladas = [{
                        "titulo":"",
                        "calculo_parcelas_restantes":"",
                        "valores_parcelas":""
                     }]
        """

        if llm_agent == 'openai':
            df = pd.json_normalize(self.call_openai()['compras_parceladas'])
        else:
            df = pd.json_normalize(self.call_genai()['compras_parceladas'])

        # Cálculo do que estava em função
        df['calculo_parcelas_restantes'] = df['calculo_parcelas_restantes'].apply(lambda x: list(range(eval(x))))
        # Vamos explodir para ser possível pivotar
        dfe = df.explode(['calculo_parcelas_restantes'], ignore_index=True)
        # Convertendo os números em datas 
        dfe['calculo_parcelas_restantes'] = dfe['calculo_parcelas_restantes'].apply(lambda x: datetime.now().date() + relativedelta(months=x))
        # Pivot e tratamento final:
        dfe['valores_parcelas'] = dfe['valores_parcelas'].astype('float64')
        dfe.rename(columns={'calculo_parcelas_restantes':'meses_restantes'}, inplace=True)
        dfe = dfe.pivot_table(index="titulo", columns='meses_restantes', values="valores_parcelas")
        dfe['Total'] = dfe.sum(axis=1)
        dfe.sort_values(by='Total', ascending=False, inplace=True)
        
        return dfe
    