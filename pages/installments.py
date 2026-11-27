import datetime
import logging
import pandas as pd
import streamlit as st
from src import installments, invoice_client
from src.installments_analytics_report import bank_pie, estab_bar, month_bar, different_months_warning
from src.sidebars import Navbar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='Parcelas', layout='wide')

Navbar()

st.title('Parcelas')

BANK_LABELS = {'nubank': 'Nubank', 'xp': 'XP Investimentos'}


def _format_remote_date(iso_str: str | None) -> str:
    if not iso_str:
        return "data indisponível"
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


col_both, col_xp, col_nu = st.columns([2, 1, 1])
with col_both:
    if st.button(
        "📥 Buscar XP + Nubank",
        type="primary",
        use_container_width=True,
        key="btn_inst_fetch_both",
    ):
        with st.spinner("Buscando últimas faturas XP (Drive) e Nubank (Gmail) via backend..."):
            try:
                st.session_state["inst_remote_xp"] = invoice_client.fetch_latest_invoice("xp")
            except invoice_client.InvoiceClientError as fetch_err:
                st.error(f"XP: {fetch_err}")
            try:
                st.session_state["inst_remote_nubank"] = invoice_client.fetch_latest_invoice("nubank")
            except invoice_client.InvoiceClientError as fetch_err:
                st.error(f"Nubank: {fetch_err}")
with col_xp:
    if st.button("📥 Só XP (Drive)", use_container_width=True, key="btn_inst_fetch_xp"):
        try:
            with st.spinner("Buscando última fatura XP no Google Drive..."):
                st.session_state["inst_remote_xp"] = invoice_client.fetch_latest_invoice("xp")
                st.session_state.pop("inst_remote_nubank", None)
        except invoice_client.InvoiceClientError as fetch_err:
            st.error(str(fetch_err))
with col_nu:
    if st.button("📧 Só Nubank (Gmail)", use_container_width=True, key="btn_inst_fetch_nubank"):
        try:
            with st.spinner("Buscando última fatura Nubank no Gmail..."):
                st.session_state["inst_remote_nubank"] = invoice_client.fetch_latest_invoice("nubank")
                st.session_state.pop("inst_remote_xp", None)
        except invoice_client.InvoiceClientError as fetch_err:
            st.error(str(fetch_err))

remote_xp = st.session_state.get("inst_remote_xp")
remote_nu = st.session_state.get("inst_remote_nubank")

if remote_xp is not None or remote_nu is not None:
    col_info, col_clear = st.columns([5, 1])
    with col_info:
        parts = []
        if remote_xp is not None:
            parts.append(f"XP: **{remote_xp.filename}** ({_format_remote_date(remote_xp.date)})")
        if remote_nu is not None:
            parts.append(f"Nubank: **{remote_nu.filename}** ({_format_remote_date(remote_nu.date)})")
        st.caption("Origem automática — " + " | ".join(parts))
    with col_clear:
        if st.button("✖️ Limpar", use_container_width=True, key="btn_inst_clear_remote"):
            st.session_state.pop("inst_remote_xp", None)
            st.session_state.pop("inst_remote_nubank", None)
            st.rerun()

arquivos = st.file_uploader(
    "Ou arraste manualmente as faturas (.csv) — Nubank e/ou XP Investimentos",
    type="csv",
    accept_multiple_files=True,
    key='installments_upload',
)

sources = list(arquivos) if arquivos else [
    r.to_bytes_io() for r in (remote_xp, remote_nu) if r is not None
]

try:
    if sources:
        bank_data = {}
        for f in sources:
            f.seek(0)
            raw = installments.load_csv(f)
            bank = installments.detect_bank(raw)
            label = BANK_LABELS.get(bank, bank)
            invoice_month = installments.extract_invoice_month(raw, bank)
            std_df = installments.standardize(raw, bank)
            if not std_df.empty:
                bank_data[label] = (std_df, invoice_month)

        if not bank_data:
            st.info("Nenhuma compra parcelada encontrada nas faturas carregadas.")
        else:
            all_std = pd.concat([v[0] for v in bank_data.values()], ignore_index=True)
            invoice_month = min(v[1] for v in bank_data.values())
            df = installments.build_crosstable(all_std, invoice_month)
            month_cols = [c for c in df.columns if c not in ('estabelecimento', 'qtd_parcelas_faltantes')]

            st.dataframe(installments.display_crosstable(df), use_container_width=True, height=600)

            st.markdown("## Report analítico de parcelas")

            warning = different_months_warning(bank_data)
            if warning:
                st.warning(warning)

            col1, col2 = st.columns([1, 2])
            with col1:
                st.plotly_chart(bank_pie(bank_data, invoice_month), use_container_width=True)
            with col2:
                st.plotly_chart(estab_bar(df, month_cols), use_container_width=True)

            st.plotly_chart(month_bar(df, month_cols), use_container_width=True)

except Exception as e:
    logging.error(f"Erro ao processar parcelas: {e}")
    st.error(f"Erro ao processar as faturas: {e}")
