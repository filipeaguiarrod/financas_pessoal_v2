import streamlit as st
import requests
import datetime
import os
import pandas as pd
from src.sidebars import Navbar

# Configuração da API
API_URL = "http://192.168.3.4:7555"

st.set_page_config(page_title="Painel de Controle ETL", layout="wide")
Navbar()

# Estilos CSS customizados minimalistas
st.markdown("""
<style>
    .api-meta-badge {
        background-color: #f0f2f6;
        padding: 0.2rem 0.5rem;
        border-radius: 0.2rem;
        font-weight: 500;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("Painel de Controle ETL")
st.caption("Gerenciamento e monitoramento do pipeline de extração, transformação e carga (ETL).")

# Função para testar conexão com a API e buscar metadados
@st.cache_data(ttl=10)
def check_api_connection():
    try:
        response = requests.get(API_URL + "/", timeout=3)
        if response.status_code == 200:
            return True, response.json()
    except Exception:
        pass
    return False, {}

is_online, api_meta = check_api_connection()

if not is_online:
    st.error(f"API de ETL Offline - Não foi possível conectar ao servidor {API_URL}.")
    st.info("Verifique se o servidor local na porta 7555 está ativo e acessível na rede.")
    st.stop()

# Cabeçalho de Metadados da API
col_meta1, col_meta2, col_meta3 = st.columns(3)
with col_meta1:
    st.markdown(f"Serviço: <span class='api-meta-badge'>{api_meta.get('name', 'Finanças ETL API')}</span>", unsafe_allow_html=True)
with col_meta2:
    st.markdown(f"Status: <span class='api-meta-badge' style='color:#2e7d32;'>ONLINE</span>", unsafe_allow_html=True)
with col_meta3:
    st.markdown(f"Versão: <span class='api-meta-badge'>v{api_meta.get('version', '1.0.0')}</span>", unsafe_allow_html=True)

st.divider()

# Layout em duas colunas principais
col_left, col_right = st.columns([1, 1.2], gap="large")

# Coluna Esquerda: GET /latest-dates (Datas Atuais de Carga)
with col_left:
    st.subheader("Últimas Datas de Carga")
    st.write("Dados mais recentes carregados no banco de dados:")
    
    if st.button("Atualizar Datas", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    try:
        dates_resp = requests.get(f"{API_URL}/latest-dates", timeout=5)
        if dates_resp.status_code == 200:
            dates_data = dates_resp.json()
            
            # Conta Corrente
            chk = dates_data.get("checking_account", {})
            st.markdown("### Conta Corrente")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Transação Recente", chk.get("max_data", "N/A"))
            with col2:
                st.metric("Competência Máxima", chk.get("max_dt_competencia", "N/A"))
            
            created_at_chk = chk.get("max_created_at", "N/A")
            if created_at_chk != "N/A":
                try:
                    dt_parsed = datetime.datetime.fromisoformat(created_at_chk.split('.')[0])
                    created_at_chk = dt_parsed.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    pass
            st.caption(f"Última sincronização: `{created_at_chk}`")
            
            st.write("")
            
            # Cartão de Crédito
            cc = dates_data.get("credit_card", {})
            st.markdown("### Cartão de Crédito")
            col3, col4 = st.columns(2)
            with col3:
                st.metric("Transação Recente", cc.get("max_data", "N/A"))
            with col4:
                st.metric("Competência Máxima", cc.get("max_dt_competencia", "N/A"))
                
            created_at_cc = cc.get("max_created_at", "N/A")
            if created_at_cc != "N/A":
                try:
                    dt_parsed = datetime.datetime.fromisoformat(created_at_cc.split('.')[0])
                    created_at_cc = dt_parsed.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    pass
            st.caption(f"Última sincronização: `{created_at_cc}`")
            
        else:
            st.error(f"Falha ao obter datas: Código {dates_resp.status_code}")
    except Exception as e:
        st.error(f"Erro ao conectar com /latest-dates: {e}")

# Coluna Direita: POST /run-etl (Executar Nova Carga)
with col_right:
    st.subheader("Executar Processamento (ETL)")
    st.write("Selecione os parâmetros para iniciar uma nova carga:")
    
    with st.form("etl_form"):
        months = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
        
        # Mês atual como sugestão padrão
        current_month_idx = datetime.datetime.now().month - 1
        selected_month = st.selectbox("Mês de Competência", options=months, index=current_month_idx)
        
        block_options = {
            "both": "Todos os blocos (Google Sheets + Postgres)",
            "gsheets": "Apenas Google Sheets",
            "postgres": "Apenas Banco de Dados Postgres"
        }
        selected_block_key = st.selectbox(
            "Destino dos Blocos", 
            options=list(block_options.keys()), 
            format_func=lambda x: block_options[x]
        )
        
        run_background = st.toggle("Executar em segundo plano", value=True)
        
        submitted = st.form_submit_button("Iniciar Processamento", use_container_width=True, type="primary")
        
        if submitted:
            payload = {
                "mes": selected_month,
                "block": selected_block_key,
                "background": run_background
            }
            
            try:
                etl_resp = requests.post(f"{API_URL}/run-etl", json=payload, timeout=10)
                if etl_resp.status_code == 200:
                    res_data = etl_resp.json()
                    st.success("Processamento de ETL iniciado com sucesso.")
                    st.json(res_data)
                    st.rerun()
                else:
                    st.error(f"Erro {etl_resp.status_code}: {etl_resp.text}")
            except Exception as e:
                st.error(f"Erro ao disparar ETL: {e}")

st.divider()

# Painel Inferior: Monitoramento em tempo real (GET /run-status)
st.subheader("Monitoramento da Última Execução")

@st.fragment(run_every=5)
def render_status_monitor():
    try:
        status_resp = requests.get(f"{API_URL}/run-status", timeout=3)
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            
            status = status_data.get("status", "unknown").lower()
            mes = status_data.get("mes", "N/A")
            block = status_data.get("block", "N/A")
            start_time = status_data.get("start_time", "N/A")
            end_time = status_data.get("end_time", "N/A")
            error = status_data.get("error")
            
            def format_iso_time(iso_str):
                if not iso_str or iso_str == "N/A":
                    return "N/A"
                try:
                    dt = datetime.datetime.fromisoformat(iso_str.split('.')[0])
                    return dt.strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    return iso_str
            
            formatted_start = format_iso_time(start_time)
            formatted_end = format_iso_time(end_time)
            
            # Painel com o status em destaque
            if status == "running":
                st.info(f"Executando: O pipeline de ETL para o mês de '{mes}' está rodando.")
            elif status == "success":
                st.success(f"Concluído: A última execução ({mes}) terminou com sucesso.")
            elif status == "failed":
                st.error(f"Falha: Ocorreu um erro no processamento do mês '{mes}'.")
            elif status == "idle":
                st.warning("Ocioso: Nenhum processamento ativo no momento.")
            else:
                st.info(f"Status Atual: {status.upper()}")
                
            # Exibir detalhes em colunas
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s1:
                st.markdown(f"**Mês Alvo:** `{mes}`")
            with col_s2:
                st.markdown(f"**Bloco:** `{block}`")
            with col_s3:
                st.markdown(f"**Início:** `{formatted_start}`")
            with col_s4:
                st.markdown(f"**Término:** `{formatted_end}`")
                
            if error:
                st.markdown("### Erro Reportado")
                st.error(error)
                
            # Exibir outros atributos dinâmicos caso existam
            extra_fields = {k: v for k, v in status_data.items() if k not in ["status", "mes", "block", "start_time", "end_time", "error"]}
            if extra_fields:
                st.markdown("### Detalhes do Log")
                st.json(extra_fields)
                
            # Indicador de refresh da tela
            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            st.markdown(f"<div style='text-align: right; color: #888; font-size: 0.75rem; font-style: italic; margin-top: 10px;'>Atualização automática: 5s • Check: {now_str}</div>", unsafe_allow_html=True)
            
        else:
            st.error(f"Erro ao obter status: {status_resp.status_code}")
    except Exception as e:
        st.error(f"Erro ao conectar com /run-status: {e}")

render_status_monitor()

# --- Nova Seção: Visualização de Dados Carregados (Banco de Dados) ---
st.divider()
st.subheader("Visualizar Dados Carregados")

from src import postgres as ps

try:
    psql = ps.PostgresUploader()
    db_conn_ok = True
except Exception as e:
    db_conn_ok = False
    db_conn_err = str(e)

if not db_conn_ok:
    st.warning(f"Não foi possível conectar ao banco de dados: {db_conn_err}")
else:
    schema = psql.db_schema
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        table_selected = st.selectbox(
            "Tabela",
            options=["checking_account", "credit_card"],
            format_func=lambda x: "Conta Corrente" if x == "checking_account" else "Cartão de Crédito",
            key="db_table_select"
        )
        
    try:
        comp_query = f"SELECT DISTINCT dt_competencia FROM {schema}.{table_selected} ORDER BY dt_competencia DESC"
        comp_df = psql.query_to_df(comp_query)
        
        if comp_df.empty:
            st.info("Nenhum lançamento encontrado nesta tabela.")
        else:
            comp_dates = comp_df['dt_competencia'].tolist()
            comp_options = [d.strftime("%Y-%m") for d in comp_dates if d is not None]
            
            with col_v2:
                comp_selected = st.selectbox(
                    "Mês de Competência",
                    options=comp_options,
                    key="db_comp_select"
                )
                
            if comp_selected:
                tx_query = f"""
                    SELECT data, categoria, lancamento, valor, created_at, dt_competencia 
                    FROM {schema}.{table_selected} 
                    WHERE dt_competencia = '{comp_selected}-01'
                    ORDER BY data, lancamento
                """
                tx_df = psql.query_to_df(tx_query)
                
                if tx_df.empty:
                    st.info(f"Nenhum registro encontrado para a competência {comp_selected}.")
                else:
                    # Métricas minimalistas simples
                    total_amount = tx_df['valor'].sum()
                    total_txs = len(tx_df)
                    
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        formatted_total = f"R$ {total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        st.metric("Valor total", formatted_total)
                    with col_m2:
                        st.metric("Qtd transações", total_txs)
                        
                    tx_df_display = tx_df.copy()
                    tx_df_display['data'] = pd.to_datetime(tx_df_display['data']).dt.strftime('%d/%m/%Y')
                    tx_df_display['dt_competencia'] = pd.to_datetime(tx_df_display['dt_competencia']).dt.strftime('%d/%m/%Y')
                    tx_df_display['created_at'] = pd.to_datetime(tx_df_display['created_at']).dt.strftime('%d/%m/%Y %H:%M:%S')
                    
                    st.dataframe(
                        tx_df_display, 
                        column_config={
                            "data": st.column_config.TextColumn("data", width="small"),
                            "categoria": st.column_config.TextColumn("categoria", width="medium"),
                            "lancamento": st.column_config.TextColumn("lancamento", width="large"),
                            "valor": st.column_config.NumberColumn("valor", format="%.2f", width="small"),
                            "created_at": st.column_config.TextColumn("created_at", width="medium"),
                            "dt_competencia": st.column_config.TextColumn("dt_competencia", width="small")
                        },
                        use_container_width=True, 
                        hide_index=True
                    )
                    
    except Exception as e:
        st.error(f"Erro ao consultar dados: {e}")
