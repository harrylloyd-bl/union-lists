from datetime import datetime
import logging

import pytest
from pytest import raises
import pandas as pd

from union_lists.config import *
from union_lists.dataset import reformat_union_lists as data

logger = logging.getLogger(__name__)
logging.basicConfig(filename=f"{LOGS_DIR}/{datetime.now().strftime("%Y%m%d_%H%M")}_testing.log", level=logging.INFO)

def test_extract_plus_references():
    x_num: str = "X/9053/58N/4+N/8"
    scale: str = "One Inch"
    bn, bl, sid = ("58", "N", "4")
    entry: dict[str, str|None] = {}

    one_inch_plus = data.extract_plus_references(x_num=x_num, scale=scale, bl=bl, sid=sid, entry=entry)
    assert len(one_inch_plus) == 1
    assert one_inch_plus[0]["Post-1905 Block Number"] == "58"
    assert one_inch_plus[0]["Post-1905 Block Letter"] == "N"
    assert one_inch_plus[0]["Post-1905 Sheet ID"] == "8"


def test_create_label_map():
    lines = ["a", "b", "c", "d", "e"]
    labels = ["note", "note", "note", "note", "note"]

    with pytest.raises(ValueError):
        label_map = data.create_notes_map(lines=lines, labels=labels)

    lines = ["a", "b", "c", "d", "e"]
    labels = ["note", "ref", "note", "note", "ref"]

    label_map = data.create_notes_map(lines=lines, labels=labels)
    assert label_map == {1: "c\nd\na\n", 4: "a\n"}

    lines = ["a", "b", "c", "d", "e"]
    labels = ["ref", "ref", "note", "note", "ref"]

    label_map = data.create_notes_map(lines=lines, labels=labels)
    assert label_map == {0: "", 1: "c\nd\n", 4: ""}

    lines = ["a", "b", "a", "b"]
    labels = ["ref", "note", "ref", "note"]

    label_map = data.create_notes_map(lines=lines, labels=labels)
    assert label_map == {0: "b\n", 2: "b\n"}


def test_extract_references():
    row = pd.Series(  # Contrived row, not actually 38N/2
        {'Post-1905_1': "38N/2",
        'Post-1905_2': 'X/9053/38N/2 1909 /// ref\nSafi area only of Mohmand Country /// note\nX/9053/38N/2 1909/1918 /// ref\nSafi area only of Mohmand Country /// note',
        '1886-1905_1': "Punjab 51",
        '1886-1905_2': "X/9373/51  1901 /// ref\nPeshawar only /// note",
        'Pre-1886_1': "Peshawar",
        'Pre-1886_2': "see list for X/1748/1-11 /// note\nPeshawar only /// note"}
    )
    
    references = data.extract_references(row=row, periods=["Post-1905", "1886-1905", "Pre-1886"])

    expected = {
        "X/9053/38N/2 1909": {"Period": "Post-1905", "Notes": "Safi area only of Mohmand Country\nPre-1886 Peshawar: see list for X/1748/1-11\nPeshawar only"},
        "X/9053/38N/2 1909/1918": {"Period": "Post-1905", "Notes": "Safi area only of Mohmand Country\nPre-1886 Peshawar: see list for X/1748/1-11\nPeshawar only"},
        "X/9373/51  1901": {"Period": "1886-1905", "Notes": "Peshawar only\nPre-1886 Peshawar: see list for X/1748/1-11\nPeshawar only"}
    }

    assert references == expected


