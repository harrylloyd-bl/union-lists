import datetime
import glob
import os
import re

import pandas as pd
from pandas.api.types import is_string_dtype

from union_lists.config import RAW_DATA_DIR, INTERIM_DATA_DIR


def copy_to_col(df: pd.DataFrame, idx: pd.Index|list[int|str], source: str, destination: str) -> None:
    """Copy values from one column to another and clear the copied from cells

    Args:
        df (pd.DataFrame): Dataframe to operate on
        idx (pd.Index): row index cells to operate on
        col_1 (str): source column
        col_2 (str): destination column

    Returns:
        None
    """
    if destination == "notes":
        if not is_string_dtype(df[destination].dtype):
            raise ValueError("Notes column doesn't have string dtype")
        
        if df.loc[idx, destination].isna().any():
            raise ValueError("NaN values in Notes column won't be copied to correctly")
        
        non_empty_notes = df.loc[idx][df.loc[idx, destination] != ""].index
        
        df.loc[non_empty_notes, "notes"] += "\n"
        df.loc[idx, destination] += f"Note copied from {source.capitalize().replace("_", " ")}: " + df.loc[idx, source].astype(str)
    else:
        df.loc[idx, destination] = df.loc[idx, source].astype(df[destination].dtype)
        if df.loc[idx, destination].isna().any():
            raise ValueError(f"Some copied entries are NaN, check dtypes: col_1 has dtype {df[source].dtype}; col_2 has dtype {df[destination].dtype}")

    df.loc[idx, source] = pd.NA
    return None


def clean_dates(dates: pd.Series) -> pd.Series:
    """Clean a date column
    Fix 5 character length years
    Replace some known erroneous strings in dates

    Args:
        dates (pd.Series): Date column from a dataframe to operate on

    Returns:
        pd.Series: Cleaned date column
    """
    dates = dates.where(lambda x: x != ".").where(lambda x: x != "                         ").where(lambda x: x != ' ')
    
    # most inclusions of '6' in a date are erroneous, appart from three 1966 dates in Block 94
    five_char_date_re = re.compile(r"\d{5,5}")
    fcd_index = dates.dropna()[~dates.dropna().apply(lambda x: five_char_date_re.match(x)).isna()].index
    dates.loc[fcd_index] = dates.loc[fcd_index].str.replace("196", "19")

    dates = dates.str.replace("219", "19").str.replace("`", "")
    return dates


def clean_coloured(coloured: pd.Series) -> pd.Series:
    """Clean a Coloured column
    Replace z -> x
    Deduplicate xx -> x
    apply .lower()
    Strip trailing hyphens
    Convert 0 and - to x (have checked in source that this is appropriate)

    Args:
        dates (pd.Series): Date column from a dataframe to operate on

    Returns:
        pd.Series: Cleaned date column
    """    
    coloured = coloured.str.lower().str.strip()
    coloured = coloured.replace("z", "x").str.replace("0", "x").str.replace("xx", "x")
    coloured = coloured.str.replace("^-$", "x", regex=True).str.replace("x-", "x")
    coloured = coloured.where(lambda x: x != ".")
    return coloured


def clean_gridded(gridded: pd.Series) -> pd.Series:
    """Clean a Gridded column
    Replace xx -> x
    apply .strip()
    Convert spaces to pd.NA

    Args:
        dates (pd.Series): Date column from a dataframe to operate on

    Returns:
        pd.Series: Cleaned date column
    """    
    gridded = gridded.where(lambda x: x != " ")
    gridded = gridded.str.strip()
    gridded = gridded.str.replace("xx", "x")
    return gridded


def clean_copies(copies: pd.Series) -> pd.Series:
    """Clean a Copies column
    Replace x -> 1

    Args:
        copies (pd.Series): Copies column from a dataframe to operate on

    Returns:
        pd.Series: Cleaned Copies column
    """
    copies = copies.str.strip()
    copies = copies.str.replace("x$", "1", regex=True)
    copies = copies.str.replace(".0", "")  # fix floats
    return copies


