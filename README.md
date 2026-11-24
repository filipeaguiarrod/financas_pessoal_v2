# Finanças Pessoal v2

## Ideia Geral do Repositório

Interface Streamlit para padronizar e processar arquivos CSV e XLSX de diferentes instituições financeiras:

- XP Investimentos
- Conta Itaú
- Cartão Itaú
- Cartão Nubank

## Funcionalidades

### Aba Cartão de Crédito (`app.py`)
- **Importação flexível de faturas (XP e Nubank):**
  - Upload manual de arquivo `.csv`.
  - Busca automática via `financas_backend` (configurado em `FINANCAS_API_URL` no `.env`):
    - **XP Investimentos:** busca o `.csv` mais recente da pasta configurada no Google Drive (`GET /invoices/xp/latest`).
    - **Nubank:** busca em tempo real o anexo `.csv` do e-mail mais recente de fatura no Gmail (`GET /invoices/nubank/latest`).
- **Classificação e Enriquecimento:**
  - Classifica automaticamente as transações via regras do usuário → histórico no banco → modelo de ML ([financial_category_model](https://github.com/filipeaguiarrod/financial_category_model)).
  - Enriquecimento opcional multi-origem de lançamentos de e-commerce (**Amazon**, **Shopee** e **Mercado Livre**) a partir da tabela `ecommerce_orders`, padronizando os nomes de forma enxuta (`AMZ - <Descrição>`, `Shopee - <Descrição>`, `MELI - <Descrição>`).
- **Conciliação Integrada com Google Sheets:**
  - Identifica automaticamente o banco (`xp` → `G4:J98` ou `nubank` → `G99:J200`) e a aba do mês atual.
  - Lê os lançamentos atuais da planilha via backend (`GET /sheets/card-block`), reconcilia mantendo a fatura oficial como verdade absoluta e exibe a comparação **Fatura Anterior (Sheets)** vs **Fatura Conciliada (Atual)** com confirmação de batimento.
  - Permite editar categorias inline na tabela e enviar o bloco reconciliado diretamente para o Google Sheets (`POST /sheets/card-block`) com confirmação explícita.

### Módulo de Análise de Parcelas
Analisa as parcelas das faturas dos cartões, facilitando o acompanhamento de despesas parceladas.
Pode usar modelos de LLM para criar um report de extensão e valor das contas parceladas.

### Aba E-commerce
Processa dados de compras em lojinhas online através de HTML tabulado, ajudando na organização e categorização de gastos com e-commerce.
- Shopee
- Amazon
- Mercado Livre (não mostra preços)

Basta copiar o html nas páginas de pedidos e colar no campo indicado para gerar a tabela de compras.

### Aba Backoffice
Agrupa ferramentas administrativas integradas ao banco de dados:
- **Regras do Usuário**: Interface para cadastrar, editar ou remover regras personalizadas de classificação baseadas no nome do estabelecimento.
- **Painel de ETL**: Controle integrado com a API `financas_backend` para acionar novas cargas de processamento, sincronizar pedidos de e-commerce (`POST /sync-ecommerce`) e monitorar o status da última execução em segundo plano.
- **Visualizador de Dados**: Consulta simplificada dos lançamentos de conta corrente e cartão de crédito salvos no banco de dados filtrados por mês de competência, exibindo a tabela com os nomes de colunas originais do banco.

## Configuração (`.env`)
Nenhuma credencial, token ou URL privada é versionada no repositório. Configure localmente no arquivo `.env`:
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SCHEMA`
- `FINANCAS_API_URL` — URL base da API `financas_backend` (ex.: `http://localhost:7555`)
- `CLASSIFICATION_MODEL_API`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`
