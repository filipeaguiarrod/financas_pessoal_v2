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
                orders_df = psql.get_ecommerce_orders(days=120, origem="Amazon")
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
                            enriched_df.at[row_idx, "Estabelecimento"] = f"{orig_estab} — {chosen['descricao']}"
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

                st.caption(
                    f"Destino: aba **{rec_meta['mes']}** | bloco **{rec_meta['range']}** "
                    f"(capacidade máxima: {rec_meta.get('max_rows', '-')} linhas)"
                )

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("💳 Fatura Oficial", _format_brl(rec_stats.get("valor_fatura", 0.0)), f"{rec_stats.get('total', 0)} itens")
                m2.metric("📋 Base Sheets", _format_brl(rec_stats.get("valor_antigo", 0.0)), f"{rec_state.get('sheets_count', 0)} itens")
                m3.metric("🏷️ Mantidas", str(rec_stats.get("mantidos", 0)))
                m4.metric("🆕 Novos", str(rec_stats.get("novos", 0)))
                m5.metric("🗑️ Descartados", str(removidos_count), f"-{_format_brl(val_removido)}" if removidos_count > 0 else "0", delta_color="inverse" if removidos_count > 0 else "off")

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
    itau_file = None
    bradesco_file = None

    # --- Itau ---
    try:
        st.subheader('Itau')
        itau_file = st.file_uploader("Jogue aqui o arquivo .xls Itau")
        if itau_file is not None:
            itau = checking_account.transform_itau(itau_file)

            if st.toggle("*Classificar transações ?*", value=False, key='itau_classifier'):
                itau = checking_account.classify_checking_account(itau)
                itau['valor (R$)'] = itau['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                classification_legend(show_modelo=False)
                st.dataframe(checking_account.style_classified(itau))
            else:
                st.dataframe(itau)
    except Exception as e:
        logging.info(f"Itau: {e}")
        st.error(f"Erro ao processar extrato Itaú: {e}")

    # --- Bradesco ---
    try:
        st.subheader('Bradesco')
        bradesco_file = st.file_uploader("Jogue aqui o arquivo .csv Bradesco")
        if bradesco_file is not None:
            bradesco = checking_account.transform_bradesco(bradesco_file)

            if st.toggle("*Classificar transações ?*", value=False, key='bradesco_classifier'):
                bradesco = checking_account.classify_checking_account(bradesco)
                bradesco['valor (R$)'] = bradesco['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                classification_legend(show_modelo=False)
                st.dataframe(checking_account.style_classified(bradesco))
            else:
                st.dataframe(bradesco)
    except Exception as e:
        logging.info(f"Bradesco: {e}")
        st.error(f"Erro ao processar extrato Bradesco: {e}")

    # --- Consolidação (quando ambos forem carregados) ---
    if itau_file is not None and bradesco_file is not None:
        try:
            st.subheader('Extrato Consolidado')
            itau_raw = checking_account.transform_itau(itau_file)
            bradesco_raw = checking_account.transform_bradesco(bradesco_file)

            # Consolidar usando as regras de filtragem
            merged = checking_account.consolidate_checking_accounts(itau_raw, bradesco_raw)

            if st.toggle("*Classificar transações consolidadas ?*", value=False, key='consolidated_classifier'):
                merged_class = checking_account.classify_checking_account(merged)
                merged_class['valor (R$)'] = merged_class['valor (R$)'].map(lambda x: f"{x:.2f}".replace('.', ','))
                classification_legend(show_modelo=False)
                st.dataframe(checking_account.style_classified(merged_class))
            else:
                st.dataframe(merged)
        except Exception as e:
            logging.info(f"Consolidação: {e}")
            st.error(f"Erro ao consolidar os extratos: {e}")
