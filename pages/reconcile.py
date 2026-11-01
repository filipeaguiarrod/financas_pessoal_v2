import streamlit as st
import pandas as pd
import logging
from src.sidebars import Navbar
from src import reconciler, credit_card

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='Reconciliação de Faturas', layout='wide')

Navbar()

# Custom CSS consistente com app.py e layout amplo responsivo
st.markdown("""
<style>
    h1 {
        margin-bottom: 0.5rem !important;
    }
    .main-subtitle {
        color: #666;
        font-size: 1.05rem;
        margin-bottom: 2rem;
    }
    div[data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        margin-bottom: 1.5rem !important;
        padding: 0 !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        white-space: nowrap !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.95rem !important;
        font-weight: 600 !important;
    }
    .step-box {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1.2rem;
        border: 1px solid #e9ecef;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("Reconciliação de Faturas")
st.markdown('<p class="main-subtitle">A <b>Fatura Oficial é a verdade absoluta</b>: sincronize suas categorias já validadas, descarte compras não efetivadas e garanta fechamento com 100% de exatidão.</p>', unsafe_allow_html=True)

def format_currency(val: float) -> str:
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- Entradas Lado a Lado (Passo 1 e Passo 2) ---
col_step1, col_step2 = st.columns(2, gap="large")

with col_step1:
    st.subheader("1. 📋 Base Validada (Google Sheets)")
    st.caption("Transações que você já conferiu e categorizou na sua planilha.")
    sheets_text = st.text_area(
        "Cole aqui as linhas copiadas do Google Sheets:",
        height=190,
        placeholder="Exemplo:\nCombustível\t01/09/2026\tMP *SHELLBOX\t98,65\nRestaurante\t18 set.\tIFD*TMC COMERCIO DE PI\t130,43",
        help="Aceita copiar blocos de colunas do Sheets (tabulado) ou texto vertical."
    )

    df_sheets = None
    if sheets_text.strip():
        try:
            df_sheets = reconciler.parse_sheets_data(sheets_text)
            total_sheets_val = round(float(df_sheets['Valor'].apply(reconciler.parse_amount).sum()), 2) if not df_sheets.empty else 0.0
            st.success(f"✓ **{len(df_sheets)} lançamentos** identificados na Base Sheets ({format_currency(total_sheets_val)})")
        except Exception as e:
            st.error(f"Erro ao interpretar dados do Sheets: {e}")

with col_step2:
    st.subheader("2. 💳 Fatura Fechada (Verdade Absoluta)")
    st.caption("Arquivo oficial da operadora. O valor final e a lista de itens respeitarão estritamente esta fatura.")
    fatura_source_type = st.radio(
        "Origem da fatura nova:",
        ["Upload de Arquivo (CSV Nubank / XP)", "Colar Texto / Tabela"],
        horizontal=True
    )

    df_fatura = None
    if fatura_source_type.startswith("Upload de Arquivo"):
        uploaded_file = st.file_uploader(
            "Arquivo da fatura (.csv — Nubank ou XP Investimentos):",
            type=['csv'],
            key="reconcile_invoice_file"
        )

        if uploaded_file is not None:
            try:
                with st.spinner("Lendo e classificando fatura oficial..."):
                    invoice = credit_card.process_credit_card_invoice(uploaded_file)
                    df_fatura = credit_card.classify_invoice(invoice.df)

                if df_fatura is not None:
                    total_fatura_val = round(float(df_fatura['Valor'].apply(reconciler.parse_amount).sum()), 2) if not df_fatura.empty else 0.0
                    st.success(f"✓ **{len(df_fatura)} transações** da fatura **{invoice.bank_name}** ({format_currency(total_fatura_val)})")
            except Exception as e:
                st.error(f"Erro ao processar fatura: {e}")
    else:
        fatura_text = st.text_area(
            "Cole aqui a tabela da fatura classificada (Categoria, Data, Estabelecimento, Valor):",
            height=190,
            placeholder="Restaurante\t01/09/2026\t99FOOD *SPOLETO\t54,14\nCombustível\t01/09/2026\tMP *SHELLBOX\t98,65"
        )
        if fatura_text.strip():
            try:
                df_fatura = reconciler.parse_sheets_data(fatura_text)
                total_fatura_val = round(float(df_fatura['Valor'].apply(reconciler.parse_amount).sum()), 2) if not df_fatura.empty else 0.0
                st.success(f"✓ **{len(df_fatura)} lançamentos** identificados na fatura colada ({format_currency(total_fatura_val)})")
            except Exception as e:
                st.error(f"Erro ao interpretar fatura colada: {e}")

st.divider()

# --- Ação de Conciliação ---
col_action1, col_action2, col_action3 = st.columns([1, 2, 1])
with col_action2:
    run_reconcile = st.button("🔄 Conciliar Transações (Fatura como Verdade)", type="primary", use_container_width=True)

if run_reconcile:
    if df_fatura is None or df_fatura.empty:
        st.warning("⚠️ Por favor, forneça o arquivo ou texto da **Fatura Fechada no passo 2** (ela é a base de verdade).")
    else:
        try:
            df_reconciled, stats = reconciler.reconcile_transactions(df_sheets, df_fatura)
            st.session_state['reconciled_result'] = df_reconciled
            st.session_state['reconciled_stats'] = stats
            st.toast("Conciliação concluída com sucesso!", icon="✅")
        except Exception as e:
            st.error(f"Erro ao conciliar transações: {e}")

# --- Exibição de Resultados ---
if 'reconciled_result' in st.session_state:
    df_reconciled = st.session_state['reconciled_result']
    stats = st.session_state.get('reconciled_stats', {})

    st.markdown("### 📊 Resultado da Conciliação")

    val_antigo = stats.get('valor_antigo', 0.0)
    val_fatura = stats.get('valor_fatura', 0.0)
    val_novo = stats.get('valor_novo', 0.0)
    removidos_count = stats.get('removidos', 0)
    val_removido = stats.get('valor_removido', 0.0)
    df_descartados = stats.get('df_descartados', pd.DataFrame())

    # Banner informativo principal
    st.success(
        f"✅ **Fatura 100% Conciliada com a Operadora!** Total Consolidado: **{format_currency(val_novo)}** ({stats.get('total', len(df_reconciled))} lançamentos)."
    )

    if removidos_count > 0:
        st.info(
            f"ℹ️ **{removidos_count} transação(ões) da Base Sheets ({format_currency(val_removido)}) foram removidas** por não constarem na fatura oficial fechada (não efetivadas pela operadora). Consulte a aba *Transações Não Efetivadas* abaixo."
        )

    # Painel de métricas sem truncamento
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("💳 Fatura Oficial (Verdade)", format_currency(val_fatura), f"{stats.get('total', 0)} itens")
    m2.metric("📋 Base Anterior (Sheets)", format_currency(val_antigo), f"{len(df_sheets) if df_sheets is not None else 0} itens")
    m3.metric("🏷️ Categorias Mantidas", f"{stats.get('mantidos', 0)}", "validadas no Sheets")
    m4.metric("🆕 Novos da Fatura", f"{stats.get('novos', 0)}", "lançamentos novos")
    m5.metric(
        "🗑️ Não Efetivadas",
        f"{removidos_count}",
        f"-{format_currency(val_removido)}" if removidos_count > 0 else "0",
        delta_color="inverse" if removidos_count > 0 else "off"
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Abas para separar a lista consolidada dos itens descartados
    tab_consolidado, tab_descartados = st.tabs([
        f"📋 Fatura Consolidada Final ({stats.get('total', len(df_reconciled))})",
        f"🗑️ Transações Não Efetivadas / Descartadas ({removidos_count})"
    ])

    with tab_consolidado:
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

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.download_button(
                label="📥 Baixar CSV Conciliado",
                data=df_reconciled.to_csv(index=False, sep=';', encoding='utf-8-sig'),
                file_name="fatura_conciliada.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col_btn2:
            with st.popover("📋 Copiar para Google Sheets", use_container_width=True):
                st.markdown("**Instruções:** Clique na caixa abaixo, selecione tudo (**Ctrl+A**), copie (**Ctrl+C**) e cole diretamente na sua planilha (**Ctrl+V**):")
                st.text_area("TSV Pronto para o Sheets:", value=tsv_output, height=220)

    with tab_descartados:
        if removidos_count > 0 and not df_descartados.empty:
            st.warning(
                f"⚠️ As **{removidos_count} transação(ões)** abaixo estavam na sua base anterior do Sheets, mas **não constam na fatura oficial**. "
                "Elas foram descartadas da base consolidada porque não foram efetivadas pela operadora (ou foram compras canceladas / estornadas)."
            )

            disp_descartados = df_descartados.copy()
            disp_descartados['Valor'] = disp_descartados['Valor'].apply(
                lambda x: f"{x:.2f}".replace('.', ',') if isinstance(x, (int, float)) else str(x)
            )

            st.dataframe(
                disp_descartados[['categoria', 'Data', 'Estabelecimento', 'Valor', '_motivo']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("🎉 Nenhuma transação foi descartada! Todos os lançamentos da base anterior casaram perfeitamente com a fatura oficial.")
