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
    if "38B.doc" in input_dfs:
        # Y102 38 X9052.doc 38J/SW IOR/X/9052/38J/SW
        input_dfs["38B.doc"].loc[37, "Post-1905_2"] = input_dfs["38B.doc"].loc[37, "Post-1905_2"].replace("NW", "SW")

        # Y102 38 X9052.doc 38 P SE IOR/X/9052/38P/SE
        input_dfs["38B.doc"].loc[63, "Post-1905_2"] = input_dfs["38B.doc"].loc[63, "Post-1905_2"].replace("NE", "SE")

    if "Y102 38 X9052.doc" in input_dfs:
        # Y102 38 X9052.doc 38S/NW IOR/X/9052/38N/SW
        input_dfs["Y102 38 X9052.doc"].loc[84, "metadata"] = input_dfs["Y102 38 X9052.doc"].loc[84, "metadata"].replace("38S/NW", "38N/SW")
        input_dfs["Y102 38 X9052.doc"].loc[85, "metadata"] = input_dfs["Y102 38 X9052.doc"].loc[85, "metadata"].replace("38S/NW", "38N/SW")

    if "Y102 53 X9052.doc" in input_dfs:
        # Y102 53 X9052.doc 53 M SW IOR/X/9052/53M/SW+M/SE
        input_dfs["Y102 53 X9052.doc"].loc[69, "metadata"] = input_dfs["Y102 53 X9052.doc"].loc[69, "metadata"].replace("53M/SW and M/SE", "53M/SW+M/SE")
    
    if "Y101 38 X9053.docx" in input_dfs:
        input_dfs["Y102 53 X9052.doc"].loc[:, "metadata"] = input_dfs["Y102 53 X9052.doc"].loc[:, "metadata"].str.replace(" & ", "+")


def log_data_errors(output_df_dict: dict[str, pd.DataFrame]) -> None:
    # TODO record edits to data made by fix_data_errors in the Notes field of the final data model
    pass


def pre_process_df(df: pd.DataFrame) -> pd.DataFrame:
    # Apply any preprocessing that can be column vectorised before the rows are processed
    for col in df.dropna(axis=1, how="all"):
        if df[col].dtype in (pd.StringDtype(na_value=np.nan), str):
            df[col] = df[col].str.replace("  ", " ")
    return df


def validate_block_info(bn, bl, sid):
    bn_re = re.compile(r"\d{2,2}$")
    bl_re = re.compile(r"[A-P]{1,1}$")
    sid_re = re.compile(r"\d{1,2}$|[NESW]{2}$")

    if not hasattr(bn_re.match(bn), "group"):
        raise ValueError(f"Block Number does not match expected 2 digit pattern: {bn}")

    if not hasattr(bl_re.match(bl), "group"):
        raise ValueError(f"Block Letter does not match expected 1 letter pattern: {bl}")

    if sid is not None and not hasattr(sid_re.match(sid), "group"):  # sid can be None so check for that case
        raise ValueError(f"Sheet ID does not match expected 1-2 digit or 2 letter pattern: {sid}")


