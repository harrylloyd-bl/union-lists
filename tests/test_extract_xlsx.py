import pandas as pd
from pandas.api.types import is_string_dtype, is_integer_dtype
import numpy as np
import union_lists.dataset.extract_from_xlsx as xlsx_extract


def test_pre_process_xlsx():
    df = pd.read_excel("tests/Block 2.xlsx")

    result = xlsx_extract.pre_process_xlsx(df, file_id="Block 2")
    
    assert result.shape == (260, 31)
    assert (result.index == pd.RangeIndex(0, 260)).all()
    assert result.columns[0] == "block_number"
    assert result.columns[-1] == "notes"
    assert sum([1 for c in result.columns if "date" in c]) == 6
    assert sum([1 for c in result.columns if "copies" in c]) == 6
    assert sum([1 for c in result.columns if "gridded" in c]) == 6

    count = result.count()
    assert count[["block_number", "block_letter", "sheet_id"]].to_list() == [260, 256, 256]

    assert is_integer_dtype(result["block_number"])
    assert is_string_dtype(result["block_letter"])
    assert is_integer_dtype(result["sheet_id"])

    assert result["block_letter"].dropna().equals(result["block_letter"].dropna().str.strip())

    assert result["date_1"].dropna().values.tolist() == ["1956", "1944", "1955"]