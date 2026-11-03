import os
import re
import json
import logging
from typing import Literal, Optional, Tuple, Dict, Any
import pandas as pd
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

try:
    dotenv_path = os.path.abspath(".env")
    load_dotenv(dotenv_path=dotenv_path)
except Exception:
    pass

# Palavras-chave proibidas para garantir que a consulta seja estritamente somente-leitura (Read-Only)
FORBIDDEN_SQL_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "truncate", "create",
    "replace", "grant", "revoke", "vacuum", "comment", "reindex",
    "copy", "call", "execute", "exec", "into", "merge"
}


def clean_sql(query: str) -> str:
    """Limpa blocos de markdown e espaços extras da query SQL."""
    q = query.strip()
    if q.startswith("```"):
        lines = q.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        q = "\n".join(lines).strip()
    # Remove ponto e vírgula final desnecessário
    if q.endswith(";"):
        q = q[:-1].strip()
    return q


def validate_sql_safety(query: str) -> Tuple[bool, str]:
    """
    Valida rigorosamente se a consulta SQL é segura e de somente-leitura (SELECT).
    Retorna (is_safe, message_reason).
    """
    q_clean = clean_sql(query)
    if not q_clean:
        return False, "A consulta SQL está vazia."

    # Remove comentários SQL para análise de palavras proibidas
    q_no_comments = re.sub(r"--.*?(\n|$)", " ", q_clean)
    q_no_comments = re.sub(r"/\*.*?\*/", " ", q_no_comments, flags=re.DOTALL)
    
    # Bloqueia múltiplos comandos concatenados por ponto e vírgula
    # Permite apenas um statement único
    statements = [s.strip() for s in q_no_comments.split(";") if s.strip()]
    if len(statements) > 1:
        return False, "Múltiplas instruções SQL separadas por ';' não são permitidas por motivos de segurança."

    stmt = statements[0]
    tokens = re.findall(r"\b[A-Za-z_]+\b", stmt.lower())

    if not tokens:
        return False, "Nenhum token SQL válido encontrado."

    # Deve iniciar com SELECT ou WITH (para Common Table Expressions que terminam em SELECT)
    first_token = tokens[0]
    if first_token not in ("select", "with"):
        return False, f"Apenas consultas do tipo SELECT ou WITH são permitidas (iniciado com '{first_token.upper()}')."

    # Se iniciou com WITH, deve conter SELECT
    if first_token == "with" and "select" not in tokens:
        return False, "Instrução WITH deve conter uma cláusula SELECT final."

    # Verifica palavras-chave proibidas
    for token in tokens:
        if token in FORBIDDEN_SQL_KEYWORDS:
            return False, f"Operação proibida detectada no comando SQL: '{token.upper()}'."

    return True, "Consulta validada como segura."


