# Finanças Pessoal v2

## Ideia Geral do Repositório

Interface Streamlit para padronizar e processar extratos e faturas (CSV, XLS e PDF) de diferentes instituições financeiras:

- XP Investimentos
- Conta Itaú (PDF exportado do app ou XLS)
- Conta Bradesco (CSV)
- Cartão Nubank

## Funcionalidades

### Aba Cartão de Crédito (`app.py`)
- **Importação flexível de faturas (XP e Nubank):**
  - Upload manual de arquivo `.csv`.
  - Busca automática via `financas_backend` (configurado em `FINANCAS_API_URL` no `.env`):
    - **XP Investimentos:** busca o `.csv` mais recente da pasta configurada no Google Drive (`GET /invoices/xp/latest`).
    - **Nubank:** busca em tempo real o anexo `.csv` do e-mail mais recente de fatura no Gmail (`GET /invoices/nubank/latest`).
- **Classificação e Enriquecimento:**
  - Classifica automaticamente as transações na ordem: **Regras do usuário** (`rules_classifier`) → **Histórico no PostgreSQL** (`primary_classifier`) → **Modelo de Machine Learning** (`secondary_classifier`, via [financial_category_model](https://github.com/filipeaguiarrod/financial_category_model)).
  - Enriquecimento opcional multi-origem de lançamentos de e-commerce (**Amazon**, **Shopee** e **Mercado Livre**) a partir da tabela `ecommerce_orders`, padronizando os nomes de forma enxuta (`AMZ - <Descrição>`, `Shopee - <Descrição>`, `MELI - <Descrição>`).
  - **Reclassificação pela descrição rica do produto:** quando ambos os toggles (*Classificar transações ?* e *Enriquecer ecommerce ?*) estão ativos — tanto no match automático quanto na resolução manual de casos ambíguos — a **descrição real do produto** (sem o prefixo/ruído da operadora) é enviada novamente para toda a cadeia de classificação (incluindo o modelo de Machine Learning), substituindo a categoria genérica pela categoria inferida do produto.
- **Conciliação Integrada com Google Sheets:**
  - Identifica automaticamente o banco (`xp` → `G4:J98` ou `nubank` → `G99:J200`) e a aba do mês atual.
  - Lê os lançamentos atuais da planilha via backend (`GET /sheets/card-block`), reconcilia mantendo a fatura oficial como verdade absoluta e exibe a comparação **Fatura Anterior (Sheets)** vs **Fatura Conciliada (Atual)** com confirmação de batimento.
  - Permite editar categorias inline na tabela e enviar o bloco reconciliado diretamente para o Google Sheets (`POST /sheets/card-block`) com confirmação explícita.

### Aba Conta Corrente (`app.py`)
- **Importação automática via Google Drive (`financas_backend`) e upload manual:**
  - Botão único **"📥 Buscar Itaú + Bradesco (Drive)"** (além de busca individual e upload manual de `.pdf`/`.xls` para Itaú e `.csv` para Bradesco):
    - **Itaú (`GET /statements/itau/latest`):** baixa o extrato `.pdf` mais recente do Google Drive e extrai apenas os lançamentos efetivados com `pdfplumber` (ignorando cabeçalho de saldos/limites, `Lançamentos futuros`, linhas de saldo diário e `Posição consolidada`), montando a descrição no formato `<Tipo> - <Descrição>`.
    - **Bradesco (`GET /statements/bradesco/latest`):** baixa o extrato `.csv` mais recente do Google Drive (diferenciando-o automaticamente dos CSVs da XP na mesma pasta) e interrompe a leitura antes de `Lançamentos periódicos`.
- **Consolidação automática e Classificação:**
  - Ao carregar Itaú e Bradesco, consolida ambos automaticamente removendo rendimentos automáticos, pagamentos de fatura (XP/Nubank) e transferências internas entre as duas contas.
  - Classifica os lançamentos via Regras do Usuário + Histórico no PostgreSQL e disponibiliza botão **"📋 Copiar TSV (Sheets A4:E)"** pronto para colagem na planilha.

### Módulo de Análise de Parcelas (`pages/installments.py`)
Analisa as parcelas das faturas dos cartões (XP e Nubank), facilitando o acompanhamento de despesas parceladas:
- **Busca automática via `financas_backend`:** botões para carregar **XP + Nubank juntos**, **só XP (Drive)** ou **só Nubank (Gmail)**, além de upload manual de múltiplos CSVs.
- Gera crosstable de projeção mensal e gráficos analíticos consolidados (participação por banco, por estabelecimento e evolução mensal).

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
