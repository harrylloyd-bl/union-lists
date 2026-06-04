from multiprocessing import Value
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
import glob
import json
import logging
import os
import re

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(filename=f"logs/{datetime.now().strftime("%Y%m%d_%H%M")}_main.log", level=logging.INFO)


def fix_data_errors(input_df_dict: dict[str, pd.DataFrame]) -> None:
    """Manually fix some errors in the raw documents

    Args:
        df_dict (dict[str, pd.DataFrame]): Dict of the dataframes extracted from the raw .doc files
    """
    if "38B.doc" in dfs:
        # Y102 38 X9052.doc 38J/SW IOR/X/9052/38J/SW
        dfs["38B.doc"].loc[37, "Post-1905_2"] = dfs["38B.doc"].loc[37, "Post-1905_2"].replace("NW", "SW")

        # Y102 38 X9052.doc 38 P SE IOR/X/9052/38P/SE
        dfs["38B.doc"].loc[63, "Post-1905_2"] = dfs["38B.doc"].loc[63, "Post-1905_2"].replace("NE", "SE")

    if "Y102 38 X9052.doc" in dfs:
        # Y102 38 X9052.doc 38S/NW IOR/X/9052/38N/SW
        dfs["Y102 38 X9052.doc"].loc[84, "metadata"] = dfs["Y102 38 X9052.doc"].loc[84, "metadata"].replace("38S/NW", "38N/SW")
        dfs["Y102 38 X9052.doc"].loc[85, "metadata"] = dfs["Y102 38 X9052.doc"].loc[85, "metadata"].replace("38S/NW", "38N/SW")

    if "Y102 53 X9052.doc" in dfs:
        # Y102 53 X9052.doc 53 M SW IOR/X/9052/53M/SW+M/SE
        dfs["Y102 53 X9052.doc"].loc[69, "metadata"] = dfs["Y102 53 X9052.doc"].loc[69, "metadata"].replace("53M/SW and M/SE", "53M/SW+M/SE")


def log_data_errors(output_df_dict: dict[str, pd.DataFrame]) -> None:
    pass


def pre_process_df(df: pd.DataFrame) -> pd.DataFrame:
    # Apply any preprocessing that can be column vectorised before the rows are processed
    for col in df.dropna(axis=1, how="all"):
        if df[col].dtype in (pd.StringDtype(na_value=np.nan), str):
            df[col] = df[col].str.replace("  ", " ")
    return df


