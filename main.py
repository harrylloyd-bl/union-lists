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
from union_lists.config import RAW_DATA_DIR, INTERIM_DATA_DIR, PROCESSED_DATA_DIR, LOGS_DIR

logger = logging.getLogger(__name__)
logging.basicConfig(filename=f"{LOGS_DIR}/{datetime.now().strftime("%Y%m%d_%H%M")}_main.log", level=logging.INFO)

PARSE_DOCX = True
PARSE_XLSX = True

def main():
    SCALE = "One Inch"
    print(f"{SCALE}: Reformating tables to new data format")
    block_suffix = {"One Inch": "A", "Half Inch": "B", "Quarter Inch": "C"}[SCALE]
    all_csv_files = glob.glob(f"{INTERIM_DATA_DIR}/{SCALE}/*.csv")
    if SCALE == "One Inch":
        csv_files = [x for x in all_csv_files if "BLOCK" not in x.upper()]
    else:
        csv_files = all_csv_files

    scale_docs = {"Quarter Inch": 44, "Half Inch": 34, "One Inch": 40}
    assert len(csv_files) == scale_docs[SCALE]

    if PARSE_DOCX:
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
            if file_id in ["Y104 38 X9051.doc", "Y104 53 X9051.docx"] and df.columns.equals(pd.Index(["Post-1905_1", "metadata"])):
                target = file_id.split()[1]
                target_df = entry_dfs[target + f"{block_suffix}.doc"]
                [data.process_2col_row(row=row, source=file_id, target_df=target_df, scale=SCALE) for (_, row) in df.iterrows()]

        docx_output_df = pd.concat([df for df in entry_dfs.values()])

        for file_id, df in input_dfs.items():
            if file_id in ["Y104RE~3.doc", "X13104.doc", "X13104 52to58.doc", "X9051_WORK_XLISTS.doc", "WLPS21N4 52to53.doc", "SIquarterX14092.doc"]:
                target_df = docx_output_df
                if file_id == "X13104.doc":
                    df["metadata"] = df["metadata"].str.replace("I-", "I").str.replace("J-", "J")
                [data.process_2col_row(row=row, source=file_id, target_df=target_df, scale=SCALE) for (_, row) in df.iterrows()]
        
        docx_output_df = docx_output_df.reset_index(drop=True)
        data.validate_output(df_input=input_dfs, output=docx_output_df)
    else:
        docx_output_df = pd.DataFrame()
    
    if SCALE == "One Inch":
        preprocessed_xlsx_files = [x for x in all_csv_files if "BLOCK" in x.upper()]
        assert len(preprocessed_xlsx_files) == 37
        clean_dfs = {}
        xlsx_entry_dfs = {}

        for f in preprocessed_xlsx_files:
            file_id = os.path.basename(f).split(".")[0] + ".xlsx"
            
            df = pd.read_csv(f, encoding="utf-8-sig")
            clean_dfs[file_id] = df
        

        print("Extracting entries from xlsx rows")
        with tqdm(clean_dfs.items()) as t:
            for file_id, df in t:
                t.set_description(f"{file_id}")
                entries = []
                [entries.extend(data.process_xlsx_row(row=row[1], source=file_id, scale=SCALE)) for row in df.iterrows()]
                
                entry_df = pd.concat([pd.DataFrame(x, index=[0]) for x in entries]).reset_index(drop=True)
                xlsx_entry_dfs[file_id] = entry_df

        xlsx_output_df = pd.concat([df for df in xlsx_entry_dfs.values()]).reset_index(drop=True)
        print("Resolving See references in xlsx data")
        xlsx_output_df = data.resolve_see_refs(xlsx_output_df)

        print("Merging xlsx and docx references")
        output_df = data.combine_doc_xlsx_outputs(doc_df=docx_output_df, xlsx_df=xlsx_output_df).sort_values(by=["Post-1905 Block Number", "Post-1905 Block Letter", "Post-1905 Sheet ID", "Print Date"])
    else:
        output_df = docx_output_df
    
    output_df.to_excel(f"{PROCESSED_DATA_DIR}/v0.1.1_{SCALE.replace(' ', '_')}_References.xlsx", index=False)


if __name__ == "__main__":
    main()