def extract_plus_references(x_num: str, scale: str, bn: str, bl: str, sid: str|None, entry: dict[str, str|None]) -> list[dict[str, str|None]]:
    """Split references where they contain a plus into multiple entries

    Args:
        x_num (str): The complete X number reference
        scale (str): Map scale
        bn (str): Initial block number
        bl (str): Initial block letter
        sid (str): Initial sheet ID
        entry (dict[str, str | None]): Initial entry

    Returns:
        list[dict[str, str|None]]: A list of entries split from the complete reference
    """
    plus_entries = []
    logging.info(f"creating new entry for reference with plus: {x_num}")
    plus_bn = x_num[7:9]
    plus_bl = bl
    plus_sid = sid
    bn_re = re.compile(r"\d{2,2}")

    for part in x_num[7:].split("+"):
        if scale == "Quarter Inch":
            logging.info(f"Quarter Inch ref with +: {x_num}")
            
            if hasattr(bn_re.match(part), "group"):
                plus_bn = part[:2]
                part = part[2:]

            plus_bl = part[0]
            plus_sid = None

        elif scale == "Half Inch":
            if hasattr(bn_re.match(part), "group"):
                plus_bn = part[:2]
                part = part[2:]

            plus_bl = part.split("/")[0]
            plus_sid = part.split("/")[1]

        elif scale == "One Inch":
            if len(part) > 2 and hasattr(bn_re.match(part), "group"):
                plus_bn = part[:2]
                part = part[2:]
            
            if len(part) <= 2:
                plus_sid = part
            else:
                plus_bl = part.split("/")[0]
                plus_sid = part.split("/")[1]
            
        validate_block_info(plus_bn, plus_bl, plus_sid)
        if plus_bn == bn and plus_bl == bl and plus_sid == sid:
            continue
        else:
            plus_entry = deepcopy(entry)
            plus_entry["Post-1905 Block Number"] = plus_bn
            plus_entry["Post-1905 Block Letter"] = plus_bl
            plus_entry["Post-1905 Sheet ID"] = plus_sid
        
        plus_entries.append(plus_entry)
    
    return plus_entries


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
    
    # TODO handle quarter inch references without the '/' separator
    # Post-1905
    if scale == "Quarter Inch":
        bn, bl = row.loc["Post-1905_1"][:2], row.loc["Post-1905_1"][2]
        sid = None
    else:
        bn, bl = row.loc["Post-1905_1"].split("/")[0][:2], row.loc["Post-1905_1"].split("/")[0][2]
        sid = row.loc["Post-1905_1"].split("/")[1]

    validate_block_info(bn, bl, sid)

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
    year_re = re.compile(r"\d{4,4}$")
    references = {}
    for period in periods:
        col_2 = period + "_2"
        if not pd.isna(row.loc[col_2]):
            lines = [l.strip() for l in row.loc[col_2].split("\n")]
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
            elif "X/" in l and "+" in l and hasattr(year_re.search(l), "group"):
                logging.info(f"reference with plus: {l}")
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
            plus_entries = extract_plus_references(x_num=x_num, scale=scale, bn=bn, bl=bl, sid=sid, entry=entry)
            entries.extend(plus_entries)
        
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
        elif len(block_info) == 3:
            bns, bls = [block_info[:2]], [block_info[2]]
            sids = [None]
        else:
            bns, bls = [block_info.split("/")[0][:2]], [block_info.split("/")[0][2]]
            sids = [block_info.split("/")[1]]
        
        for bn, bl, sid in zip(bns, bls, sids):
            validate_block_info(bn, bl, sid)
            published_query = f"`Post-1905 Block Number` == '{bn}' and `Post-1905 Block Letter` == '{bl}' and `Post-1905 Sheet ID` == '{sid}' and `Full Reference` == 'IOR/{row.loc["Post-1905_1"]}'"
            query_idx = target_df.query(published_query).index
            if target_df.query(published_query).empty:
                logging.info(f"Queried df for {source} is empty. Query is {published_query}")
                # raise ValueError(f"Queried df for {source} is empty. Query is {published_query}")
            for i in query_idx:
                target_df.loc[i, "Notes"] += f"\n\nExtended metadata from {source}: \n{row.loc['metadata']}"