def process_6col_row(row: pd.Series, source: str, scale: str, metadata: dict[str, str]) -> list[dict[str, str | None]]:
    """Process a 6 col map row into the current data model

    Args:
        row (pd.Series): A row from a .doc/.xlsx file with information about a map sheet
        source (str): The filename the row came from
        scale (str): One of "One Inch", "Half Inch", "Quarter Inch". The scale of the map as a string.
    """
    entries = []
    entry_template = {
        "Source File": source,
        "Series Title": f"Survey of India India and Adjacent Countries {scale} Series",
        "Scale": {"Quarter Inch": "1:253,440", "Half Inch": "1:126,720", "One Inch": "63,360"}[scale],
        "Published": None,  # How to tell if published and we don"t have a copy?
        "Location Room": "UGF",
        "Location Section": None,  # dict lookup with external resource, out of scope currently, see Issue #2
        "Location Detail": None,  # dict lookup with external resource, out of scope currently, see Issue #2
        "Full Reference": None,
        "Print Date": None,
        "Time Period": None,
        "Parent Reference": None,
        "Post-1905 Related References": "", # Introduced with Issue #3
        "1886-1905 Related References": "", # Introduced with Issue #3
        "Pre-1886 Related References": "", # Introduced with Issue #3
        "Post-1905 Block Number": None,
        "Post-1905 Block Letter": None,
        "Post-1905 Sheet ID": None,
        "1886-1905 New Sheet ID": None,
        "1886-1905 Old Sheet ID": None,
        "Pre-1886 New Sheet ID": None,
        "Pre-1886 Old Sheet ID": None,
        "Sheet Title": None,
        "Edition Number": None,
        "Edition Date": None,
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
        "Notes": ""
    }
    
    # Post-1905
    bn, bl = row.loc["Post-1905_1"].split("/")[0][:2], row.loc["Post-1905_1"].split("/")[0][2]
    sid = row.loc["Post-1905_1"].split("/")[1]
    entry_template["Post-1905 Block Number"] = bn
    entry_template["Post-1905 Block Letter"] = bl
    entry_template["Post-1905 Sheet ID"] = sid

    periods = ["Post-1905", "1886-1905", "Pre-1886"]

    # 1886-1905/Pre-1886 new/old sheet IDS
    for period in periods[1:]:
        col_1 = period + "_1"
        if not pd.isna(row.loc[col_1]):
            if len(row.loc[col_1].split("\n")) == 1:
                entry_template[f"{period} New Sheet ID"] = row.loc[col_1]
            elif len(row.loc[col_1].split("\n")) == 2:
                entry_template[f"{period} New Sheet ID"] = row.loc[col_1].split("\n")[1]
                entry_template[f"{period} Old Sheet ID"] = row.loc[col_1].split("\n")[0]

    
    # References
    year_re = re.compile(r"\d{4,4}")
    references = {}
    for period in periods:
        col_2 = period + "_2"
        if not pd.isna(row.loc[col_2]):
            lines = row.loc[col_2].split("\n")
            modified_lines = lines.copy()
        else:
            continue
        
        modified_lines_to_remove = []
        for i, l in enumerate(lines):
            if "X/" in l and len(lines) == 1:
                logging.info(f"reference single line: {l}")
                references.update({lines[0]: period})
                break
            elif "X/" in l and "+" not in l:
                logging.info(f"reference simple: {l}")
                references.update({l: period})
            elif "X/" in l and "+" in l and hasattr(year_re.search(lines[i+1]), "group"):
                logging.info(f"reference with plus: {l} // {lines[i+1]}")
                modified_line = l.strip() + " " + lines[i+1].strip()
                references.update({modified_line: period})
                modified_lines[i] = modified_line
                modified_lines_to_remove.append(lines[i+1])
        
        [modified_lines.remove(l) for l in modified_lines_to_remove]
        row.loc[col_2] = "\n".join(modified_lines)
            

    if not references:
        entry = entry_template
        entries.append(entry)
        return entries
    
    time_period = {"Post-1905": ">1905", "1886-1905": "1886-1905", "Pre-1886": "<1886"}
    for ref, period in references.items():
        entry = deepcopy(entry_template)
        entry["Time Period"] = time_period[period]
        entry["Published"] = "Y"

        # Year and Reference
        if len(ref.split()) == 2:
            x_num, year = ref.rsplit()
        elif len(ref.split()) > 2:
            split_ref = ref.split()
            x_num, year = split_ref[0], split_ref[1]
            ref_note = " ".join(split_ref[2:])
            logging.info(f"reference includes note: {ref_note}")
            entry["Notes"] += f"Reference note: {ref_note}\n"  # ty:ignore[unsupported-operator]

        entry["Print Date"] = year
        entry["Edition Date"] = ""
        if "/" in year:
            logging.info(f"slash split year: {year}")
            entry["Print Date"] = year.split("/")[1]
            entry["Edition Date"] = year.split("/")[0]
            entry["Notes"] += f"Print Date: {year}. Reference in source {source} indicates earlier Edition Date: {ref}\n"  # ty:ignore[unsupported-operator]

        entry["Full Reference"] = "IOR/" + x_num
        entry["Parent Reference"] = "/".join(entry["Full Reference"].split("/")[:3])

        # Related References
        other_refs = references.copy()
        del other_refs[ref]

        for ref, period in other_refs.items():
            entry[period + " Related References"] += "\n" + ref  # ty:ignore[unsupported-operator]
            entry[period + " Related References"] = entry[period + " Related References"].lstrip("\n")  # ty:ignore[unresolved-attribute]
            

        # Reference Notes
        lines = row.loc[f"{period}_2"].split("\n")
        if len(lines) > lines.index(ref) + 2 and "X/" not in lines[lines.index(ref) + 1]:
            entry["Notes"] += f"Reference coverage note: {lines[lines.index(ref) + 1]}\n"  # ty:ignore[unsupported-operator]
            
        # Source column header/footer
        period_header = metadata[f"{period}_header"]
        period_footer = metadata[f"{period}_footer"]
        entry["Notes"] += f"\nSource period column header text: \n{period_header}\n"  # ty:ignore[unsupported-operator]
        entry["Notes"] += f"\nSource period column footer text: \n{period_footer}"
        entry["Notes"] = entry["Notes"].strip("\n")
        
        entries.append(entry)

        if "+" in x_num and entry["Time Period"] == ">1905":
            logging.info(f"creating new entry for reference with plus: {x_num}")
            plus_bn = x_num[7:9]
            for part in x_num[9:].split("+"):
                plus_entry = deepcopy(entry)
                plus_bl = part.split("/")[0]
                plus_sid = part.split("/")[1]
                if plus_bl == bl and plus_sid == sid:
                    continue
                else:
                    plus_entry["Post-1905 Block Number"] = plus_bn
                    plus_entry["Post-1905 Block Letter"] = plus_bl
                    plus_entry["Post-1905 Sheet ID"] = plus_sid
                
                entries.append(plus_entry)
        
    return entries