def apply_manual_corrections(df: pd.DataFrame, file_id: str) -> tuple[pd.DataFrame, str]:
    """Apply a series of manual corrections to the source files
    In general for edge cases with one or at most several members

    Args:
        df (pd.DataFrame): Dataframe to apply correction to
        file_id (str): file id to select which corrections to apply

    Returns:
        tuple[pd.DataFrame, str]: Corrected dataframe and file id
    """

    # TODO verify all assertions
    if file_id == "Block 3":
        assert df.loc[185, "date_2"] == "see L11/2"
        df.loc[185, "date_2"] = "see L11 1957"

    elif file_id == "Block 34":
        assert df.loc[263, "copies_2"] == datetime.datetime(year=2017, month=3, day=2)
        df.loc[263, "copies_2"] = "2/3"

    elif file_id == "Block 38":
        assert df.loc[148, "date_1"] == "1943 See 38 K1"
        df.loc[148, "date_1"] = 1943
        df.loc[148, "notes"] = "Note added during processing: `Date 1` column read '1943 See 38 K1'"

        assert df.loc[160, "date_1"] == "1943 See 38 j13"
        df.loc[160, "date_1"] = 1943
        df.loc[160, "notes"] = "Note added during processing: `Date 1` column read '1943 See 38 J13'"

        assert df.loc[172, "gridded_2"] == "`"
        df.loc[172, "gridded_2"] = pd.NA

    elif file_id == "Block 39":
        assert df.loc[85, "date_2"] == "1928 See D10"
        df.loc[85, "date_2"] = 1928
        df.loc[85, "notes"] = "Note added during processing: `Date 2` column read '1928 See D10'"

    elif file_id == "Block 43":
        assert df.loc[237, "date_1"] == "See 43 F9 Drawer435"
        df.loc[237, "date_1"] = "See 43 F9"

        assert df.loc[282, "date_1"] == "1932 See F12"
        df.loc[282, "date_1"] = 1932
        df.loc[282, "notes"] = "Note added during processing: `Date 1` column read '1932 See F12'"

    elif file_id == "Block 44":
        assert df.loc[50, "date_1"] == "14  See A10 1908"
        df.loc[50, "date_1"] = "See A10 1908"

        assert df.loc[452, "date_1"] == "1936 See 44 P2"
        df.loc[452, "date_1"] = 1936
        df.loc[452, "notes"] = "Note added during processing: `Date 1` column read '1936 See 44 P2'"

    elif file_id == "Block 45":
        assert df.loc[64, "date_1"] == "1946 See H3 and H7"
        df.loc[64, "date_1"] = 1946
        df.loc[64, "notes"] = "Note added during processing: `Date 1` column read '1946 See H3 and H7'"

        assert df.loc[156, "date_1"] == "1947 See H3"
        df.loc[156, "date_1"] = 1947
        df.loc[156, "notes"] = "Note added during processing: `Date 1` column read '1947 See H3'"

    elif file_id == "Block 53":
        assert df.loc[383, "date_1"] == "Se 53 H3"
        df.loc[383, "date_1"] = "See 53 H3"

        assert df.loc[486, "date_1"] == "See mK4"
        df.loc[486, "date_1"] = "See K4"

        assert df.loc[121, "date_4"] == 2
        df.loc[121, "date_4"] = pd.NA
        df.loc[121, "notes"] = "Note added during processing: 2 recorded in source `Date 4` column, erroneous but possibly indicating two copies of this map\n"

    elif file_id == "Block 54":
        assert df.loc[205, "drawer"] == "410-"
        df.loc[205, "drawer"] = 410

    elif file_id == "Block 55":
        assert df.loc[202, "date_1"] == r"\see F9"
        df.loc[202, "date_1"] = "See F9"

    elif file_id == "Block 57":
        assert df.loc[342, "date_1"] == 19141
        df.loc[342, "date_1"] = 1914

    elif file_id == "Block 58":
        assert df.loc[386, "date_1"] == "19 28"
        df.loc[386, "date_1"] = "1928"

    elif file_id == "Block 62":
        assert df.loc[[72, 75, 78, 82, 85, 88], "repmat"].to_list() == ["   2copies", 2, 2, 2, 2, 2]
        df.loc[[72, 75, 78, 82, 85, 88], "repmat"] = ["2 copies", "2 copies", "2 copies", "2 copies", "2 copies", "2 copies"]
        df["notes"] = ""

    elif file_id == "Block 63":
        # block_letter col in wrong place
        df["block_letter"] = df["block_number"]

        assert df.loc[17, "date_1"] == "6      See A2 1907"
        df.loc[17, "date_1"] = "See A2 1907"

        assert df.loc[95, "date_1"] == "14 S ee B10 1906"
        df.loc[95, "date_1"] = "See B10 1906"

        assert df.loc[264, "date_1"] == "See E!!"
        df.loc[264, "date_1"] = "See E11"

    elif file_id == "Block 64":
        assert df.loc[496, "date_1"] == "M15     See Block 73 A3"
        df.loc[496, "date_1"] = "See Block 73 A3"

        assert pd.isna(df.loc[506, "date_1"])
        df.loc[506, "date_1"] = "See Block 73 A3"

    elif file_id == "Block 65":
        assert df.loc[403, "date_2"] == "O2/O3/O6 all on same map"
        df.loc[403, "date_2"] = pd.NA
        df.loc[403, "notes"] = "Note copied from Date 1: O2/O3/O6 all on same map\n"

        assert df.loc[406, "date_1"] == "See O2"
        df.loc[406, "date_1"] = 1933
        df.loc[406, "notes"] = "Note copied from Date 1: O2/O3/O6 all on same map\n"

        assert df.loc[411, "date_1"] == "See O2"
        df.loc[411, "date_1"] = 1933
        df.loc[411, "notes"] = "Note copied from Date 1: O2/O3/O6 all on same map\n"

    elif file_id == "Block 72":
        assert df.loc[263, "date_1"] == 19174
        df.loc[263, "date_1"] = 1917

        assert df.loc[250, "date_1"] == "See G10        1935"
        df.loc[250, "date_1"] = "See G10"

        assert df.loc[251, "date_1"] == "See G10        1935"
        df.loc[251, "date_1"] = "See G10"

    elif file_id == "Block 73":
        assert df.loc[192, "date_1"] == "6          1929?1928"
        df.loc[192, "date_1"] = "1929?1928"

        assert df.loc[458, "date_1"] == "15            See L11"
        df.loc[458, "date_1"] = "See L11"

        assert df.loc[549, "date_1"] == "1          See 73 L13"
        df.loc[549, "date_1"] = "See 73 L13"

        assert df.loc[550, "date_1"] == "1           See 73 L14"
        df.loc[550, "date_1"] = "See 73 L14"

        assert df.loc[8, "date_1"] == "See Block 64 M15"
        df = df.drop(index=8)

    elif file_id == "Block 78":
        assert df.loc[87, "date_1"] == "Saee D4"
        df.loc[87, "date_1"] = "See D4"

        # Mistaken 0 due to a formula being used for this specific cell
        assert df.loc[287, "gridded_1"] == 0
        df.loc[287, "gridded_1"] = pd.NA


    elif file_id == "Block 83":
        assert df.loc[95, "shelfmark"] == "X`14202"
        df.loc[95, "shelfmark"] = "X14202"

    elif file_id == "Block 84":
        assert df.loc[41, "drawer"] == "?1955"
        df.loc[41, "drawer"] = "3107/3108"

        assert df.loc[41, "repmat"] == " 3107/3108"
        df.loc[41, "repmat"] = pd.NA
        df.loc[41, "copies_1"] += " 3107/3108"

        assert df.loc[586, "date_1"] == "P3 includes part of 84 P7 and part  of 84 L15"
        assert df.loc[570, "date_1"] == "1903-1938"
        df.loc[570, "notes"] = "Note copied from Date 1: P3 includes part of 84 P7 and part of 84 L15\n"
        df = df.drop(index=[585, 586])

    elif file_id == "Block 86template":
        file_id = "Block 86"

    elif file_id == "Block 92":
        assert df.loc[115, "date_1"] == "1944 See F15"
        df.loc[115, "date_1"] = 1944
        df.loc[115, "notes"] = "Note added during processing: `Date 1` column read '1944 See F15'"

    elif file_id == "Block 93":
        assert df.loc[402, "date_1"] == 145
        df.loc[402, "date_1"] = 1945

    elif file_id == "Block 94":
        assert df.loc[309, "date_1"] == 19271927
        df.loc[309, "date_1"] = 1927

        assert df.loc[319, "date_1"] == "SeeH6/1926"
        df.loc[319, "date_1"] = "SeeH6 1926"

        assert df.loc[53, "date_2"] == datetime.datetime(year=1907, month=6, day=1)
        df.loc[53, "date_2"] = 1907

        assert df.loc[54, "date_2"] == datetime.datetime(year=1905, month=4, day=28)
        df.loc[54, "date_2"] = 1905

        assert df.loc[55, "date_2"] == datetime.datetime(year=1905, month=3, day=30)
        df.loc[55, "date_2"] = 1905

    return df, file_id


