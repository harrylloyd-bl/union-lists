import pandas as pd
import union_lists.dataset.extract_from_xlsx as xlsx_extract


def test_pre_process_xlsx():
    df = pd.read_excel("tests/Block 2.xlsx")

    result = xlsx_extract.pre_process_xlsx(df, file_id="Block 2")
    
    assert result.shape == (256, 31)
    assert (result.index == pd.RangeIndex(0, 256)).all()
    assert result.columns[0] == "block_number"
    assert result.columns[-1] == "notes"
    assert sum([1 for c in result.columns if "date" in c]) == 6
    assert sum([1 for c in result.columns if "copies" in c]) == 6
    assert sum([1 for c in result.columns if "gridded" in c]) == 6

    count = result.count()
    assert count[["block_number", "block_letter", "sheet_id"]].to_list() == [256, 256, 256]