import logging
import pandas as pd
import streamlit as st
from src import installments
from src.installments_analytics_report import bank_pie, estab_bar, month_bar, different_months_warning
from src.sidebars import Navbar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='Parcelas', layout='wide')

Navbar()

st.title('Parcelas')

BANK_LABELS = {'nubank': 'Nubank', 'xp': 'XP Investimentos'}

arquivos = st.file_uploader(
    "Arraste as faturas (.csv) — Nubank e/ou XP Investimentos",
    type="csv",
    accept_multiple_files=True,
    key='installments_upload',
)

try:
    if arquivos:
        bank_data = {}
        for f in arquivos:
            f.seek(0)
            raw = installments.load_csv(f)
            bank = installments.detect_bank(raw)
            label = BANK_LABELS.get(bank, bank)
            invoice_month = installments.extract_invoice_month(raw, bank)
            std_df = installments.standardize(raw, bank)
            bank_data[label] = (std_df, invoice_month)

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
