import streamlit as st
import pandas as pd
import logging
from src.sidebars import Navbar
from src import reconciler, credit_card

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='Reconciliação de Faturas', layout='centered')

Navbar()

# Custom CSS consistente com app.py (minimalista, sem bordas pesadas)
st.markdown("""
<style>
    h1 {
        margin-bottom: 2rem !important;
    }
    div[data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        margin-bottom: 1.5rem !important;
        padding: 0 !important;
    }
    div[data-testid="stExpander"] details summary p {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
    }
    div[data-testid="stExpander"] details {
        border: none !important;
    }
    .stSubheader p {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        margin-top: 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("Reconciliação de Faturas")
st.caption("Una sua base validada no Google Sheets com faturas novas sem perder correções manuais e preenchendo as categorias pendentes.")

# --- Seção 1: Base Validada do Sheets ---
st.subheader("1. Base Validada (Google Sheets)")
sheets_text = st.text_area(
    "Cole aqui as linhas da sua planilha do Sheets (Ctrl+C no Sheets e Ctrl+V aqui):",
    height=150,
    placeholder="Exemplo:\nCombustível\t01/09/2026\tMP *SHELLBOX\t98,65\n\t18 set.\tIFD*TMC COMERCIO DE PI\t130,43",
    help="Aceita copiar colunas do Sheets (tabulado) ou fluxo vertical de células."
)

df_sheets = None
if sheets_text.strip():
    try:
        df_sheets = reconciler.parse_sheets_data(sheets_text)
        st.success(f"{len(df_sheets)} lançamentos identificados na base do Sheets.")
    except Exception as e:
        st.error(f"Erro ao interpretar dados do Sheets: {e}")

# --- Seção 2: Fatura Nova / Fechada ---
st.subheader("2. Fatura Nova / Fechada")
fatura_source_type = st.radio(
    "Origem da fatura nova:",
    ["Upload de Arquivo (Fatura Nubank / XP)", "Colar Texto / Tabela Classificada"],
    horizontal=True
)

df_fatura = None
if fatura_source_type.startswith("Upload de Arquivo"):
    uploaded_file = st.file_uploader("Arquivo da fatura (.csv — Nubank ou XP Investimentos)", type=['csv'])

    if uploaded_file is not None:
        try:
            with st.spinner("Lendo e classificando fatura..."):
                invoice = credit_card.process_credit_card_invoice(uploaded_file)
                df_fatura = credit_card.classify_invoice(invoice.df)

            if df_fatura is not None:
                st.success(f"{len(df_fatura)} transações carregadas e classificadas da fatura ({invoice.bank_name}).")
        except Exception as e:
            st.error(f"Erro ao processar fatura: {e}")
else:
    fatura_text = st.text_area(
        "Cole aqui a tabela da fatura classificada (colunas: Categoria, Data, Estabelecimento, Valor):",
        height=150,
        placeholder="Restaurante\t01/09/2026\t99FOOD *SPOLETO - SHOPPIN\t54,14\nCombustível\t01/09/2026\tMP *SHELLBOX\t98,65"
    )
    if fatura_text.strip():
        try:
            df_fatura = reconciler.parse_sheets_data(fatura_text)
            st.success(f"{len(df_fatura)} lançamentos identificados na fatura colada.")
        except Exception as e:
            st.error(f"Erro ao interpretar fatura colada: {e}")

st.divider()

# --- Seção 3: Execução da Conciliação ---
if st.button("Conciliar Transações", type="primary", use_container_width=True):
    if df_sheets is None or df_sheets.empty:
        st.warning("Por favor, cole os dados da Base do Sheets no passo 1.")
    elif df_fatura is None or df_fatura.empty:
        st.warning("Por favor, forneça os dados da Fatura Nova no passo 2.")
    else:
        try:
            df_reconciled, stats = reconciler.reconcile_transactions(df_sheets, df_fatura)
            st.session_state['reconciled_result'] = df_reconciled
            st.session_state['reconciled_stats'] = stats
            st.success("Conciliação realizada com sucesso!")
        except Exception as e:
            st.error(f"Erro ao conciliar transações: {e}")

# Exibe resultado da sessão se disponível
if 'reconciled_result' in st.session_state:
    df_reconciled = st.session_state['reconciled_result']
    stats = st.session_state.get('reconciled_stats', {})

    st.subheader("Resultado da Conciliação")

    # Métricas resumidas limpas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Final", stats.get('total', len(df_reconciled)))
    c2.metric("Mantidas (Sheets)", stats.get('mantidos', 0))
    c3.metric("Preenchidas (Fatura)", stats.get('preenchidos', 0))
    c4.metric("Novos Lançamentos", stats.get('novos', 0))

    # Tabela principal formatada
    display_df = df_reconciled.copy()
    display_df['Valor'] = display_df['Valor'].apply(
        lambda x: f"{x:.2f}".replace('.', ',') if isinstance(x, (int, float)) else str(x)
    )

    st.dataframe(
        display_df[['categoria', 'Data', 'Estabelecimento', 'Valor', '_status']],
        use_container_width=True,
        hide_index=True
    )

    # Ações de Exportação
    tsv_output = reconciler.to_sheets_tsv(df_reconciled, include_header=False)

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        st.download_button(
            label="Baixar CSV Conciliado",
            data=df_reconciled.to_csv(index=False, sep=';', encoding='utf-8-sig'),
            file_name="fatura_conciliada.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col_btn2:
        with st.popover("Copiar para Google Sheets", use_container_width=True):
            st.caption("Selecione todo o texto abaixo (Ctrl+A), copie (Ctrl+C) e cole (Ctrl+V) direto no Sheets:")
            st.text_area("TSV Pronto para o Sheets:", value=tsv_output, height=220)