def validate_output(df_input: dict[str, pd.DataFrame], output: pd.DataFrame) -> None:
    """Apply a set of validation steps to an output dataframe
    These are a series of assert statements based on understanding of the input data

    Args:
        output_df (pd.DataFrame): _description_
    """
    
    sources_by_scale = {
        "63,360": set([os.path.basename(x) for x in glob.glob("C:\\Users\\hlloyd\\projects\\union-lists\\data\\raw\\One Inch\\*.doc")]),
        "1:126,720": set([os.path.basename(x) for x in glob.glob("C:\\Users\\hlloyd\\projects\\union-lists\\data\\raw\\Half Inch\\*.doc")]),
        "1:253,440": set([os.path.basename(x) for x in glob.glob("C:\\Users\\hlloyd\\projects\\union-lists\\data\\raw\\Quarter Inch\\*.doc")])
    }

    assert set(output["Scale"].unique()) <= set(sources_by_scale.keys())  # Won't work on a concatenated df of all the individual doc dfs
    assert set(output["Source File"].unique()) <= sources_by_scale[output["Scale"].unique()[0]]
    assert np.array_equal(output["Location Room"].unique(), ["UGF"])
    assert set(output["Time Period"].unique()) <= {"<1886", "1886-1905", ">1905", None}

    combined_input_text = ""
    for df in df_input.values():
        df = df.dropna(axis=1, how="all")
        df += " "
        combined_input_text += df.sum().sum()

    ref_re = re.compile(r"X/\d{1,7}/[\d\w/+]{1,}(?=\s)")
    input_refs = ref_re.findall(combined_input_text)
    input_iors = set(["IOR/" + ref for ref in input_refs])
    #  'IOR/X/9052/53M/SW' checked and removed as incorrect findall of IOR/X/9052/53M/SW+M/SE
    input_iors = input_iors - {'IOR/X/9052/53M/SW'}
    output_iors = set(output["Full Reference"].dropna())
    assert input_iors == output_iors

    assert np.array_equal(output["Parent Reference"].dropna().str.count("/").unique(), [2.0])

    # all_xnums = input_dfs["38B"].astype(str).sum(axis=1).str.replace("  ", " ").apply(lambda x: set(ref_re.findall(x)))
    # related_lookup = defaultdict(set)
    # for xnums in all_xnums:
    #     for xnum in xnums:
    #         related_lookup[xnum] |= xnums
    # for k,v in related_lookup.items():
    #     v -= {k}

    # for k, ref in full_refs_with_date.items():
    #     output_related_refs = set(("\n".join(output.loc[k, ["Post-1905 Related References", "1886-1905 Related References", "Pre-1886 Related References"]])).split("\n")) - {""}
    #     assert output_related_refs <= related_lookup[ref]

    assert output[
        [
            'Sheet Title', 'Edition Number', 
            'Designation_1', 'Designation_2', 'Publication Date', 'Print Reference', 'Copies Printed',
            'Coloured', 'Gridded', 'Number of Copies', 'Repmat', 'Latitude', 'Longitude', 'Available'
        ]
    ].dropna(axis=1, how="all").empty


if __name__ == "__main__":

    scale = "One Inch"
    block_suffix = {"One Inch": "A", "Half Inch": "B", "Quarter Inch": "C"}[scale]
    csv_files = glob.glob(f"data/interim/{scale}/*.csv")
    metadata_files = glob.glob(f"data/interim/{scale}/*.json")

    input_dfs, metadatas = {}, {}
    for f in csv_files:
        file_id = os.path.basename(f).split(".")[0] + ".doc"
        df = pd.read_csv(f, encoding="utf8").dropna(how="all")
        with open(f[:-4] + ".json") as g:
            metadata = json.load(g)
        input_dfs[file_id] = pre_process_df(df)
        metadatas[file_id] = metadata

    fix_data_errors(input_dfs)

    entry_dfs = {}
    for file_id, df in input_dfs.items():
        print(file_id)
        entries = []
        if df.columns.equals(pd.Index(['Post-1905_1', 'Post-1905_2', '1886-1905_1', '1886-1905_2', 'Pre-1886_1', 'Pre-1886_2'])):
            [entries.extend(process_6col_row(row[1], source=file_id, scale=scale, metadata=metadatas[file_id])) for row in df.iterrows()]
            entry_df = pd.concat([pd.DataFrame(x, index=[0]) for x in entries]).reset_index(drop=True)
            entry_dfs[file_id] = entry_df
    
    for file_id, df in input_dfs.items():
        if "Y" in file_id and df.columns.equals(pd.Index(["Post-1905_1", "metadata"])):
            target = file_id.split()[1]
            target_df = entry_dfs[target + f"{block_suffix}.doc"]
            [process_2col_row(row=row, source=file_id, target_df=target_df) for (name, row) in df.iterrows()]

    output = pd.concat([df for df in entry_dfs.values()])
    validate_output(df_input=input_dfs, output=output)

    output.to_csv("data/processed/v0.7_one_inch_sample.csv", encoding="utf-8-sig", index=False)
    output.to_excel("data/processed/v0.7_one_inch_sample.xlsx", index=False)