def pre_process_xlsx(df: pd.DataFrame, file_id: str) -> pd.DataFrame:
    columns = [
        'block_number', 'block_letter', 'sheet_id', 'date_1', 'date_2', 'date_3',
        'date_4', 'date_5', 'date_6', 'drawer', 'shelfmark', 'coloured_1',
        'coloured_2', 'coloured_3', 'coloured_4', 'coloured_5',
        'coloured_6', 'gridded_1', 'gridded_2', 'gridded_3',
        'gridded_4', 'gridded_5', 'gridded_6', 'copies_1',
        'copies_2', 'copies_3', 'copies_4', 'copies_5',
        'copies_6', 'repmat', 'notes'
    ]

    if df.shape[1] == 30:
        df['notes'] = ""

    file_id = file_id.capitalize()

    df = df.iloc[5:].reset_index(drop=True)
    df.columns = columns

    na_notes_idx = df["notes"][df["notes"].isna()].index
    df["notes"] = df["notes"].astype(str)
    df.loc[na_notes_idx, "notes"] = ""

    df, file_id = apply_manual_corrections(df, file_id)

    block_number = file_id.split()[1]
    df["block_number"] = block_number
    df["block_number"] = df["block_number"].astype(int)
    df["block_letter"] = df["block_letter"].astype(str)
    df["sheet_id"] = df["sheet_id"].astype("Int64")
    df["drawer"] = df["drawer"].astype("str")
    df["shelfmark"] = df["shelfmark"].astype("str")
    
    # block_letter_re = re.compile("[A-P]$")
    # sheet_id_re = re.compile(r"\d{1,2}$")
    # date_re = re.compile(r"\d{4,4}$")
    # drawer_re = re.compile(r"[0-9/]+$")
    # shelfmark_re = re.compile(r"[xXD0-9\[\]]+$")
    grid_color_re = re.compile(r"x$")
    copy_re = re.compile(r"[\d/]{1,3}$|S$")

    for i in range(1, 7):
        df[f"date_{i}"] = clean_dates(df[f"date_{i}"].astype(str))
        # TODO convert to int if forcing all hyphen/? dates to pure date
        # df[f"date_{i}"] = df[f"date_{i}"].astype("Int64")

        df[f"coloured_{i}"] = clean_coloured(df[f"coloured_{i}"].astype(str))
        df[f"gridded_{i}"] = clean_gridded(df[f"gridded_{i}"].astype(str))
        df[f"copies_{i}"] = clean_copies(df[f"copies_{i}"].astype(str))

        bad_coloured = df.dropna(subset=f"coloured_{i}")[df[f"coloured_{i}"].dropna().apply(lambda x: grid_color_re.match(x)).isna()]
        if not bad_coloured.empty:
            # breakpoint()
            raise ValueError(f"Incorrectly formatted Coloured entries at idx: {bad_coloured.index}")

        # breakpoint()
        grid_idx_to_copy = df.dropna(subset=f"gridded_{i}")[df[f"gridded_{i}"].dropna().apply(lambda x: grid_color_re.match(x)).isna()].index
        copy_to_col(df, grid_idx_to_copy, f"gridded_{i}", "notes")
        bad_gridded = df.dropna(subset=f"gridded_{i}")[df[f"gridded_{i}"].dropna().apply(lambda x: grid_color_re.match(x)).isna()]
        if not bad_gridded.empty:
            raise ValueError(f"Incorrectly formatted Gridded entries at idx: {bad_gridded.index}")

        # breakpoint()
        copies_idx_to_copy = df.dropna(subset=f"copies_{i}")[df[f"copies_{i}"].dropna().apply(lambda x: copy_re.match(x)).isna()].index
        copy_to_col(df, copies_idx_to_copy, f"copies_{i}", "notes")
        bad_copies = df.dropna(subset=f"copies_{i}")[df[f"copies_{i}"].dropna().apply(lambda x: copy_re.match(x)).isna()]
        if not bad_copies.empty:
            raise ValueError(f"Incorrectly formatted Copies entries at idx: {bad_copies.index}")

    for col in df.columns:
        if is_string_dtype(df[col]):
            df[col] = df[col].str.strip()

    df["notes"] = df["notes"].where(df["notes"] != "")

    block_letter_re = re.compile("[A-P]")
    idx_to_copy = df.dropna(subset="block_letter")[df["block_letter"].dropna().apply(lambda x: block_letter_re.match(x)).isna()].index
    copy_to_col(df, idx_to_copy, "block_letter", "date_1")

    bad_block_letters = df.dropna(subset="block_letter")[df["block_letter"].dropna().apply(lambda x: block_letter_re.match(x)).isna()]
    if not bad_block_letters.empty:
        raise ValueError(f"Incorrectly formatted block letters at idx: {bad_block_letters.index}")

    # ffill has to come after regex check on columns
    df["block_letter"] = df["block_letter"].ffill()

    sheet_id_re = re.compile(r"\d{1,2}")
    bad_sheet_ids = df.dropna(subset="sheet_id")[df["sheet_id"].dropna().astype(str).apply(lambda x: sheet_id_re.match(x)).isna()]
    if not bad_sheet_ids.empty:
        raise ValueError(f"Incorrectly formatted sheet ids at idx: {bad_sheet_ids.index}")

    df["sheet_id"] = df["sheet_id"].ffill()

    df["shelfmark"] = df["shelfmark"].str.upper().str.replace("X", "X/")

    return df


def annotate_uncertain_dates(df: pd.DataFrame) -> pd.DataFrame:
    # TODO pass any dates with question marks to the notes column
    return df


if __name__ == "__main__":
    SCALE = "One Inch"
    xlsx_files = glob.glob(f"{RAW_DATA_DIR}/{SCALE}/*.xlsx")
    xlsx_files = [x for x in xlsx_files if "\\~" not in x and "(2)" not in x]
    dfs = {os.path.basename(x).split(".")[0]: pd.read_excel(x) for x in xlsx_files}
    clean_dfs = {block: pre_process_xlsx(df, block) for block, df in dfs.items()}
    [df.to_csv(f"{INTERIM_DATA_DIR}/{SCALE}/{block}.csv", encoding="utf-8-sig", index=False) for block, df in clean_dfs.items()]