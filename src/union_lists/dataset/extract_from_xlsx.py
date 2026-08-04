import pandas as pd


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

    df = df.iloc[5:].reset_index(drop=True)
    df.columns = columns

    if file_id == "Block 86Template":
        file_id = "Block 86"

    block_number = file_id.split()[1]
    df["block_number"] = block_number
    
    return df
