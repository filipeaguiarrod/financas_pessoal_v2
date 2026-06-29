import re
from pathlib import Path

import pandas as pd
import pytest

from src.installments import run_pipeline

GROUND_TRUTH = Path(__file__).parent.parent / "data" / "ground_truth" / "parcelas"
INPUTS_DIR = GROUND_TRUTH / "inputs"
EXPECTED_DIR = GROUND_TRUTH / "expected"


def _input_name_from_expected(expected_path: Path) -> Path:
    """Deriva o nome do arquivo de input a partir do expected (remove '-final-table')."""
    input_name = re.sub(r"-final-table", "", expected_path.stem) + ".csv"
    return INPUTS_DIR / input_name


def _load_pairs():
    pairs = []
    for expected_path in sorted(EXPECTED_DIR.glob("*.csv")):
        input_path = _input_name_from_expected(expected_path)
        if input_path.exists():
            pairs.append(pytest.param(input_path, expected_path, id=expected_path.stem))
    return pairs


def _print_diff(result: pd.DataFrame, expected: pd.DataFrame) -> None:
    common_cols = [c for c in result.columns if c in expected.columns]
    r = result[common_cols].reset_index(drop=True)
    e = expected[common_cols].reset_index(drop=True)

    found_diff = False
    for col in r.columns:
        both_nan = r[col].isna() & e[col].isna()
        diverge = r[col].ne(e[col]) & ~both_nan
        if diverge.any():
            found_diff = True
            print(f"\n[DIFF] coluna '{col}':")
            print(pd.concat([r.loc[diverge, col].rename("resultado"),
                             e.loc[diverge, col].rename("esperado")], axis=1).to_string())

    if not found_diff:
        print("\n[OK] nenhuma divergência encontrada")


@pytest.mark.parametrize("input_path,expected_path", _load_pairs())
def test_pipeline_matches_ground_truth(input_path, expected_path):
    print(f"\n--- comparando ---")
    print(f"  input   : {input_path}")
    print(f"  expected: {expected_path}")

    result = run_pipeline(input_path)
    expected = pd.read_csv(expected_path)

    print(f"linhas  resultado={len(result)} | esperado={len(expected)}")
    print(f"colunas resultado={list(result.columns)}")
    print(f"colunas esperadas={list(expected.columns)}")

    cols_extra = set(result.columns) - set(expected.columns)
    cols_faltando = set(expected.columns) - set(result.columns)
    if cols_extra:
        print(f"[AVISO] colunas a mais no resultado: {cols_extra}")
    if cols_faltando:
        print(f"[AVISO] colunas faltando no resultado: {cols_faltando}")

    print("\nresultado:")
    print(result.to_string(index=False))
    print("\nesperado:")
    print(expected.to_string(index=False))

    _print_diff(result, expected)

    pd.testing.assert_frame_equal(
        result.reset_index(drop=True),
        expected.reset_index(drop=True),
        check_like=True,
        check_dtype=False,
    )
