import streamlit as st
from src import postgres as ps
from src.sidebars import Navbar

st.set_page_config(page_title='Regras do Usuário', layout='centered')
Navbar()

st.title('Regras do Usuário')
st.caption('Regras aplicadas na classificação antes do modelo de ML. A primeira regra que bater com o estabelecimento ganha.')

psql = ps.PostgresUploader()
psql.ensure_rules_table()


def reload_rules():
    return psql.get_rules()


rules = reload_rules()

# --- Regras existentes ---
st.subheader('Regras cadastradas')
if rules.empty:
    st.info('Nenhuma regra cadastrada ainda.')
else:
    st.dataframe(rules, use_container_width=True, hide_index=True)

st.divider()

# --- Adicionar ---
st.subheader('Adicionar regra')
with st.form('form_add', clear_on_submit=True):
    sentenca = st.text_input('Sentença', placeholder='ex: netflix')
    categoria = st.text_input('Categoria', placeholder='ex: Streaming')
    submitted = st.form_submit_button('Salvar')
    if submitted:
        if sentenca.strip() and categoria.strip():
            psql.add_rule(sentenca.strip(), categoria.strip())
            st.success(f'Regra "{sentenca}" → "{categoria}" adicionada.')
            st.rerun()
        else:
            st.warning('Preencha sentença e categoria.')

st.divider()

# --- Editar ---
st.subheader('Editar regra')
if not rules.empty:
    with st.form('form_edit'):
        rule_id_edit = st.selectbox('ID da regra', rules['id'].tolist())
        row = rules[rules['id'] == rule_id_edit].iloc[0]
        nova_sentenca = st.text_input('Nova sentença', value=row['sentenca'])
        nova_categoria = st.text_input('Nova categoria', value=row['categoria'])
        submitted_edit = st.form_submit_button('Atualizar')
        if submitted_edit:
            psql.update_rule(rule_id_edit, nova_sentenca.strip(), nova_categoria.strip())
            st.success('Regra atualizada.')
            st.rerun()
else:
    st.info('Nenhuma regra para editar.')

st.divider()

# --- Deletar ---
st.subheader('Deletar regra')
if not rules.empty:
    with st.form('form_delete'):
        rule_id_del = st.selectbox('ID da regra', rules['id'].tolist(), key='del_select')
        confirm = st.checkbox('Confirmar exclusão')
        submitted_del = st.form_submit_button('Deletar', type='primary')
        if submitted_del:
            if confirm:
                psql.delete_rule(rule_id_del)
                st.success(f'Regra {rule_id_del} deletada.')
                st.rerun()
            else:
                st.warning('Marque a confirmação antes de deletar.')
else:
    st.info('Nenhuma regra para deletar.')