def process_2col_row(row: pd.Series, source: str, target_df: pd.DataFrame) -> None:
    """Process a 2 column row from a Y series spreadsheet
    Y series contain extra information about map sheets
    This function uses that information to enrich existing rows in a dataframe processed from a 6 col spreadsheet

    Args:
        row (pd.Series): Row from a Y series spreadsheet
        source (str): The file name of the Y series spreadsheet
        target_df (pd.DataFrame): The dataframe to update with enriched metadata
    """
    if pd.isna(row.loc["Post-1905_1"]) and "not published" in row.loc["metadata"]:
        block_info = row.loc["metadata"].split()[1]
        bn, bl = block_info.split("/")[0][:2], block_info.split("/")[0][2]
        sid = block_info.split("/")[1]
        
        not_published_query = f"`Post-1905 Block Number` == '{bn}' and `Post-1905 Block Letter` == '{bl}' and `Post-1905 Sheet ID` == '{sid}'"
        query_idx = target_df.query(not_published_query).index

        if target_df.query(not_published_query).empty:
            raise ValueError(f"Queried df for {source} is empty. Query is {not_published_query}")
        
        for i in query_idx:
            target_df.loc[i, "Published"] = "N"
            target_df.loc[i, "Notes"] += f"\n\nPublication info from {source}: \n{row.loc['metadata']}"

    elif not row.isna().any():
        if "\n" in row.loc["Post-1905_1"]:
                row.loc["Post-1905_1"] = "".join([l.strip() for l in row.loc["Post-1905_1"].split("\n")])
        
        block_info = row.loc["metadata"].split()[1]
        
        if "+" in block_info:
            bls = [x.split("/")[0] for x in block_info[2:].split("+")]
            sids = [x.split("/")[1] for x in block_info[2:].split("+")]
            bns = [block_info[:2] for x in bls]
            logging.info(f"Y doc ref contains +: block info {block_info}, bns {bns}, bls {bls}, sids {sids}")
        else:
            bns, bls = [block_info.split("/")[0][:2]], [block_info.split("/")[0][2]]
            sids = [block_info.split("/")[1]]
        
        for bn, bl, sid in zip(bns, bls, sids):
            published_query = f"`Post-1905 Block Number` == '{bn}' and `Post-1905 Block Letter` == '{bl}' and `Post-1905 Sheet ID` == '{sid}' and `Full Reference` == 'IOR/{row.loc["Post-1905_1"]}'"
            query_idx = target_df.query(published_query).index
            if target_df.query(published_query).empty:
                logging.info(f"Queried df for {source} is empty. Query is {published_query}")
                # raise ValueError(f"Queried df for {source} is empty. Query is {published_query}")
            for i in query_idx:
                target_df.loc[i, "Notes"] += f"\n\nExtended metadata from {source}: \n{row.loc['metadata']}"


def validate_output(output_df):
    pass


if __name__ == "__main__":

    csv_files = glob.glob("data/interim/Half Inch/*.csv")
    metadata_files = glob.glob("data/interim/Half Inch/*.json")

    dfs, metadatas = {}, {}
    for f in csv_files[15:16]:
        file_id = os.path.basename(f).split(".")[0] + ".doc"
        df = pd.read_csv(f, encoding="utf8").dropna(how="all")
        with open(f[:-4] + ".json") as g:
            metadata = json.load(g)
        dfs[file_id] = pre_process_df(df)
        metadatas[file_id] = metadata

    fix_data_errors(dfs)

    entry_dfs = {}
    for file_id, df in dfs.items():
        print(file_id)
        entries = []
        if df.columns.equals(pd.Index(['Post-1905_1', 'Post-1905_2', '1886-1905_1', '1886-1905_2', 'Pre-1886_1', 'Pre-1886_2'])):
            [entries.extend(process_6col_row(row[1], source=file_id, scale="Half Inch", metadata=metadatas[file_id])) for row in df.iterrows()]
            entry_df = pd.concat([pd.DataFrame(x, index=[0]) for x in entries]).reset_index(drop=True)
            entry_dfs[file_id] = entry_df
    
    for file_id, df in dfs.items():
        if "Y" in file_id and df.columns.equals(pd.Index(["Post-1905_1", "metadata"])):
            target = file_id.split()[1]
            target_df = entry_dfs[target + "B.doc"]
            [process_2col_row(row=row, source=file_id, target_df=target_df) for (name, row) in df.iterrows()]

    combined_df = pd.concat([df for df in entry_dfs.values()])
    validate_output(combined_df)

    combined_df.to_csv("data/processed/v0.6_sample.csv", encoding="utf-8-sig", index=False)
    combined_df.to_excel("data/processed/v0.6_sample.xlsx", index=False)
