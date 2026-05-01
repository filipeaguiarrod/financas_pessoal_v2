# Testes de parcelas

## O que é testado

O pipeline determinístico de extração de parcelas (`src/parcelas.py`) é testado comparando sua saída com arquivos de resultado esperado (ground truth) gerados manualmente.

---

## Estrutura de arquivos

```
data/ground_truth/parcelas/
├── inputs/      ← faturas brutas no formato original do banco
└── expected/    ← resultado esperado após rodar o pipeline
```

Os arquivos de `inputs/` e `expected/` não sobem para o repositório (excluídos via `.gitignore`).

---

## Como o teste funciona

### 1. Descoberta automática dos pares

O teste varre `expected/` e para cada arquivo deriva o input correspondente removendo `-final-table` do nome:

```
nu-fatura-2026-05-02-final-table.csv  →  nu-fatura-2026-05-02.csv
xp-fatura-2026-05-05-final-table.csv  →  xp-fatura-2026-05-05.csv
```

Se o input existir em `inputs/`, o par é registrado. Adicionar novos ground truths não exige alterar o código do teste.

### 2. Execução do pipeline real

Para cada par, `run_pipeline(input_path)` executa o fluxo completo:

```
load_csv → detect_bank → extract_invoice_month → standardize → build_crosstable
```

O mesmo código que roda em produção no Streamlit.

### 3. Comparação com o ground truth

`pd.testing.assert_frame_equal` compara o resultado com o CSV esperado com duas tolerâncias:

- `check_like=True` — aceita linhas e colunas em ordem diferente
- `check_dtype=False` — não falha por diferença de tipo (`int64` vs `float64`)

O log imprime ambas as tabelas lado a lado e aponta células divergentes. `NaN vs NaN` é ignorado pois não é divergência real.

---

## Como rodar

```bash
make test_parcelas
```

---

## Como adicionar um novo caso de teste

1. Coloque a fatura bruta em `data/ground_truth/parcelas/inputs/`
2. Gere o resultado esperado manualmente e salve em `data/ground_truth/parcelas/expected/` seguindo o padrão de nome `<nome-da-fatura>-final-table.csv`
3. Rode `make test_parcelas` — o novo par é detectado automaticamente

---

## O que o teste garante

Se `parse_nubank`, `parse_xp` ou `build_crosstable` forem alterados e o resultado mudar, o teste quebra e mostra exatamente qual coluna e linha divergiu.
