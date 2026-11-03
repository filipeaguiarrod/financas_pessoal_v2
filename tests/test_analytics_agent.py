import pytest
import pandas as pd
from ai_agents.analytics_agent import validate_sql_safety, clean_sql, AnalyticsAgent
from src.postgres import PostgresUploader


def test_clean_sql():
    raw_fence = "```sql\nSELECT * FROM financials.credit_card;\n```"
    assert clean_sql(raw_fence) == "SELECT * FROM financials.credit_card"

    raw_semicolon = "SELECT categoria, valor FROM table;"
    assert clean_sql(raw_semicolon) == "SELECT categoria, valor FROM table"


def test_validate_sql_safety_valid_queries():
    valid_queries = [
        "SELECT * FROM financials.credit_card",
        "SELECT categoria, SUM(valor) FROM financials.credit_card GROUP BY categoria",
        "SELECT data, lancamento, valor FROM financials.checking_account WHERE valor > 100 ORDER BY valor DESC LIMIT 10",
        "WITH monthly AS (SELECT dt_competencia, SUM(valor) AS total FROM financials.credit_card GROUP BY dt_competencia) SELECT * FROM monthly",
        "/* Comentario */ SELECT id, sentenca FROM financials.user_rules -- outro comentario\nWHERE id > 0"
    ]
    for q in valid_queries:
        is_safe, msg = validate_sql_safety(q)
        assert is_safe, f"Deveria ser válida: {q}. Motivo rejeição: {msg}"


def test_validate_sql_safety_rejects_dangerous_queries():
    dangerous_queries = [
        "DROP TABLE financials.credit_card",
        "DELETE FROM financials.checking_account WHERE id = 1",
        "UPDATE financials.user_rules SET categoria = 'X'",
        "INSERT INTO financials.user_rules (sentenca, categoria) VALUES ('a', 'b')",
        "TRUNCATE TABLE financials.credit_card",
        "ALTER TABLE financials.credit_card ADD COLUMN test int",
        "SELECT * FROM financials.credit_card; DROP TABLE financials.credit_card;",
        "SELECT * INTO new_table FROM financials.credit_card",
        "EXEC xp_cmdshell('whoami')",
        "GRANT ALL PRIVILEGES ON DATABASE mydb TO user",
    ]
    for q in dangerous_queries:
        is_safe, msg = validate_sql_safety(q)
        assert not is_safe, f"Deveria ter sido rejeitada como perigosa: {q}"


def test_validate_sql_safety_rejects_empty_and_non_select():
    assert not validate_sql_safety("")[0]
    assert not validate_sql_safety("   ")[0]
    assert not validate_sql_safety("SHOW TABLES")[0]


def test_analytics_agent_json_parsing():
    agent = AnalyticsAgent.__new__(AnalyticsAgent)
    
    # JSON puro
    raw_json = '{"sql_query": "SELECT 1", "explanation": "Teste", "chart": {"type": "bar"}}'
    parsed = agent._parse_json_safely(raw_json)
    assert parsed["sql_query"] == "SELECT 1"
    assert parsed["chart"]["type"] == "bar"

    # JSON com bloco markdown
    raw_markdown = 'Aqui está a consulta:\n```json\n{"sql_query": "SELECT 2", "explanation": "Markdown", "chart": {"type": "line"}}\n```'
    parsed_md = agent._parse_json_safely(raw_markdown)
    assert parsed_md["sql_query"] == "SELECT 2"
    assert parsed_md["chart"]["type"] == "line"


def test_postgres_schema_summary_fallback():
    # Verifica que get_schema_summary retorna texto mesmo sem conexão real ativa
    uploader = PostgresUploader.__new__(PostgresUploader)
    uploader.db_schema = "financials"
    uploader.connection = None
    uploader.engine = None
    
    summary = PostgresUploader.get_schema_summary(uploader)
    assert "financials.checking_account" in summary
    assert "financials.credit_card" in summary
    assert "financials.user_rules" in summary


from unittest.mock import MagicMock
from langchain_core.messages import AIMessage


def test_generate_query_and_viz_with_mock_llm():
    agent = AnalyticsAgent.__new__(AnalyticsAgent)
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content='{"sql_query": "SELECT * FROM financials.credit_card", "explanation": "Ok", "chart": {"type": "bar"}}'
    )
    agent.llm = mock_llm

    res = agent.generate_query_and_viz("quais os maiores gastos?", "schema...")
    assert res["error"] is None
    assert res["is_safe"] is True
    assert res["sql_query"] == "SELECT * FROM financials.credit_card"

    # Verifica que invoke foi chamado com SystemMessage e HumanMessage sem erros de interpolação
    assert mock_llm.invoke.called
    args, _ = mock_llm.invoke.call_args
    messages = args[0]
    assert len(messages) == 2
    assert "FORMATO DE RESPOSTA OBRIGATÓRIO" in messages[0].content
    assert messages[1].content == "quais os maiores gastos?"
