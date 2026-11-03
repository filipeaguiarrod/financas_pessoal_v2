import os
import streamlit as st
import pandas as pd
import plotly.express as px
from dotenv import load_dotenv

from src.sidebars import Navbar
from src import postgres as ps
from ai_agents.analytics_agent import AnalyticsAgent, validate_sql_safety, clean_sql

load_dotenv()

st.set_page_config(page_title="Análise de Dados com IA", layout="wide", page_icon="📊")
Navbar()

# Custom CSS minimalista
st.markdown("""
<style>
    .status-badge {
        padding: 0.25rem 0.6rem;
        border-radius: 0.375rem;
        font-weight: 500;
        font-size: 0.85rem;
        display: inline-block;
        margin-right: 0.5rem;
    }
    .badge-ok {
        background-color: #e8f5e9;
        color: #2e7d32;
    }
    .badge-warn {
        background-color: #fff3e0;
        color: #e65100;
    }
    .query-card {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        border-left: 4px solid #1976d2;
    }
    .insight-card {
        background-color: #f0f7ff;
        border-radius: 0.5rem;
        padding: 1.25rem;
        margin-top: 1rem;
        margin-bottom: 1rem;
        border-left: 4px solid #0288d1;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 Análise de Dados com IA")
st.caption("Explore e analise as transações financeiras utilizando linguagem natural, consultas automáticas e gráficos interativos alimentados pelo Google Gemini.")

# --- Verificação de Conexões ---
has_google_key = bool(os.environ.get("GOOGLE_API_KEY"))
db_connected = False
psql = None
db_error_msg = ""

try:
    psql = ps.PostgresUploader()
    # Teste rápido de query
    psql.query_to_df("SELECT 1;")
    db_connected = True
except Exception as e:
    db_error_msg = str(e)

AVAILABLE_MODELS = [
    "gemini-3.8-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3-flash-preview"
]
default_env_model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
if default_env_model not in AVAILABLE_MODELS:
    AVAILABLE_MODELS.insert(0, default_env_model)

col_s1, col_s2, col_s3 = st.columns([1.2, 1, 1.2])
with col_s1:
    if db_connected:
        st.markdown(f"<span class='status-badge badge-ok'>● PostgreSQL: Conectado ({psql.db_schema or 'financials'})</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"<span class='status-badge badge-warn'>▲ PostgreSQL: Desconectado</span>", unsafe_allow_html=True)
with col_s2:
    if has_google_key:
        st.markdown("<span class='status-badge badge-ok'>● Gemini IA: Configurado</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span class='status-badge badge-warn'>▲ Gemini IA: Sem chave GOOGLE_API_KEY</span>", unsafe_allow_html=True)
with col_s3:
    selected_model = st.selectbox(
        "Modelo:",
        options=AVAILABLE_MODELS,
        index=AVAILABLE_MODELS.index(default_env_model) if default_env_model in AVAILABLE_MODELS else 0,
        key="selected_gemini_model"
    )

st.divider()

if not db_connected:
    st.error(f"Não foi possível conectar ao banco de dados: {db_error_msg}")
    st.info("Verifique se as variáveis de ambiente do PostgreSQL (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD) estão preenchidas no `.env`.")
    st.stop()


# --- Funções Auxiliares de Renderização de Gráficos ---
def render_dynamic_chart(df: pd.DataFrame, chart_config: dict, container):
    """
    Renderiza um gráfico interativo com Plotly a partir do DataFrame e configuração.
    Oferece controles para o usuário alterar o tipo de gráfico e eixos.
    """
    if df.empty or len(df.columns) < 1:
        return

    cols = list(df.columns)
    suggested_type = chart_config.get("type", "bar")
    if suggested_type not in ["bar", "line", "pie", "area", "table"]:
        suggested_type = "bar"

    # Auto-identificação de eixos
    suggested_x = chart_config.get("x")
    if suggested_x not in cols:
        suggested_x = cols[0]

    suggested_y = chart_config.get("y")
    if suggested_y not in cols:
        # Pega a primeira coluna numérica ou a segunda coluna
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        suggested_y = numeric_cols[0] if numeric_cols else (cols[1] if len(cols) > 1 else cols[0])

    with container:
        col_c1, col_c2, col_c3 = st.columns([1, 1, 1])
        with col_c1:
            chart_type_options = ["Barras", "Linhas", "Pizza/Donut", "Área", "Ocultar Gráfico"]
            type_map = {"bar": "Barras", "line": "Linhas", "pie": "Pizza/Donut", "area": "Área", "table": "Ocultar Gráfico"}
            default_index = list(type_map.values()).index(type_map.get(suggested_type, "Barras"))
            selected_type = st.selectbox("Tipo de Gráfico", options=chart_type_options, index=default_index, key="viz_chart_type")

        if selected_type == "Ocultar Gráfico":
            return

        with col_c2:
            x_col = st.selectbox("Eixo X / Categoria", options=cols, index=cols.index(suggested_x) if suggested_x in cols else 0, key="viz_x_axis")
        with col_c3:
            numeric_or_all = df.select_dtypes(include=["number"]).columns.tolist() or cols
            y_col = st.selectbox("Eixo Y / Valores", options=numeric_or_all, index=numeric_or_all.index(suggested_y) if suggested_y in numeric_or_all else 0, key="viz_y_axis")

        title = chart_config.get("title", f"{y_col} por {x_col}")

        try:
            fig = None
            if selected_type == "Barras":
                fig = px.bar(df, x=x_col, y=y_col, title=title, text_auto=True)
            elif selected_type == "Linhas":
                fig = px.line(df, x=x_col, y=y_col, title=title, markers=True)
            elif selected_type == "Pizza/Donut":
                fig = px.pie(df, names=x_col, values=y_col, title=title, hole=0.4)
            elif selected_type == "Área":
                fig = px.area(df, x=x_col, y=y_col, title=title)

            if fig:
                fig.update_layout(
                    template="plotly_white",
                    margin=dict(t=50, b=40, l=40, r=40),
                    hovermode="x unified" if selected_type in ["Linhas", "Área"] else "closest"
                )
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Não foi possível renderizar o gráfico com as colunas selecionadas: {e}")


# --- Abas Principais ---
tab_chat, tab_sql, tab_dict = st.tabs([
    "💬 Pergunte aos seus Dados (IA)",
    "🛠️ Editor SQL Direto",
    "📚 Dicionário de Dados"
])

# ==============================================================================
# TAB 1: CONSULTA COM IA
# ==============================================================================
with tab_chat:
    if not has_google_key:
        st.warning("⚠️ Chave `GOOGLE_API_KEY` não configurada. Defina a variável no `.env` para habilitar a geração de queries com IA.")
    
    st.markdown("##### 💡 Sugestões Rápidas de Análise")
    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
    
    selected_quick_prompt = None
    with quick_col1:
        if st.button("💳 Top 10 Gastos Cartão", use_container_width=True):
            selected_quick_prompt = "Quais são as 10 maiores despesas registradas no cartão de crédito? Mostre data, lançamento, categoria e valor."
    with quick_col2:
        if st.button("📊 Gastos por Categoria", use_container_width=True):
            selected_quick_prompt = "Qual o total de gastos agrupado por categoria no cartão de crédito, ordenado do maior para o menor?"
    with quick_col3:
        if st.button("📈 Evolução Mensal", use_container_width=True):
            selected_quick_prompt = "Qual a soma total de gastos por mês (dt_competencia) no cartão de crédito?"
    with quick_col4:
        if st.button("🏦 Conta vs Cartão", use_container_width=True):
            selected_quick_prompt = "Compare a soma total de saídas/gastos da conta corrente com a fatura do cartão de crédito por mês."

    # Campo de Entrada
    default_prompt_val = selected_quick_prompt or st.session_state.get("last_prompt", "")
    with st.form("ai_query_form"):
        user_prompt = st.text_input(
            "Digite sua pergunta sobre as transações:",
            value=default_prompt_val,
            placeholder="Ex: Quanto gastei com Restaurante ou Alimentação nos últimos 3 meses?",
            key="user_query_input"
        )
        col_b1, col_b2 = st.columns([1, 4])
        with col_b1:
            btn_submit = st.form_submit_button("🚀 Analisar com IA", use_container_width=True)
        with col_b2:
            include_insights = st.checkbox("Gerar síntese analítica (insights da IA) sobre o resultado", value=True)

    # Execução
    if btn_submit and user_prompt.strip():
        st.session_state["last_prompt"] = user_prompt
        schema_summary = psql.get_schema_summary()

        with st.spinner(f"🤖 O Gemini ({selected_model}) está analisando o esquema e elaborando a consulta SQL..."):
            agent = AnalyticsAgent(model_name=selected_model)
            ai_response = agent.generate_query_and_viz(user_prompt, schema_summary)

        llm_error = ai_response.get("error")
        sql_query = ai_response.get("sql_query", "")
        explanation = ai_response.get("explanation", "")
        chart_config = ai_response.get("chart", {})
        is_safe = ai_response.get("is_safe", False)
        safety_reason = ai_response.get("safety_reason", "")

        if llm_error:
            st.error(f"❌ **Erro na Chamada com o Modelo de IA**: {llm_error}")
            st.info("Verifique sua conexão ou se a chave GOOGLE_API_KEY no arquivo .env possui saldo e permissão de acesso.")
        elif not is_safe:
            st.error(f"❌ **Consulta Bloqueada por Segurança**: {safety_reason}")
            if sql_query:
                st.code(sql_query, language="sql")
        elif not sql_query:
            st.error("❌ Não foi possível gerar uma consulta SQL válida para a solicitação informada.")
            st.info(explanation)
        else:
            # Mostra explicação amigável
            st.markdown(f"""
            <div class='query-card'>
                <b>Intenção Identificada:</b> {explanation}
            </div>
            """, unsafe_allow_html=True)

            # Execução no PostgreSQL
            try:
                df_result = psql.query_to_df(sql_query)

                if df_result.empty:
                    st.info("ℹ️ A consulta foi executada com sucesso, mas não retornou nenhuma linha.")
                else:
                    st.success(f"Encontrados **{len(df_result)}** registros.")

                    # Métricas de destaque
                    num_cols = df_result.select_dtypes(include=["number"]).columns.tolist()
                    if num_cols:
                        metric_cols = st.columns(min(len(num_cols), 3))
                        for i, col_name in enumerate(num_cols[:3]):
                            col_total = df_result[col_name].sum()
                            with metric_cols[i]:
                                if "valor" in col_name.lower() or "total" in col_name.lower():
                                    st.metric(f"Soma de {col_name}", f"R$ {col_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                                else:
                                    st.metric(f"Total {col_name}", f"{col_total:,.2f}")

                    # Renderização do Gráfico Plotly
                    st.markdown("#### 📈 Visualização Gráfica")
                    chart_container = st.container()
                    render_dynamic_chart(df_result, chart_config, chart_container)

                    # Tabela de Dados
                    st.markdown("#### 📋 Dados Tabulares")
                    st.dataframe(df_result, use_container_width=True)

                    # Botão de Download
                    csv_data = df_result.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="📥 Baixar Resultado em CSV",
                        data=csv_data,
                        file_name="analise_financeira.csv",
                        mime="text/csv"
                    )

                    # Síntese e Insights da IA
                    if include_insights:
                        with st.spinner("🧠 Gerando insights executivos..."):
                            insights_text = agent.generate_insights(user_prompt, df_result)
                            st.markdown(f"""
                            <div class='insight-card'>
                                <h4>💡 Insights e Análise da IA</h4>
                                {insights_text}
                            </div>
                            """, unsafe_allow_html=True)

                # Auditoria da Query SQL
                with st.expander("🔍 Inspecionar SQL Executado"):
                    st.code(sql_query, language="sql")

            except Exception as e:
                st.error(f"Erro ao executar a consulta no banco de dados: {e}")
                with st.expander("Ver SQL com erro"):
                    st.code(sql_query, language="sql")


# ==============================================================================
# TAB 2: EDITOR SQL DIRETO (READ-ONLY)
# ==============================================================================
with tab_sql:
    st.markdown("##### Executar Consulta SQL Personalizada")
    st.caption("Escreva consultas customizadas no PostgreSQL. Por segurança, apenas operações de leitura (`SELECT`) são permitidas.")

    default_custom_sql = f"""SELECT categoria, COUNT(*) as qtd, ROUND(CAST(SUM(valor) AS numeric), 2) as total_gasto
FROM {psql.db_schema or 'financials'}.credit_card
GROUP BY categoria
ORDER BY total_gasto DESC
LIMIT 20;"""

    custom_sql = st.text_area("Comando SQL:", value=default_custom_sql, height=140)
    btn_run_custom = st.button("Executar Consulta", key="btn_run_custom")

    if btn_run_custom and custom_sql.strip():
        is_safe, safety_reason = validate_sql_safety(custom_sql)
        if not is_safe:
            st.error(f"❌ **Consulta Bloqueada**: {safety_reason}")
        else:
            try:
                df_custom = psql.query_to_df(clean_sql(custom_sql))
                if df_custom.empty:
                    st.info("A consulta não retornou resultados.")
                else:
                    st.success(f"Retornadas **{len(df_custom)}** linhas.")
                    chart_container_custom = st.container()
                    render_dynamic_chart(df_custom, {"type": "bar"}, chart_container_custom)
                    st.dataframe(df_custom, use_container_width=True)
            except Exception as e:
                st.error(f"Erro na execução da consulta: {e}")


# ==============================================================================
# TAB 3: DICIONÁRIO DE DADOS
# ==============================================================================
with tab_dict:
    st.markdown("##### 📚 Estrutura das Tabelas do Banco")
    st.caption("Visão geral das tabelas e campos disponíveis para exploração e consultas.")

    schema_name = psql.db_schema or 'financials'
    try:
        dict_query = f"""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = '{schema_name}'
            ORDER BY table_name, ordinal_position;
        """
        dict_df = psql.query_to_df(dict_query)
        if not dict_df.empty:
            for t_name, grp in dict_df.groupby("table_name"):
                with st.expander(f"📁 Tabela: `{schema_name}.{t_name}` ({len(grp)} colunas)", expanded=True):
                    display_cols = grp[["column_name", "data_type", "is_nullable"]].rename(
                        columns={"column_name": "Coluna", "data_type": "Tipo de Dado", "is_nullable": "Permite Nulo"}
                    )
                    st.dataframe(display_cols, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma metainformação encontrada via information_schema.")
    except Exception as e:
        st.warning(f"Não foi possível carregar o dicionário dinâmico: {e}")
        st.markdown(f"""
        **Esquema Padrão:**
        * `{schema_name}.credit_card`: `data`, `categoria`, `lancamento`, `valor`, `created_at`, `dt_competencia`
        * `{schema_name}.checking_account`: `data`, `categoria`, `lancamento`, `valor`, `created_at`, `dt_competencia`
        * `{schema_name}.user_rules`: `id`, `sentenca`, `categoria`
        """)
