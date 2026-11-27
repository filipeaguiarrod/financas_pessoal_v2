import datetime
import logging
import streamlit as st
import pandas as pd
from src import credit_card, checking_account, installments, ecommerce_enrichment, invoice_client, postgres, reconciler
from src.sidebars import Navbar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

st.set_page_config(page_title='easy-financ-export', layout='centered')

Navbar()

# Custom CSS for a minimalist, clean, larger layout without borders/dividers
st.markdown("""
<style>
    /* Aumenta a distância abaixo do título principal (h1) */
    h1 {
        margin-bottom: 3.5rem !important;
    }
    /* Remove expander borders, shadows, and default background */
    div[data-testid="stExpander"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        margin-bottom: 2rem !important;
        padding: 0 !important;
    }
    /* Make expander titles larger and bolder */
    div[data-testid="stExpander"] details summary p {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    /* Remove default details outline/border */
    div[data-testid="stExpander"] details {
        border: none !important;
    }
    /* Clean up headers inside the expanders */
    .stSubheader p {
        font-size: 1.4rem !important;
        font-weight: 600 !important;
        margin-top: 1.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("Extratos & Faturas")


def classification_legend(show_modelo=True):
    items = [
        '<span style="color:gray">■ Regras</span>',
        '<span style="color:#1565C0">■ Histórico</span>',
    ]
    if show_modelo:
        items.append('<span style="color:#E65100">■ Modelo</span>')
    st.markdown('<small>' + '&nbsp;&nbsp;'.join(items) + '</small>', unsafe_allow_html=True)


def _format_remote_date(iso_str: str | None) -> str:
    if not iso_str:
        return "data indisponível"
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str


def _format_brl(val: float) -> str:
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


# --- Drill Down: Cartão de Crédito ---
with st.expander("💳 Cartão de Crédito", expanded=False):
    try:
        cc_file = st.file_uploader(
            "Jogue aqui o arquivo da fatura (.csv — Nubank ou XP Investimentos)",
            type=['csv'],
            key='cc_invoice_uploader'
        )

        col_btn_xp, col_btn_nu = st.columns(2)
        with col_btn_xp:
            if st.button("📥 Buscar última fatura XP (Drive)", use_container_width=True, key="btn_fetch_xp_invoice"):
                try:
                    with st.spinner("Buscando última fatura XP no Google Drive via backend..."):
                        st.session_state["cc_remote_invoice"] = invoice_client.fetch_latest_invoice("xp")
                except invoice_client.InvoiceClientError as fetch_err:
                    st.error(str(fetch_err))
        with col_btn_nu:
            if st.button("📧 Buscar última fatura Nubank (Gmail)", use_container_width=True, key="btn_fetch_nubank_invoice"):
                try:
                    with st.spinner("Buscando última fatura Nubank no Gmail via backend..."):
                        st.session_state["cc_remote_invoice"] = invoice_client.fetch_latest_invoice("nubank")
                except invoice_client.InvoiceClientError as fetch_err:
                    st.error(str(fetch_err))

        remote_invoice = st.session_state.get("cc_remote_invoice")
        cc_source = None

        if cc_file is not None:
            cc_source = cc_file
        elif remote_invoice is not None:
            source_label = "Google Drive" if remote_invoice.source == "google_drive" else "Gmail"
            col_info, col_clear = st.columns([5, 1])
            with col_info:
                st.caption(
                    f"Origem automática ({source_label}): **{remote_invoice.filename}** "
                    f"({_format_remote_date(remote_invoice.date)})"
                )
            with col_clear:
                if st.button("✖️ Limpar", use_container_width=True, key="btn_clear_remote_invoice"):
                    st.session_state.pop("cc_remote_invoice", None)
                    st.rerun()
            cc_source = remote_invoice.to_bytes_io()

        if cc_source is not None:
            invoice = credit_card.process_credit_card_invoice(cc_source)
            logging.info(f"Fatura processada: banco={invoice.bank}, shape={invoice.df.shape}")

            st.success(f"Fatura identificada: **{invoice.bank_name}**")
            st.metric("Valor Parcial", round(invoice.total_amount, 2))

            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                classify = st.toggle("*Classificar transações ?*", value=False, key='cc_classifier')
            with col_t2:
                enrich_ecommerce = st.toggle("*Enriquecer ecommerce ?*", value=False, key='cc_enrich_ecommerce')
            with col_t3:
                show_installments = False
                if invoice.has_installments:
                    show_installments = st.toggle("Analisar parcelas", key='cc_installments')

            base_df = credit_card.classify_invoice(invoice.df) if classify else invoice.df.copy()
            active_invoice_df = base_df.copy()

            if enrich_ecommerce:
                psql = postgres.PostgresUploader()
                orders_df = psql.get_ecommerce_orders(days=120)
                cfg = psql.get_ecommerce_matching_config()
                no_reclass = (lambda d: pd.DataFrame({"categoria": [None] * len(d), "_source": [None] * len(d)}))
                enriched_df, ambiguous_map = ecommerce_enrichment.enrich_amazon_transactions(
                    base_df,
                    orders_df,
                    days_before=cfg["days_before"],
                    days_after=cfg["days_after"],
                    value_tolerance=cfg["value_tolerance"],
                    installment_tolerance=cfg["installment_tolerance"],
                    store_patterns=cfg["store_patterns"],
                    raw_df=invoice.raw_df,
                    classify_fn=credit_card.classify_invoice if classify else no_reclass,
                )

                if ambiguous_map:
                    st.caption("Casos ambíguos encontrados — selecione o produto correspondente:")
                    for row_idx, candidates in ambiguous_map.items():
                        orig_estab = enriched_df.at[row_idx, "Estabelecimento"]
                        orig_val = enriched_df.at[row_idx, "Valor"]
                        orig_dt = enriched_df.at[row_idx, "Data"]
                        options = ["-- Manter original --"] + [
                            f"{c['descricao']} (Pedido {c['pedido_id']} | {c['data']} | R$ {c['valor']:.2f})"
                            for c in candidates
                        ]
                        choice = st.selectbox(
                            f"{orig_dt} | {orig_estab} | R$ {orig_val:.2f}",
                            options=options,
                            key=f"cc_ambig_{row_idx}",
                        )
                        if choice != "-- Manter original --":
                            chosen = candidates[options.index(choice) - 1]
                            chosen_origin = chosen.get("origem") or ecommerce_enrichment.detect_ecommerce_origin(orig_estab) or "Amazon"
                            enriched_df.at[row_idx, "Estabelecimento"] = ecommerce_enrichment.format_enriched_establishment(
                                chosen_origin, chosen["descricao"]
                            )
                            enriched_df.at[row_idx, "match_status"] = "matched_manual"
                            if classify:
                                reclass = credit_card.classify_invoice(pd.DataFrame([{
                                    "Data": orig_dt,
                                    "Estabelecimento": chosen["descricao"],
                                    "Valor": orig_val,
                                }]))
                                enriched_df.at[row_idx, "categoria"] = reclass.at[0, "categoria"]
                                if "_source" in reclass.columns:
                                    enriched_df.at[row_idx, "_source"] = reclass.at[0, "_source"]

                st.markdown(
                    '<small>'
                    '<span style="color:#2E7D32">■ Enriquecido</span>&nbsp;&nbsp;'
                    '<span style="color:#E65100">■ Ambíguo / Modelo</span>&nbsp;&nbsp;'
                    '<span style="color:#C62828">■ Sem Match</span>&nbsp;&nbsp;|&nbsp;&nbsp;'
                    '<span style="color:gray">■ Regras</span>&nbsp;&nbsp;'
                    '<span style="color:#1565C0">■ Histórico</span>'
                    '</small>',
                    unsafe_allow_html=True,
                )
                cols_show = (
                    ["categoria", "_source", "match_status", "Data", "Estabelecimento", "Valor"]
                    if classify
                    else ["match_status", "Data", "Estabelecimento", "Valor"]
                )
                disp_df = credit_card.format_display_df(enriched_df[cols_show])
                st.dataframe(ecommerce_enrichment.style_enriched(disp_df), use_container_width=True)
                active_invoice_df = enriched_df.copy()
            elif classify:
                classification_legend()
                disp_df = credit_card.format_display_df(base_df)
                st.dataframe(credit_card.style_classified(disp_df), use_container_width=True)
            else:
                disp_df = credit_card.format_display_df(base_df)
                st.dataframe(disp_df, use_container_width=True)

            if show_installments:
                st.dataframe(
                    installments.display_crosstable(installments.pipeline_from_df(invoice.raw_df)),
                    use_container_width=True,
                    height=600 if invoice.bank == 'xp' else 'content'
                )

            # --- Conciliação Integrada com Google Sheets ---
            st.divider()
            st.subheader("🔄 Conciliar com Google Sheets")

            invoice_sig = f"{invoice.bank}:{len(invoice.df)}:{invoice.total_amount}"
            if st.session_state.get("cc_reconcile_sig") != invoice_sig:
                st.session_state.pop("cc_reconcile_state", None)
                st.session_state["cc_reconcile_sig"] = invoice_sig

            default_range = invoice_client.DEFAULT_SHEET_RANGES.get(invoice.bank, "G4:J98")
            current_month_idx = datetime.datetime.now().month - 1

            col_rec_m, col_rec_btn = st.columns([1.2, 1.8], vertical_alignment="bottom")
            with col_rec_m:
                rec_month = st.selectbox(
                    "Aba do mês no Google Sheets",
                    options=MONTHS_PT,
                    index=current_month_idx,
                    key="cc_reconcile_month",
                    help=f"Cartão detectado automaticamente: {invoice.bank_name} ({default_range})",
                )
            with col_rec_btn:
                if st.button(
                    f"🔄 Ler Sheets ({default_range}) e Conciliar",
                    type="primary",
                    use_container_width=True,
                    key="btn_cc_reconcile_sheets",
                ):
                    try:
                        with st.spinner(f"Lendo aba '{rec_month}' ({default_range}) no Google Sheets e conciliando..."):
                            df_sheets_cur, sheets_meta = invoice_client.fetch_sheets_card_block(
                                invoice.bank, rec_month
                            )
                            # Garante classificação para lançamentos novos da fatura
                            if "categoria" in active_invoice_df.columns and classify:
                                df_fatura_cls = active_invoice_df.copy()
                            else:
                                df_fatura_cls = credit_card.classify_invoice(
                                    active_invoice_df[["Data", "Estabelecimento", "Valor"]]
                                )
                            df_rec, rec_stats = reconciler.reconcile_transactions(
                                df_sheets_cur, df_fatura_cls
                            )
                            st.session_state["cc_reconcile_state"] = {
                                "df": df_rec,
                                "stats": rec_stats,
                                "meta": sheets_meta,
                                "sheets_count": len(df_sheets_cur),
                            }
                    except invoice_client.InvoiceClientError as rec_err:
                        st.error(str(rec_err))

            rec_state = st.session_state.get("cc_reconcile_state")
            if rec_state is not None:
                df_rec = rec_state["df"]
                rec_stats = rec_state["stats"]
                rec_meta = rec_state["meta"]
                removidos_count = rec_stats.get("removidos", 0)
                val_removido = rec_stats.get("valor_removido", 0.0)
                df_descartados = rec_stats.get("df_descartados", pd.DataFrame())

                val_antigo = rec_stats.get("valor_antigo", 0.0)
                val_novo = rec_stats.get("valor_novo", 0.0)
                val_fatura = rec_stats.get("valor_fatura", 0.0)
                bate_fatura = rec_stats.get("bate_com_fatura", abs(val_novo - val_fatura) < 0.01)

                st.caption(
                    f"Destino: aba **{rec_meta['mes']}** | bloco **{rec_meta['range']}** "
                    f"(capacidade máxima: {rec_meta.get('max_rows', '-')} linhas)"
                )

                m1, m2 = st.columns(2)
                m1.metric("Fatura Anterior (Sheets)", _format_brl(val_antigo))
                diff_ant = round(val_novo - val_antigo, 2)
                m2.metric(
                    "Fatura Conciliada (Atual)",
                    _format_brl(val_novo),
                    delta=f"{'+' if diff_ant >= 0 else ''}{_format_brl(diff_ant)}" if abs(diff_ant) >= 0.01 else "Sem diferença",
                )

                if bate_fatura:
                    st.success(f"✅ Bate 100% com o valor da fatura carregada ({_format_brl(val_fatura)}).")
                else:
                    st.error(
                        f"⚠️ Diferença em relação à fatura carregada ({_format_brl(val_fatura)}): "
                        f"{_format_brl(val_novo - val_fatura)}."
                    )

                tab_rec_final, tab_rec_disc = st.tabs([
                    f"📋 Consolidado Final ({len(df_rec)})",
                    f"🗑️ Não Efetivadas ({removidos_count})",
                ])

                with tab_rec_final:
                    st.caption("Você pode ajustar qualquer **categoria** diretamente na tabela antes de enviar ao Google Sheets.")
                    edited_rec_df = st.data_editor(
                        df_rec[["categoria", "Data", "Estabelecimento", "Valor", "_status"]],
                        use_container_width=True,
                        hide_index=True,
                        disabled=["Data", "Estabelecimento", "Valor", "_status"],
                        column_config={
                            "categoria": st.column_config.TextColumn("Categoria"),
                            "Data": st.column_config.TextColumn("Data"),
                            "Estabelecimento": st.column_config.TextColumn("Estabelecimento"),
                            "Valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
                            "_status": st.column_config.TextColumn("Status"),
                        },
                        key=f"cc_rec_editor_{invoice.bank}_{rec_meta['mes']}",
                    )

                    confirm_write = st.checkbox(
                        f"Confirmo gravar **{len(edited_rec_df)} lançamento(s)** diretamente na aba "
                        f"**{rec_meta['mes']}** ({rec_meta['range']})",
                        value=False,
                        key=f"cc_rec_confirm_{invoice.bank}_{rec_meta['mes']}",
                    )

                    col_send, col_tsv = st.columns([2, 1])
                    with col_send:
                        if st.button(
                            f"📤 Enviar direto para o Google Sheets ({rec_meta['range']})",
                            type="primary",
                            use_container_width=True,
                            disabled=not confirm_write,
                            key="btn_cc_write_sheets",
                        ):
                            try:
                                with st.spinner(f"Gravando em {rec_meta['mes']} ({rec_meta['range']})..."):
                                    write_res = invoice_client.write_sheets_card_block(
                                        invoice.bank,
                                        rec_meta["mes"],
                                        edited_rec_df,
                                    )
                                st.success(
                                    f"✅ **{write_res.get('written_rows', len(edited_rec_df))} lançamento(s)** "
                                    f"gravados com sucesso na aba **{write_res.get('mes')}** ({write_res.get('range')})!"
                                )
                            except invoice_client.InvoiceClientError as write_err:
                                st.error(str(write_err))
                    with col_tsv:
                        tsv_out = reconciler.to_sheets_tsv(edited_rec_df, include_header=False)
                        with st.popover("📋 Copiar TSV", use_container_width=True):
                            st.text_area("TSV para colar manualmente:", value=tsv_out, height=180)

                with tab_rec_disc:
                    if removidos_count > 0 and not df_descartados.empty:
                        st.dataframe(
                            df_descartados[["categoria", "Data", "Estabelecimento", "Valor", "_motivo"]],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.success("Nenhuma transação descartada — tudo da planilha casou com a fatura oficial.")
    except Exception as e:
        logging.info(f"Cartão de Crédito: {e}")
        st.error(f"Erro ao processar fatura: {e}")


# --- Drill Down: Conta Corrente ---
with st.expander("🏦 Conta Corrente", expanded=False):
    col_cc_both, col_cc_itau, col_cc_brad = st.columns([2, 1, 1])
    with col_cc_both:
        if st.button(
            "📥 Buscar Itaú + Bradesco (Drive)",
            type="primary",
            use_container_width=True,
            key="btn_fetch_checking_both",
        ):
            with st.spinner("Buscando extratos Itaú (PDF) e Bradesco (CSV) no Google Drive..."):
                try:
                    st.session_state["checking_remote_itau"] = invoice_client.fetch_latest_statement("itau")
                except invoice_client.InvoiceClientError as fetch_err:
                    st.error(f"Itaú: {fetch_err}")
                try:
                    st.session_state["checking_remote_bradesco"] = invoice_client.fetch_latest_statement("bradesco")
                except invoice_client.InvoiceClientError as fetch_err:
                    st.error(f"Bradesco: {fetch_err}")
    with col_cc_itau:
        if st.button("📥 Só Itaú", use_container_width=True, key="btn_fetch_checking_itau"):
            try:
                with st.spinner("Buscando extrato Itaú (PDF) no Google Drive..."):
                    st.session_state["checking_remote_itau"] = invoice_client.fetch_latest_statement("itau")
            except invoice_client.InvoiceClientError as fetch_err:
                st.error(str(fetch_err))
    with col_cc_brad:
        if st.button("📥 Só Bradesco", use_container_width=True, key="btn_fetch_checking_bradesco"):
            try:
                with st.spinner("Buscando extrato Bradesco (CSV) no Google Drive..."):
                    st.session_state["checking_remote_bradesco"] = invoice_client.fetch_latest_statement("bradesco")
            except invoice_client.InvoiceClientError as fetch_err:
                st.error(str(fetch_err))

    remote_itau = st.session_state.get("checking_remote_itau")
    remote_bradesco = st.session_state.get("checking_remote_bradesco")

    if remote_itau is not None or remote_bradesco is not None:
        col_cc_info, col_cc_clear = st.columns([5, 1])
        with col_cc_info:
            parts_info = []
            if remote_itau is not None:
                parts_info.append(
                    f"Itaú: **{remote_itau.filename}** ({_format_remote_date(remote_itau.date)})"
                )
            if remote_bradesco is not None:
                parts_info.append(
                    f"Bradesco: **{remote_bradesco.filename}** ({_format_remote_date(remote_bradesco.date)})"
                )
            st.caption("Origem automática (Google Drive) — " + " | ".join(parts_info))
        with col_cc_clear:
            if st.button("✖️ Limpar", use_container_width=True, key="btn_clear_remote_checking"):
                st.session_state.pop("checking_remote_itau", None)
                st.session_state.pop("checking_remote_bradesco", None)
                st.rerun()

    col_up_itau, col_up_brad = st.columns(2)
    with col_up_itau:
        itau_upload = st.file_uploader(
            "Upload manual Itaú (.pdf ou .xls)",
            type=["pdf", "xls", "xlsx"],
            key="checking_itau_uploader",
        )
    with col_up_brad:
        bradesco_upload = st.file_uploader(
            "Upload manual Bradesco (.csv)",
            type=["csv"],
            key="checking_bradesco_uploader",
        )

    itau_source = itau_upload if itau_upload is not None else (
        remote_itau.to_bytes_io() if remote_itau is not None else None
    )
    bradesco_source = bradesco_upload if bradesco_upload is not None else (
        remote_bradesco.to_bytes_io() if remote_bradesco is not None else None
    )

    itau_raw = None
    bradesco_raw = None

    if itau_source is not None:
        try:
            itau_raw = checking_account.transform_itau(itau_source)
        except Exception as e:
            logging.info(f"Itau: {e}")
            st.error(f"Erro ao processar extrato Itaú: {e}")

    if bradesco_source is not None:
        try:
            bradesco_raw = checking_account.transform_bradesco(bradesco_source)
        except Exception as e:
            logging.info(f"Bradesco: {e}")
            st.error(f"Erro ao processar extrato Bradesco: {e}")

    # --- Consolidação automática (quando ambos estiverem carregados) ---
    active_checking_df = None
    active_checking_classified = False

    if itau_raw is not None and bradesco_raw is not None:
        try:
            st.subheader("📊 Extrato Consolidado (Itaú + Bradesco)")
            merged = checking_account.consolidate_checking_accounts(itau_raw, bradesco_raw)
            active_checking_df = merged.copy()

            if st.toggle("*Classificar transações consolidadas ?*", value=False, key='consolidated_classifier'):
                merged_class = checking_account.classify_checking_account(merged)
                merged_class['valor (R$)'] = merged_class['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                classification_legend(show_modelo=False)
                st.dataframe(checking_account.style_classified(merged_class), use_container_width=True)
                active_checking_df = merged_class.copy()
                active_checking_classified = True
                tsv_df = merged_class.drop(columns=['_source'], errors='ignore')
            else:
                st.dataframe(merged, use_container_width=True)
                tsv_df = merged

            tsv_checking = tsv_df.to_csv(sep='\t', index=False, header=False, lineterminator='\n')
            with st.popover("📋 Copiar TSV (Sheets A4:E)"):
                st.text_area("TSV para colar no Google Sheets:", value=tsv_checking, height=180, key="checking_tsv_area")
        except Exception as e:
            logging.info(f"Consolidação: {e}")
            st.error(f"Erro ao consolidar os extratos: {e}")
    elif itau_raw is not None:
        active_checking_df = itau_raw.copy()
    elif bradesco_raw is not None:
        active_checking_df = bradesco_raw.copy()

    # --- Conciliação Integrada com Google Sheets (Conta Corrente A4:E1000) ---
    if active_checking_df is not None and not active_checking_df.empty:
        st.divider()
        st.subheader("🔄 Conciliar Conta Corrente com Google Sheets")

        checking_sig = f"{len(active_checking_df)}:{active_checking_df['valor (R$)'].iloc[0]}:{active_checking_df['valor (R$)'].iloc[-1]}"
        if st.session_state.get("checking_reconcile_sig") != checking_sig:
            st.session_state.pop("checking_reconcile_state", None)
            st.session_state["checking_reconcile_sig"] = checking_sig

        default_checking_range = invoice_client.DEFAULT_CHECKING_SHEET_RANGE
        now_dt = datetime.datetime.now()
        current_month_idx = now_dt.month - 1

        col_ck_m, col_ck_cut_on, col_ck_cut_dt = st.columns([1.2, 1.0, 1.3], vertical_alignment="bottom")
        with col_ck_m:
            ck_month = st.selectbox(
                "Aba do mês no Google Sheets",
                options=MONTHS_PT,
                index=current_month_idx,
                key="checking_reconcile_month",
                help=f"Bloco de Conta Corrente: {default_checking_range}",
            )
        with col_ck_cut_on:
            use_cutoff = st.checkbox(
                "Filtrar por data de corte",
                value=True,
                key="checking_use_cutoff",
                help="Mantém apenas lançamentos do extrato a partir da data selecionada.",
            )
        with col_ck_cut_dt:
            default_cutoff = datetime.date(now_dt.year, now_dt.month, 1)
            cutoff_date = st.date_input(
                "A partir de",
                value=default_cutoff,
                format="DD/MM/YYYY",
                disabled=not use_cutoff,
                key="checking_cutoff_date",
            )

        if st.button(
            f"🔄 Ler Sheets ({default_checking_range}) e Conciliar",
            type="primary",
            use_container_width=True,
            key="btn_checking_reconcile_sheets",
        ):
            try:
                with st.spinner(f"Lendo aba '{ck_month}' ({default_checking_range}) no Google Sheets e conciliando..."):
                    df_sheets_ck, sheets_ck_meta = invoice_client.fetch_sheets_checking_block(ck_month)
                    if active_checking_classified and "categoria" in active_checking_df.columns:
                        df_ext_cls = active_checking_df.copy()
                    else:
                        df_ext_cls = checking_account.classify_checking_account(active_checking_df)
                    df_ck_rec, ck_rec_stats = reconciler.reconcile_checking_transactions(
                        df_sheets_ck,
                        df_ext_cls,
                        cutoff_date=cutoff_date if use_cutoff else None,
                    )
                    st.session_state["checking_reconcile_state"] = {
                        "df": df_ck_rec,
                        "stats": ck_rec_stats,
                        "meta": sheets_ck_meta,
                        "cutoff": cutoff_date if use_cutoff else None,
                    }
            except invoice_client.InvoiceClientError as rec_err:
                st.error(str(rec_err))

        ck_rec_state = st.session_state.get("checking_reconcile_state")
        if ck_rec_state is not None:
            df_ck_rec = ck_rec_state["df"]
            ck_stats = ck_rec_state["stats"]
            ck_meta = ck_rec_state["meta"]
            ck_cutoff = ck_rec_state.get("cutoff")

            removidos_ck = ck_stats.get("removidos", 0)
            df_ck_disc = ck_stats.get("df_descartados", pd.DataFrame())
            val_antigo_ck = ck_stats.get("valor_antigo", 0.0)
            val_novo_ck = ck_stats.get("valor_novo", 0.0)
            val_ext_ck = ck_stats.get("valor_extrato", 0.0)
            bate_ext = ck_stats.get("bate_com_extrato", True)
            filtrados_corte = ck_stats.get("filtrados_por_corte", 0)

            cutoff_txt = f" | corte >= **{ck_cutoff.strftime('%d/%m/%Y')}** ({filtrados_corte} anterior(es) ignorado(s))" if ck_cutoff else ""
            st.caption(
                f"Destino: aba **{ck_meta['mes']}** | bloco **{ck_meta['range']}** "
                f"(capacidade máxima: {ck_meta.get('max_rows', '-')} linhas){cutoff_txt}"
            )

            cm1, cm2 = st.columns(2)
            cm1.metric("Saldo Líquido Anterior (Sheets)", _format_brl(val_antigo_ck))
            diff_ck = round(val_novo_ck - val_antigo_ck, 2)
            cm2.metric(
                "Saldo Líquido Conciliado (Atual)",
                _format_brl(val_novo_ck),
                delta=f"{'+' if diff_ck >= 0 else ''}{_format_brl(diff_ck)}" if abs(diff_ck) >= 0.01 else "Sem diferença",
            )

            if bate_ext:
                st.success(
                    f"✅ Bate 100% com o extrato filtrado ({_format_brl(val_ext_ck)}) — "
                    f"**{ck_stats.get('mantidos', 0)}** mantido(s) do Sheets, **{ck_stats.get('novos', 0)}** novo(s)."
                )
            else:
                st.error(f"⚠️ Diferença em relação ao extrato ({_format_brl(val_ext_ck)}): {_format_brl(val_novo_ck - val_ext_ck)}.")

            tab_ck_final, tab_ck_disc = st.tabs([
                f"📋 Consolidado Final ({len(df_ck_rec)})",
                f"🗑️ Apenas no Sheets ({removidos_ck})",
            ])

            with tab_ck_final:
                st.caption("Você pode ajustar qualquer **categoria** diretamente na tabela antes de enviar ao Google Sheets.")
                edited_ck_df = st.data_editor(
                    df_ck_rec[["categoria", "Data", "Lançamento", "Banco", "Valor", "_status"]],
                    use_container_width=True,
                    hide_index=True,
                    disabled=["Data", "Lançamento", "Banco", "Valor", "_status"],
                    column_config={
                        "categoria": st.column_config.TextColumn("Categoria"),
                        "Data": st.column_config.TextColumn("Data"),
                        "Lançamento": st.column_config.TextColumn("Lançamento"),
                        "Banco": st.column_config.TextColumn("Banco"),
                        "Valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
                        "_status": st.column_config.TextColumn("Status"),
                    },
                    key=f"ck_rec_editor_{ck_meta['mes']}",
                )

                confirm_ck_write = st.checkbox(
                    f"Confirmo gravar **{len(edited_ck_df)} lançamento(s)** diretamente na aba "
                    f"**{ck_meta['mes']}** ({ck_meta['range']})",
                    value=False,
                    key=f"ck_rec_confirm_{ck_meta['mes']}",
                )

                col_ck_send, col_ck_tsv = st.columns([2, 1])
                with col_ck_send:
                    if st.button(
                        f"📤 Enviar direto para o Google Sheets ({ck_meta['range']})",
                        type="primary",
                        use_container_width=True,
                        disabled=not confirm_ck_write,
                        key="btn_ck_write_sheets",
                    ):
                        try:
                            with st.spinner(f"Gravando em {ck_meta['mes']} ({ck_meta['range']})..."):
                                write_res = invoice_client.write_sheets_checking_block(
                                    ck_meta["mes"],
                                    edited_ck_df,
                                )
                            st.success(
                                f"✅ **{write_res.get('written_rows', len(edited_ck_df))} lançamento(s)** "
                                f"gravados com sucesso na aba **{write_res.get('mes')}** ({write_res.get('range')})!"
                            )
                        except invoice_client.InvoiceClientError as write_err:
                            st.error(str(write_err))
                with col_ck_tsv:
                    tsv_ck_out = reconciler.to_checking_sheets_tsv(edited_ck_df, include_header=False)
                    with st.popover("📋 Copiar TSV", use_container_width=True):
                        st.text_area("TSV para colar manualmente:", value=tsv_ck_out, height=180, key="ck_rec_tsv_area")

            with tab_ck_disc:
                if removidos_ck > 0 and not df_ck_disc.empty:
                    st.dataframe(
                        df_ck_disc[["categoria", "Data", "Lançamento", "Banco", "Valor", "_motivo"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.success("Nenhum lançamento descartado — tudo do Sheets casou com o extrato.")

    # --- Visualização individual (Itaú / Bradesco) ---
    if itau_raw is not None or bradesco_raw is not None:
        st.divider()
        tab_labels = []
        if itau_raw is not None:
            tab_labels.append(f"🟠 Itaú ({len(itau_raw)})")
        if bradesco_raw is not None:
            tab_labels.append(f"🔴 Bradesco ({len(bradesco_raw)})")

        tabs = st.tabs(tab_labels)
        tab_idx = 0

        if itau_raw is not None:
            with tabs[tab_idx]:
                if st.toggle("*Classificar transações Itaú ?*", value=False, key='itau_classifier'):
                    itau_cls = checking_account.classify_checking_account(itau_raw)
                    itau_cls['valor (R$)'] = itau_cls['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                    classification_legend(show_modelo=False)
                    st.dataframe(checking_account.style_classified(itau_cls), use_container_width=True)
                else:
                    st.dataframe(itau_raw, use_container_width=True)
            tab_idx += 1

        if bradesco_raw is not None:
            with tabs[tab_idx]:
                if st.toggle("*Classificar transações Bradesco ?*", value=False, key='bradesco_classifier'):
                    brad_cls = checking_account.classify_checking_account(bradesco_raw)
                    brad_cls['valor (R$)'] = brad_cls['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                    classification_legend(show_modelo=False)
                    st.dataframe(checking_account.style_classified(brad_cls), use_container_width=True)
                else:
                    st.dataframe(bradesco_raw, use_container_width=True)
