from collections import Counter
from copy import deepcopy
from datetime import datetime
import glob
import logging
import json
import os
import xml.etree.ElementTree as ET

from docx import Document
import pandas as pd
from tqdm import tqdm
import win32com.client as win32

import union_lists.dataset.reformat_union_lists as data
from union_lists.config import INTERIM_DATA_DIR, PROCESSED_DATA_DIR, LOGS_DIR

logger = logging.getLogger(__name__)
logging.basicConfig(filename=f"{LOGS_DIR}/{datetime.now().strftime("%Y%m%d_%H%M")}_main.log", level=logging.INFO)

def main():
    SCALE = "One Inch"
    print(f"{SCALE}: Reformating tables to new data format")
    block_suffix = {"One Inch": "A", "Half Inch": "B", "Quarter Inch": "C"}[SCALE]
    csv_files = glob.glob(f"{INTERIM_DATA_DIR}/{SCALE}/*.csv")
    scale_docs = {"Quarter Inch": 38, "Half Inch": 34, "One Inch": 40}
    assert len(csv_files) == scale_docs[SCALE]

    input_dfs, metadatas = {}, {}
    for f in csv_files:
        file_id = os.path.basename(f).split(".")[0] + ".doc"
        df = pd.read_csv(f, encoding="utf8").dropna(how="all")
        with open(f[:-4] + ".json") as g:
            metadata = json.load(g)
        input_dfs[file_id] = data.pre_process_df(df)
        metadatas[file_id] = metadata

    data.fix_data_errors(input_dfs)

    entry_dfs = {}
    with tqdm(input_dfs.items(), total=scale_docs[SCALE]) as t:
        for file_id, df in t:
            t.set_description(file_id)
            # print(file_id)
            entries = []
            if df.columns.equals(pd.Index(['Post-1905_1', 'Post-1905_2', '1886-1905_1', '1886-1905_2', 'Pre-1886_1', 'Pre-1886_2'])):
                [entries.extend(data.process_6col_row(row[1], source=file_id, scale=SCALE, metadata=metadatas[file_id])) for row in df.iterrows()]
                entry_df = pd.concat([pd.DataFrame(x, index=[0]) for x in entries]).reset_index(drop=True)
                entry_dfs[file_id] = entry_df
    
    for file_id, df in input_dfs.items():
        if "Y" in file_id and df.columns.equals(pd.Index(["Post-1905_1", "metadata"])):
            target = file_id.split()[1]
            target_df = entry_dfs[target + f"{block_suffix}.doc"]
            [data.process_2col_row(row=row, source=file_id, target_df=target_df, scale=SCALE) for (_, row) in df.iterrows()]

    output = pd.concat([df for df in entry_dfs.values()])

    # output.to_csv(f"{PROCESSED_DATA_DIR}/v0.7_{scale.lower().replace(' ', '_')}_sample.csv", encoding="utf-8-sig", index=False)
    # output.to_excel(f"{PROCESSED_DATA_DIR}/v0.7_{scale.lower().replace(' ', '_')}_sample.xlsx", index=False)

    data.validate_output(df_input=input_dfs, output=output)


if __name__ == "__main__":
    main()