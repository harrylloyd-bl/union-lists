import datetime
import glob
import os
import re

import pandas as pd
from pandas.api.types import is_string_dtype

from union_lists.config import RAW_DATA_DIR


def copy_to_col(df: pd.DataFrame, idx: pd.Index, col_1: str, col_2: str) -> None:
    """Copy values from one column to another and clear the copied from cells

    Args:
        df (pd.DataFrame): Dataframe to operate on
        idx (pd.Index): row index cells to operate on
        col_1 (str): source column
        col_2 (str): destination column

    Returns:
        None
    """
    df.loc[idx, col_2] = df.loc[idx, col_1]
    df.loc[idx, col_1] = pd.NA
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
    Convert 0/- to x (have checked in source that this is appropriate)

    Args:
        dates (pd.Series): Date column from a dataframe to operate on

    Returns:
        pd.Series: Cleaned date column
    """    
    coloured = coloured.str.lower()
    coloured = coloured.replace("z", "x").str.replace("0", "x").str.replace("xx", "x")
    coloured = coloured.str.replace("^-$", "x", regex=True).str.replace("x-", "x")
    coloured = coloured.where(lambda x: x != ".")
    return coloured


def clean_gridded(gridded: pd.Series) -> pd.Series:
    """Clean a Gridded column
    Replace z -> x
    apply .lower()
    Strip trailing hyphens

    Args:
        dates (pd.Series): Date column from a dataframe to operate on

    Returns:
        pd.Series: Cleaned date column
    """    
    gridded = gridded.str.replace("xx", "x")
    gridded = gridded.where(lambda x: x != " ")
    return gridded

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
        df['notes'] = pd.NA

    file_id = file_id.capitalize()

    df = df.iloc[5:].reset_index(drop=True)
    df.columns = columns
    df["notes"] = df["notes"].astype(str)

    if file_id == "Block 38":
        assert df.loc[172, "gridded_2"] == "`"
        df.loc[172, "gridded_2"] = pd.NA

    if file_id == "Block 53":
        assert df.loc[383, "date_1"] == "Se 53 H3"
        df.loc[383, "date_1"] = "See 53 H3"

        assert df.loc[121, "date_4"] == 2
        df.loc[121, "date_4"] = pd.NA
        df.loc[121, "notes"] = "2 recorded in source `Date 4` column, erroneous but possibly indicating two copies of this map"

    if file_id == "Block 54":
        assert df.loc[205, "drawer"] == "410-"
        df.loc[205, "drawer"] = 410

    if file_id == "Block 57":
        assert df.loc[342, "date_1"] == 19141
        df.loc[342, "date_1"] = 1914

    if file_id == "Block 58":
        assert df.loc[386, "date_1"] == "19 28"
        df.loc[386, "date_1"] = "1928"

    if file_id == "Block 63":
        # block_letter col in wrong place
        df["block_letter"] = df["block_number"]

    if file_id == "Block 65":
        assert df.loc[403, "date_2"] == "O2/O3/O6 all on same map"
        df.loc[403, "date_2"] = pd.NA
        df.loc[403, "notes"] = "O2/O3/O6 all on same map"

        assert df.loc[406, "date_1"] == "See O2"
        df.loc[406, "date_1"] = 1933
        df.loc[406, "notes"] = "O2/O3/O6 all on same map"

        assert df.loc[411, "date_1"] == "See O2"
        df.loc[411, "date_1"] = 1933
        df.loc[411, "notes"] = "O2/O3/O6 all on same map"

    if file_id == "Block 72":
        assert df.loc[263, "date_1"] == 19174
        df.loc[263, "date_1"] = 1917

    if file_id == "Block 73":
        assert df.loc[192, "date_1"] == "6          1929?1928"
        df.loc[192, "date_1"] = "1929?1928"

    if file_id == "Block 78":
        # Mistaken 0 due to a formula being used for this specific cell
        assert df.loc[287, "gridded_1"] == 0
        df.loc[287, "gridded_1"] = pd.NA

    if file_id == "Block 83":
        assert df.loc[95, "shelfmark"] == "X`14202"
        df.loc[95, "shelfmark"] = "X14202"

    if file_id == "Block 84":
        assert df.loc[586, "date_1"] == "P3 includes part of 84 P7 and part  of 84 L15"
        assert df.loc[570, "date_1"] == "1903-1938"
        df.loc[570, "notes"] = "P3 includes part of 84 P7 and part of 84 L15"
        df = df.drop(index=[585, 586])

    if file_id == "Block 86template":
        file_id = "Block 86"

    if file_id == "Block 93":
        assert df.loc[402, "date_1"] == 145
        df.loc[402, "date_1"] = 1945

    if file_id == "Block 94":
        assert df.loc[309, "date_1"] == 19271927
        df.loc[309, "date_1"] = 1927

        assert df.loc[53, "date_2"] == datetime.datetime(year=1907, month=6, day=1)
        df.loc[53, "date_2"] = 1907

        assert df.loc[54, "date_2"] == datetime.datetime(year=1905, month=4, day=28)
        df.loc[54, "date_2"] = 1905

        assert df.loc[55, "date_2"] == datetime.datetime(year=1905, month=3, day=30)
        df.loc[55, "date_2"] = 1905


    block_number = file_id.split()[1]
    df["block_number"] = block_number
    df["block_number"] = df["block_number"].astype(int)
    df["block_letter"] = df["block_letter"].astype(str)
    df["sheet_id"] = df["sheet_id"].astype("Int64")
    df["drawer"] = df["drawer"].astype("str")
    df["shelfmark"] = df["shelfmark"].astype("str")
    
    grid_color_re = re.compile(r"x$")

    for i in range(1, 7):
        df[f"date_{i}"] = df[f"date_{i}"].astype("str")
        df[f"date_{i}"] = clean_dates(df[f"date_{i}"])
        # TODO convert to int if forcing all hyphen/? dates to pure date
        # df[f"date_{i}"] = df[f"date_{i}"].astype("Int64")

        df[f"coloured_{i}"] = df[f"coloured_{i}"].astype("str")
        df[f"coloured_{i}"] = clean_coloured(df[f"coloured_{i}"])

        df[f"gridded_{i}"] = df[f"gridded_{i}"].astype("str")
        df[f"gridded_{i}"] = clean_gridded(df[f"gridded_{i}"])

        grid_idx_to_copy = df[f"gridded_{i}"].astype(str).dropna().apply(lambda x: grid_color_re.match(x)).isna().index
        copy_to_col(df, grid_idx_to_copy, f"gridded_{i}", "notes")
        bad_gridded = df.dropna(subset=f"gridded_{i}").loc[:,:f"gridded_{i}"][df[f"gridded_{i}"].astype(str).dropna().apply(lambda x: grid_color_re.match(x)).isna()]
        if not bad_gridded.empty:
            raise ValueError(f"Incorrectly formatted Gridded entries at idx: {bad_gridded.index}")

    for col in df.columns:
        if is_string_dtype(df[col]):
            df[col] = df[col].str.strip()

    block_letter_re = re.compile("[A-P]")
    idx_to_copy = df.dropna(subset="block_letter")[df["block_letter"].dropna().apply(lambda x: block_letter_re.match(x)).isna()].index
    copy_to_col(df, idx_to_copy, "block_letter", "date_1")
    bad_block_letters = df.dropna(subset="block_letter")[df["block_letter"].dropna().apply(lambda x: block_letter_re.match(x)).isna()]
    if not bad_block_letters.empty:
        raise ValueError(f"Incorrectly formatted block letters at idx: {bad_block_letters.index}")
    # ffill has to come after regex check on columns
    # df["block_letter"] = df["block_letter"].ffill()

    sheet_id_re = re.compile(r"\d{1,2}")
    bad_sheet_ids = df.dropna(subset="sheet_id")[df["sheet_id"].dropna().astype(str).apply(lambda x: sheet_id_re.match(x)).isna()]
    if not bad_sheet_ids.empty:
        raise ValueError(f"Incorrectly formatted sheet ids at idx: {bad_sheet_ids.index}")
    # df["sheet_id"] = df["sheet_id"].ffill()

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