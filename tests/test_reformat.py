import pytest
from pytest import raises
import pandas as pd
from union_lists.dataset import reformat_union_lists as data


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

    result = data.process_xlsx_row(row=test_row, source="TEST.xlsx", scale="One Inch", combined_df=pd.DataFrame())

    expected = [
    {
        "Source File": "TEST.xlsx",
        "Series Title": f"Survey of India India and Adjacent Countries One Inch Series",
        "Scale": "63,360",
        "Published": "Y",
        "Location Room": "UGF",
        "Location Section": None,  # dict lookup with external resource, out of scope currently, see Issue #2
        "Location Detail": None,  # dict lookup with external resource, out of scope currently, see Issue #2
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
        "Coloured": True,
        "Gridded": True,
        "Number of Copies": '2',
        "Repmat": pd.NA,
        "Latitude": None,
        "Longitude": None,
        "Available": None,
        "Notes": pd.NA
    }
    ]

    assert result == expected