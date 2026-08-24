from multiprocessing import Value
from typing import Any

import pandas as pd
import numpy as np
from pandas.api.types import is_string_dtype, is_integer_dtype
import pytest

import union_lists.dataset.extract_from_xlsx as xlsx_extract


def convert_na(lst: list[Any]) -> list[Any]:
    new_lst = []
    for x in lst:
        if pd.isna(x):
            new_lst.append(False)
        else:
            new_lst.append(x)

    return new_lst


def test_copy_to_col():
    dummy_df = pd.DataFrame(data={"0": [0,1,2], "1":[pd.NA, pd.NA, pd.NA]}, index=[0,1,2])
    simple_copy = dummy_df.copy()
    xlsx_extract.copy_to_col(simple_copy, idx=[0, 1], source="0", destination="1")

    assert convert_na(simple_copy["0"].to_list()) == [False, False, 2]
    assert convert_na(simple_copy["1"].to_list()) == [0, 1, False]

    dummy_df["1"] = dummy_df["1"].astype(str)
    dummy_df = dummy_df.rename(columns={"1": "notes"})

    notes_copy = dummy_df.copy()
    with pytest.raises(ValueError):
        xlsx_extract.copy_to_col(notes_copy, idx=[1,2], source="0", destination="notes")
    
    dummy_df["notes"] = ""
    notes_copy = dummy_df.copy()
    xlsx_extract.copy_to_col(notes_copy, idx=[1,2], source="0", destination="notes")
    
    assert convert_na(notes_copy["0"].to_list()) == [0.0, False, False]
    assert convert_na(notes_copy["notes"].to_list()) == ["", "Note copied from 0: 1", "Note copied from 0: 2"]

    lb_notes_copy = dummy_df.copy()
    lb_notes_copy["2"] = ["note 0", "note 1", "note 2"]
    lb_notes_copy.loc[0, "notes"] = "lb_test"
    xlsx_extract.copy_to_col(lb_notes_copy, idx=[1,2], source="0", destination="notes")

    assert convert_na(lb_notes_copy["0"].to_list()) == [0.0, False, False]
    assert convert_na(lb_notes_copy["notes"].to_list()) == ["lb_test", "Note copied from 0: 1", "Note copied from 0: 2"]

    xlsx_extract.copy_to_col(lb_notes_copy, idx=[1,2], source="2", destination="notes")

    # Check no overwriting
    assert convert_na(lb_notes_copy["2"].to_list()) == ["note 0", False, False]
    assert convert_na(lb_notes_copy["notes"].to_list()) == ["lb_test", "Note copied from 0: 1\nNote copied from 2: note 1", "Note copied from 0: 2\nNote copied from 2: note 2"]


def test_clean_dates():
    dates = pd.Series([".", "                         ", " ", "19669", "1961", "219", "19", "1969`"])
    result = xlsx_extract.clean_dates(dates)
    expected = pd.Series([pd.NA, pd.NA, pd.NA, "1969", "1961", "19", "19", "1969"])
    assert result.equals(expected)


def test_clean_coloured():
    coloured = pd.Series(["A ", "z", "0", "xx", "a-", "-", "x-", "."])
    result = xlsx_extract.clean_coloured(coloured)
    expected = pd.Series(["a", "x", "x", "x", "a-", "x", "x", pd.NA])
    assert result.equals(expected)


def test_clean_gridded():
    gridded = pd.Series(["A ", "xx", " "])
    result = xlsx_extract.clean_gridded(gridded)
    expected = pd.Series(["A", "x", pd.NA])
    assert result.equals(expected)


def test_clean_copies():
    copies = pd.Series(["xa", "x "])
    result = xlsx_extract.clean_copies(copies)
    expected = pd.Series(["xa", "1"])
    assert result.equals(expected)


def test_pre_process_xlsx():
    simple_df = pd.read_excel("tests/Block 2.xlsx")
    simple_df.loc[5, "Unnamed: 3"] = ' '

    simple_result = xlsx_extract.pre_process_xlsx(simple_df, file_id="Block 2")
    
    assert simple_result.shape == (260, 31)
    assert (simple_result.index == pd.RangeIndex(0, 260)).all()
    assert simple_result.columns[0] == "block_number"
    assert simple_result.columns[-1] == "notes"
    assert sum([1 for c in simple_result.columns if "date" in c]) == 6
    assert sum([1 for c in simple_result.columns if "copies" in c]) == 6
    assert sum([1 for c in simple_result.columns if "gridded" in c]) == 6

    count = simple_result.count()
    assert count[["block_number", "block_letter", "sheet_id"]].to_list() == [260, 260, 260]

    assert is_integer_dtype(simple_result["block_number"])
    assert is_string_dtype(simple_result["block_letter"])
    assert is_integer_dtype(simple_result["sheet_id"])

    assert simple_result["block_letter"].dropna().equals(simple_result["block_letter"].dropna().str.strip())

    assert simple_result["date_1"].dropna().values.tolist() == ["1956", "1966", "1944", "1955"]

    complex_df = pd.read_excel("tests/Block 34.xlsx")
    complex_result = xlsx_extract.pre_process_xlsx(complex_df, file_id="Block 34")

    assert complex_result["notes"].dropna().unique().tolist() == ['Note copied from Copies 1: All marked Secret', 'Note copied from Copies 3: [S=Secret]', 'Note copied from Copies 2: S = Secret']