class AnalyticsAgent:
    """
    Agente de IA analítico para PostgreSQL alimentado pelo Google Gemini (ou OpenAI).
    Converte perguntas em linguagem natural para consultas SQL seguras (Text-to-SQL),
    sugere visualizações com Plotly e sintetiza insights sobre os dados.
    """

    def __init__(
        self,
        provider: Literal["gemini", "openai"] = "gemini",
        model_name: Optional[str] = None
    ):
        self.provider = provider
        if self.provider == "openai":
            selected_model = model_name or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            self.llm = ChatOpenAI(
                model=selected_model,
                temperature=0,
                api_key=os.environ.get("OPENAI_API_KEY")
            )
        else:
            # Modelo padrão: gemini-2.5-flash ou configurável via GEMINI_MODEL
            selected_model = model_name or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            self.llm = ChatGoogleGenerativeAI(
                model=selected_model,
                temperature=0,
                api_key=os.environ.get("GOOGLE_API_KEY")
            )

    def _get_system_instructions(self, schema_info: str) -> str:
        return f"""Você é um analista de dados e engenheiro de BI sênior especializado em PostgreSQL e finanças pessoais.
Seu objetivo é ler a pergunta do usuário e o esquema do banco de dados para gerar uma consulta SQL precisa, eficiente e segura.

ESQUEMA DO BANCO DE DADOS:
{schema_info}

REGRAS OBRIGATÓRIAS DE SQL:
1. Gere EXCLUSIVAMENTE consultas de leitura (SELECT ou WITH ... SELECT). NUNCA utilize comandos de modificação de dados (INSERT, UPDATE, DELETE, DROP, ALTER, etc).
2. Utilize dialeto PostgreSQL compatível.
3. Tratamento de datas e valores:
   - Os valores monetários estão na coluna 'valor' (tipo numérico/float).
   - A coluna 'data' representa a data exata da transação.
   - A coluna 'dt_competencia' representa a competência do mês/ano (ex: '2026-03-01').
   - Para agrupar por mês, use DATE_TRUNC('month', data) ou dt_competencia.
4. Trate categorias nulas com COALESCE(categoria, 'Sem Categoria') quando relevante.
5. Sempre inclua aliases legíveis nas agregações (ex: total_gasto, qtd_transacoes).
6. Limite consultas grandes sem agregação com LIMIT 200 para preservar performance.

FORMATO DE RESPOSTA OBRIGATÓRIO (JSON PURO):
Retorne SEMPRE e APENAS um objeto JSON válido no seguinte formato:
{{
  "sql_query": "SELECT ...",
  "explanation": "Explicação concisa em português do que a consulta calcula",
  "chart": {{
    "type": "bar", // opções válidas: "bar", "line", "pie", "area", "table"
    "x": "nome_coluna_eixo_x_ou_categoria",
    "y": "nome_coluna_eixo_y_ou_valor",
    "title": "Título sugerido para o gráfico",
    "orientation": "v" // "v" para vertical ou "h" para horizontal
  }},
  "metrics": [
    {{"label": "Total Estimado", "column": "nome_da_coluna_para_somar"}}
  ]
}}
"""

    def generate_query_and_viz(self, user_prompt: str, schema_info: str) -> Dict[str, Any]:
        """
        Recebe a pergunta do usuário e o schema, gerando o SQL e os metadados de visualização Plotly.
        """
        system_prompt = self._get_system_instructions(schema_info)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{user_prompt}")
        ])

        chain = prompt | self.llm
        
        try:
            response = chain.invoke({"user_prompt": user_prompt})
            raw_text = response.content if hasattr(response, "content") else str(response)

            # Extração de JSON (lida com blocos markdown ```json ... ```)
            parsed = self._parse_json_safely(raw_text)

            sql = clean_sql(parsed.get("sql_query", ""))
            parsed["sql_query"] = sql

            # Validação rigorosa de segurança do SQL gerado
            is_safe, reason = validate_sql_safety(sql)
            parsed["is_safe"] = is_safe
            parsed["safety_reason"] = reason

            return parsed
        except Exception as e:
            logging.error(f"Erro ao gerar consulta analítica com IA: {e}")
            return {
                "sql_query": "",
                "explanation": f"Não foi possível processar a pergunta: {e}",
                "chart": {"type": "table"},
                "is_safe": False,
                "safety_reason": str(e)
            }

    def generate_insights(self, user_prompt: str, df: pd.DataFrame) -> str:
        """
        Gera um resumo executivo em linguagem natural com base nos resultados obtidos do DataFrame.
        """
        if df.empty:
            return "Nenhum dado retornado para geração de insights."

        # Limita o envio de linhas para não estourar contexto/tokens
        sample_data = df.head(50).to_dict(orient="records")
        summary_stats = df.describe(include="all").to_dict() if len(df) > 0 else {}

        insights_prompt = ChatPromptTemplate.from_messages([
            ("system", """Você é um especialista em inteligência financeira pessoal.
Analise os dados resultantes da consulta solicitada pelo usuário e forneça um resumo executivo com 3 a 5 pontos-chave (bullet points).
Destaque:
- Maiores despesas ou concentrações de gastos.
- Tendências temporais ou desvios relevantes.
- Dicas práticas e pontos de atenção financeira baseados exclusivamente nos números apresentados.
Seja direto, profissional e conciso. Não invente números fora dos dados fornecidos."""),
            ("user", """Pergunta do Usuário: {user_prompt}

Estatísticas dos Dados:
{stats}

Amostra dos Resultados:
{data}

Gere o resumo de insights:""")
        ])

        chain = insights_prompt | self.llm

        try:
            res = chain.invoke({
                "user_prompt": user_prompt,
                "stats": json.dumps(summary_stats, default=str),
                "data": json.dumps(sample_data, default=str, ensure_ascii=False)
            })
            return res.content if hasattr(res, "content") else str(res)
        except Exception as e:
            logging.error(f"Erro ao gerar insights com IA: {e}")
            return f"Não foi possível gerar insights adicionais: {e}"

    def _parse_json_safely(self, text_content: str) -> Dict[str, Any]:
        """Extrai um dicionário JSON a partir da resposta de texto da LLM."""
        text_content = text_content.strip()
        # Se contiver blocos de código markdown
        if "```" in text_content:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text_content, re.DOTALL)
            if match:
                text_content = match.group(1)
            else:
                # Tenta pegar qualquer trecho entre chaves
                match = re.search(r"(\{.*\})", text_content, re.DOTALL)
                if match:
                    text_content = match.group(1)

        try:
            return json.loads(text_content)
        except json.JSONDecodeError:
            parser = JsonOutputParser()
            try:
                return parser.parse(text_content)
            except Exception:
                return {
                    "sql_query": "",
                    "explanation": text_content,
                    "chart": {"type": "table"}
                }