def test_process_6col_row():
    row = pd.Series(
        {'Post-1905_1': "38N/2",
        'Post-1905_2': 'X/9053/38N/2 1909 /// ref\nSafi area only of Mohmand Country /// note\nX/9053/38N/2 1909/1918 /// ref\nSafi area only of Mohmand Country /// note',
        '1886-1905_1': "Punjab 51",
        '1886-1905_2': "X/9373/51 1901 /// ref\nPeshawar only /// note",
        'Pre-1886_1': "Peshawar",
        'Pre-1886_2': "see list for X/1748/1-11 /// note\nPeshawar only /// note"}
    )
    source = "38A.doc"
    scale = "One Inch"
    metadata = {
        'Post-1905_header': 'Post-1905 India and Adjacent Countries map sheets: request by X number, adding dates where necessary to specify particular editions.  Where ‘no map’ is shown in this column, look in columns to the right for earlier map sheets of the same area at the same scale, and look in the Y/102 list for half-inch (1:126,720) maps and in the Y/104 list for quarter-inch (1:253,440) maps covering the same area at smaller scales.',
        '1886-1905_header': '1886-1905 Provincial standard sheets series map sheets: request by X number, adding dates where necessary to specify particular editions.  These are normally double-width sheets, each covering the area of two post-1905 sheets in the column to the left.  Where there is no entry in the column to the left, the map sheet in this column remained current for its area until at least 1941.',
        'Pre-1886_header': 'Pre-1886 published survey sheets on standard sheet lines: request by X number, adding dates where necessary to specify particular editions.  These are normally double-width sheets, each covering the area of two post-1905 sheets in the column to the far left.  Where there is no entry in the columns to the left, the map sheet in this column remained current for its area until at least 1941.  ‘See …’ notes refer to earlier published surveys at 1 inch to 1 mile not on standard sheet lines: consult the X list for information.',
        'Post-1905_footer': 'India and Adjacent Countries map sheets are compiled to modern (post-1905) longitude values, which are generally 2′30″ less than the incorrect pre-1905 values.',
        '1886-1905_footer': '‘Punjab’ denotes Punjab Survey or Punjab and North West Frontier Province Survey sheets.',
        'Pre-1886_footer': '‘Peshawar’ denotes Peshawar District survey sheets not on standard sheet lines.'
    }
    result = data.process_6col_row(row, source=source, scale=scale, metadata=metadata)

    expected_notes = "Safi area only of Mohmand Country\nPre-1886 Peshawar: see list for X/1748/1-11\nPeshawar only"
    expected_notes += f"\nSource period column header text: \n{metadata["Post-1905_header"]}\n"
    expected_notes += f"\nSource period column footer text: \n{metadata["Post-1905_footer"]}"

    expected = {
        "Source File": source,
        "Series Title": f"Survey of India India and Adjacent Countries {scale} Series",
        "Scale": {"Quarter Inch": "1:253,440", "Half Inch": "1:126,720", "One Inch": "63,360"}[scale],
        "Published": "Y",
        "Location Room": "UGF",
        "Location Section": None,  # dict lookup with external resource, out of scope currently, see Issue #2
        "Location Detail": None,  # dict lookup with external resource, out of scope currently, see Issue #2
        "Full Reference": "IOR/X/9053/38N/2",
        "Print Date": "1909",
        "Time Period": ">1905",
        "Parent Reference": "IOR/X/9053",
        "Post-1905 Related References": "X/9053/38N/2 1909/1918", # Introduced with Issue #3
        "1886-1905 Related References": "X/9373/51 1901", # Introduced with Issue #3
        "Pre-1886 Related References": "", # Introduced with Issue #3
        "Post-1905 Block Number": "38",
        "Post-1905 Block Letter": "N",
        "Post-1905 Sheet ID": "2",
        "1886-1905 New Sheet ID": "Punjab 51",
        "1886-1905 Old Sheet ID": None,
        "Pre-1886 New Sheet ID": "Peshawar",
        "Pre-1886 Old Sheet ID": None,
        "Sheet Title": None,
        "Edition Number": None,
        "Edition Date": "",
        "Designation_1": None,
        "Designation_2": None,
        "Publication Date": None,
        "Print Reference": None,
        "Copies Printed": None,
        "Coloured": None,
        "Gridded": None,
        "Number of Copies": None,
        "Repmat": None,
        "Latitude": None,
        "Longitude": None,
        "Available": None,
        "Notes": expected_notes
    }

    assert result[0] == expected


