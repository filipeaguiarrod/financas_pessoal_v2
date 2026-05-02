import streamlit as st
from src import postgres as ps
from src.sidebars import Navbar

st.set_page_config(page_title='Regras do Usuário', layout='centered')
Navbar()

st.title('Regras do Usuário')

# --- Diagrama do pipeline ---
st.markdown("""
```
📥 Transação nova
      │
      ▼
┌─────────────────────────────┐
│  1. Histórico (banco de dados) │  ← estabelecimento + valor arredondado ao inteiro (ex: R$49,99 ≈ R$49,51)
└─────────────────────────────┘
      │ NÃO classificado
      ▼
┌─────────────────────────────┐
│  2. Regras do usuário        │  ← esta página — busca sentença no nome do estabelecimento
└─────────────────────────────┘
      │ NÃO classificado
      ▼
┌─────────────────────────────┐
│  3. Modelo de ML             │  ← classifica o restante automaticamente
└─────────────────────────────┘
      │
      ▼
✅ Categoria definida
```
""")

st.caption('A categoria das regras é preservada como cadastrada. O que não for coberto pelas etapas 1 e 2 vai para o modelo.')

st.divider()

psql = ps.PostgresUploader()
psql.ensure_rules_table()

rules = psql.get_rules()
categories = psql.get_categories()

# --- Tabela de regras ---
st.subheader('Regras cadastradas')
if rules.empty:
    st.info('Nenhuma regra cadastrada ainda.')
else:
    st.dataframe(
        rules,
        use_container_width=True,
        hide_index=True,
        column_config={
            'id':        st.column_config.NumberColumn('ID', width='small'),
            'sentenca':  st.column_config.TextColumn('Sentença'),
            'categoria': st.column_config.TextColumn('Categoria'),
        }
    )

st.divider()

# --- Adicionar regra ---
st.subheader('Adicionar regra')
with st.form('form_add', clear_on_submit=True):
    sentenca = st.text_input('Sentença', placeholder='ex: netflix')
    categoria = st.selectbox('Categoria', options=categories)
    submitted = st.form_submit_button('Salvar')
    if submitted:
        if sentenca.strip():
            psql.add_rule(sentenca.strip(), categoria)
            st.success(f'Regra "{sentenca.strip()}" → "{categoria}" adicionada.')
            st.rerun()
        else:
            st.warning('Preencha a sentença.')

st.divider()

# --- Modificar / Deletar por ID ---
st.subheader('Modificar ou deletar regra')

if rules.empty:
    st.info('Nenhuma regra cadastrada ainda.')
else:
    rule_id = st.number_input('ID da regra', min_value=int(rules['id'].min()), max_value=int(rules['id'].max()), step=1)

    matched = rules[rules['id'] == rule_id]
    if matched.empty:
        st.warning(f'ID {rule_id} não encontrado.')
    else:
        row = matched.iloc[0]
        st.markdown(f'**Sentença atual:** `{row["sentenca"]}`  |  **Categoria atual:** `{row["categoria"]}`')

        acao = st.radio('Ação', ['Modificar', 'Deletar'], horizontal=True)

        if acao == 'Modificar':
            with st.form('form_edit'):
                nova_sentenca = st.text_input('Nova sentença', value=row['sentenca'])
                nova_categoria = st.selectbox(
                    'Nova categoria',
                    options=categories,
                    index=categories.index(row['categoria']) if row['categoria'] in categories else 0,
                )
                if st.form_submit_button('Atualizar'):
                    psql.update_rule(int(rule_id), nova_sentenca.strip(), nova_categoria)
                    st.success('Regra atualizada.')
                    st.rerun()

        else:
            with st.form('form_delete'):
                st.warning(f'Você está prestes a deletar a regra **{rule_id}**: `{row["sentenca"]}` → `{row["categoria"]}`')
                confirm = st.checkbox('Confirmar exclusão')
                if st.form_submit_button('Deletar', type='primary'):
                    if confirm:
                        psql.delete_rule(int(rule_id))
                        st.success(f'Regra {rule_id} deletada.')
                        st.rerun()
                    else:
                        st.warning('Marque a confirmação antes de deletar.')