def test_bin_date():
    float_date = 1922.0
    str_date = "1933"
    int_date = 1944
    str_non_date = "See H6"

    mid_date = 1904
    pre_date = 1885

    float_res = data.bin_date(float_date)
    str_res = data.bin_date(str_date)
    int_res = data.bin_date(int_date)
    str_non_res = data.bin_date(str_non_date)

    mid_res = data.bin_date(mid_date)
    pre_res = data.bin_date(pre_date)

    assert float_res == "Post-1905"
    assert str_res == "Post-1905"
    assert int_res == "Post-1905"
    assert str_non_res is None

    assert mid_res == "1886-1905"
    assert pre_res == "Pre-1886"


def test_process_xlsx_row():
    
    test_row = pd.Series({
        "block_number": 3,
        "block_letter": "A",
        "sheet_id": 3,
        "date_1": 1945,
        "date_2": pd.NA,
        "date_3": pd.NA,
        "date_4": pd.NA,
        "date_5": pd.NA,
        "date_6": pd.NA,
        "drawer": 2956.0,
        "shelfmark": "X/14251",
        "coloured_1": "x",
        "coloured_2": pd.NA,
        "coloured_3": pd.NA,
        "coloured_4": pd.NA,
        "coloured_5": pd.NA,
        "coloured_6": pd.NA,
        "gridded_1": "x",
        "gridded_2": pd.NA,
        "gridded_3": pd.NA,
        "gridded_4": pd.NA,
        "gridded_5": pd.NA,
        "gridded_6": pd.NA,
        "copies_1": 2.0,
        "copies_2": pd.NA,
        "copies_3": pd.NA,
        "copies_4": pd.NA,
        "copies_5": pd.NA,
        "copies_6": pd.NA,
        "repmat": pd.NA,
        "notes": pd.NA
    })

    result = data.process_xlsx_row(row=test_row, source="TEST.xlsx", scale="One Inch")

    expected = [
    {
        "Source File": "TEST.xlsx",
        "Series Title": f"Survey of India India and Adjacent Countries One Inch Series",
        "Scale": "63,360",
        "Published": "Y",
        "Location Room": "UGF",
        "Location Section": None,  # dict lookup with external resource, out of scope currently, see Issue #2
        "Location Detail": 2956,  # dict lookup with external resource, out of scope currently, see Issue #2
        "Full Reference": "IOR/X/14251/3A/3",
        "Print Date": "1945",
        "Time Period": ">1905",
        "Parent Reference": "IOR/X/14251",
        "Post-1905 Related References": "", # Introduced with Issue #3
        "1886-1905 Related References": "", # Introduced with Issue #3
        "Pre-1886 Related References": "", # Introduced with Issue #3
        "Post-1905 Block Number": "3",
        "Post-1905 Block Letter": "A",
        "Post-1905 Sheet ID": "3",
        "1886-1905 New Sheet ID": None,
        "1886-1905 Old Sheet ID": None,
        "Pre-1886 New Sheet ID": None,
        "Pre-1886 Old Sheet ID": None,
        "Sheet Title": None,
        "Edition Number": None,
        "Edition Date": "",
        "Designation_1": None,
        "Designation_2": None,
        "Publication Date": None,
        "Print Reference": None,
        "Copies Printed": None,
        "Coloured": "Y",
        "Gridded": "Y",
        "Number of Copies": '2',
        "Repmat": pd.NA,
        "Latitude": None,
        "Longitude": None,
        "Available": None,
        "Notes": pd.NA
    }
    ]

    assert result == expected


def test_parse_see():
    test_df = pd.DataFrame(data={
        "Print Date": ["1946", "See A 1 1946", "seea1", "see block 3 a 1", "seea1"],
        "Post-1905 Block Number": ["3", "3", "3", "6", "7"],
        "Post-1905 Block Letter": ["A", "A", "A", "A", "A"],
        "Post-1905 Sheet ID": ["1", "1", "1", "1", "1"],
        "Location Detail": [10, 10, 10, 10, 20]
    },
    index=pd.RangeIndex(0, 5)
    )
    
    result_df = test_df.copy()

    data.parse_see(idx=1, row=test_df.loc[1], df_copy=result_df)
    assert result_df.loc[1, "Print Date"] == "See 3 A1 1946"

    data.parse_see(idx=2, row=test_df.loc[2], df_copy=result_df)
    assert result_df.loc[2, "Print Date"] == "See 3 A1"

    data.parse_see(idx=3, row=test_df.loc[3], df_copy=result_df)
    assert result_df.loc[3, "Print Date"] == "See 3 A1"

    with pytest.raises(ValueError):
        data.parse_see(idx=4, row=test_df.loc[4], df_copy=result_df)
        assert result_df.loc[4, "Print Date"] == "See 3 A1"


def test_combine_doc_xlsx_outputs():
    xlsx_df = pd.DataFrame(data={
        "Full Reference": ["IOR/X/14251/3A/1", "IOR/X/14251/3Z/1", "IOR/X/14251/3B/1", "IOR/X/14251/3C/1"],
        "Location Detail": [10, "3107/3108", "3107/3108", pd.NA],
        "Print Date": ["1946", "1947", "1948", "1949"],
        "Post-1905 Block Number": ["3", "6", "6", "7"],
        "Post-1905 Block Letter": ["A", "A", "A", "A"],
        "Post-1905 Sheet ID": ["1", "1", "1", "1"],
        "Coloured": ["Y", "Y", "N", "Y"], 
        "Gridded": ["N", "Y", "Y", "N"], 
        "Number of Copies": ["1", pd.NA, "2", "3"], 
        "Repmat": [pd.NA, pd.NA, "2 Copies", pd.NA], 
        "Notes": ["a", pd.NA, "b", "c"]
    },
    index=pd.RangeIndex(0, 4)
    )
    xlsx_df = xlsx_df.convert_dtypes()

    doc_df = pd.DataFrame(data={
        "Full Reference": ["IOR/X/14251/3A/1", "IOR/X/14251/3Z/1", "IOR/X/14251/3C/1"],
        "Location Detail": [pd.NA, pd.NA, pd.NA],
        "Print Date": ["1946", "1947", "1948"],
        "Post-1905 Block Number": ["3", "6", "7"],
        "Post-1905 Block Letter": ["A", "A", "A"],
        "Post-1905 Sheet ID": ["1", "1", "1"],
        "Coloured": [pd.NA, pd.NA, pd.NA], 
        "Gridded": [pd.NA, pd.NA, pd.NA], 
        "Number of Copies": [pd.NA, pd.NA, pd.NA], 
        "Repmat": [pd.NA, pd.NA, pd.NA], 
        "Notes": ["1", "2", "3"]
    },
    index=pd.RangeIndex(0, 3)
    )
    doc_df = doc_df.convert_dtypes()

    result = data.combine_doc_xlsx_outputs(doc_df=doc_df, xlsx_df=xlsx_df)

    expected = pd.DataFrame(data={
        "Full Reference": ["IOR/X/14251/3A/1", "IOR/X/14251/3Z/1", "IOR/X/14251/3C/1", "IOR/X/14251/3B/1", "IOR/X/14251/3C/1"],
        "Location Detail": [10, "3107/3108", pd.NA, "3107/3108", pd.NA],
        "Print Date": ["1946", "1947", "1948", "1948", "1949"],
        "Post-1905 Block Number": [3, 6, 7, 6, 7],
        "Post-1905 Block Letter": ["A", "A", "A", "A", "A"],
        "Post-1905 Sheet ID": [1, 1, 1, 1, 1],
        "Coloured": ["Y", "Y", pd.NA, "N", "Y"], 
        "Gridded": ["N", "Y", pd.NA, "Y", "N"], 
        "Number of Copies": ["1", pd.NA, pd.NA, "2", "3"], 
        "Repmat": [pd.NA, pd.NA, pd.NA, "2 Copies", pd.NA], 
        "Notes": ["1\n\nNotes copied from xlsx source file\na", "2", "3", "b", "c"]
    },
    index=pd.RangeIndex(0, 5)
    )
    expected = expected.convert_dtypes()

    assert result.shape == expected.shape
    assert result.columns.equals(expected.columns)
    assert result.dtypes.equals(expected.dtypes)
    assert result.equals(expected)