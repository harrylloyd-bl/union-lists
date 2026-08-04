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

from union_lists.config import *
from union_lists.dataset.extract_from_doc import find_refs

logger = logging.getLogger(__name__)
logging.basicConfig(filename=f"{LOGS_DIR}/{datetime.now().strftime("%Y%m%d_%H%M")}_extract.log", level=logging.INFO)

def fix_data_errors(input_df_dict: dict[str, pd.DataFrame]) -> None:
    """Manually fix some errors in the raw documents

    Args:
        df_dict (dict[str, pd.DataFrame]): Dict of the dataframes extracted from the raw .doc files
    """
    if "38B.doc" in input_df_dict:
        # Y102 38 X9052.doc 38J/SW IOR/X/9052/38J/SW
        input_df_dict["38B.doc"].loc[37, "Post-1905_2"] = input_df_dict["38B.doc"].loc[37, "Post-1905_2"].replace("NW", "SW")

        # Y102 38 X9052.doc 38 P SE IOR/X/9052/38P/SE
        input_df_dict["38B.doc"].loc[63, "Post-1905_2"] = input_df_dict["38B.doc"].loc[63, "Post-1905_2"].replace("NE", "SE")

    if "58C.doc" in input_df_dict:
        # Missing new line character in cell
        input_df_dict["58C.doc"].loc[1, "Post-1905_2"] = input_df_dict["58C.doc"].loc[1, "Post-1905_2"].replace("1937 X/13104", "1937\nX/13104")

    if "83A.doc" in input_df_dict and "83a plus.doc" in input_df_dict:
        input_df_dict["83A.doc"][["1886-1905_1", "1886-1905_2", "Pre-1886_1", "Pre-1886_2"]] = input_df_dict["83a plus.doc"][["1886-1905_1", "1886-1905_2", "Pre-1886_1", "Pre-1886_2"]]
        del input_df_dict["83a plus.doc"]

    if "Y102 38 X9052.doc" in input_df_dict:
        # Y102 38 X9052.doc 38S/NW IOR/X/9052/38N/SW
        input_df_dict["Y102 38 X9052.doc"].loc[84, "metadata"] = input_df_dict["Y102 38 X9052.doc"].loc[84, "metadata"].replace("38S/NW", "38N/SW")
        input_df_dict["Y102 38 X9052.doc"].loc[85, "metadata"] = input_df_dict["Y102 38 X9052.doc"].loc[85, "metadata"].replace("38S/NW", "38N/SW")

    if "Y102 53 X9052.doc" in input_df_dict:
        # Y102 53 X9052.doc 53 M SW IOR/X/9052/53M/SW+M/SE
        input_df_dict["Y102 53 X9052.doc"].loc[69, "metadata"] = input_df_dict["Y102 53 X9052.doc"].loc[69, "metadata"].replace("53M/SW and M/SE", "53M/SW+M/SE")
    
    if "Y101 38 X9053.doc" in input_df_dict:
        # Standardise '&' as '+'
        input_df_dict["Y101 38 X9053.doc"].loc[:, "metadata"] = input_df_dict["Y101 38 X9053.doc"].loc[:, "metadata"].str.replace(" & ", "+")

        # These rows duplicate information in Y103 38 X9051.doc
        input_df_dict["Y101 38 X9053.doc"] = input_df_dict["Y101 38 X9053.doc"].iloc[:-24].copy()


def log_data_errors(output_df_dict: dict[str, pd.DataFrame]) -> None:
    # TODO record edits to data made by fix_data_errors in the Notes field of the final data model
    pass


def pre_process_df(df: pd.DataFrame) -> pd.DataFrame:
    # Apply any preprocessing that can be column vectorised before the rows are processed
    for col in df.dropna(axis=1, how="all"):
        if df[col].dtype in (pd.StringDtype(na_value=np.nan), str):
            df[col] = df[col].str.replace("  ", " ")
    return df.dropna(axis=0, how="all")


def validate_block_info(bn, bl, sid):
    """Validate a set of block information using regex

    Args:
        bn (str): a block number
        bl (str): a block letter
        sid (str): a sheet id

    Raises:
        ValueError: if bn does not match the bn_re
        ValueError: if bl does not match the bl_re
        ValueError: if sid does not match the sid_re
    """
    bn_re = re.compile(r"\d{2,2}$")
    bl_re = re.compile(r"[A-P]{1,1}$")
    sid_re = re.compile(r"\d{1,2}$|[NESW]{2}$")

    if not hasattr(bn_re.match(bn), "group"):
        raise ValueError(f"Block Number does not match expected 2 digit pattern: {bn}")

    if not hasattr(bl_re.match(bl), "group"):
        raise ValueError(f"Block Letter does not match expected 1 letter pattern: {bl}")

    if sid is not None and not hasattr(sid_re.match(sid), "group"):  # sid can be None so check for that case
        raise ValueError(f"Sheet ID does not match expected 1-2 digit or 2 letter pattern: {sid}")


def parse_plus_block_info(x_num: str, scale: str) -> list[dict[str,str | None]]:
    """Parse a reference that contains `+` to extract block info for the expanded references

    Args:
        x_num (str): an X num reference
        scale (str): the scale string (one of "One Inch", "Half Inch", "Quarter Inch")

    Returns:
        list[dict[str,str | None]]: a list of block infos for the expanded reference
    """
    if x_num.startswith("X"):
        plus_bn = "/".join(x_num.split("/")[:2])
        x_num_stub = "/".join(x_num.split("/")[2:])
    else:
        plus_bn = x_num[:2]
        x_num_stub = x_num[2:]
    parsed_block_infos = []

    bn_re = re.compile(r"\d{2,2}")
    for part in x_num_stub.split("+"):
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

        parsed_block_infos.append({
            "bn":plus_bn,
            "bl":plus_bl,
            "sid":plus_sid
            })
    
    return parsed_block_infos
    

def extract_plus_references(x_num: str, scale: str, bl: str, sid: str|None, entry: dict[str, str|None]) -> list[dict[str, str|None]]:
    """Split references where they contain a plus into multiple entries

    Args:
        x_num (str): The complete X number reference
        scale (str): Map scale
        bl (str): Initial block letter
        sid (str): Initial sheet ID
        entry (dict[str, str | None]): Initial entry

    Returns:
        list[dict[str, str|None]]: A list of entries split from the complete reference
    """
    plus_entries = []
    logging.info(f"creating new entry for reference with plus: {x_num}")
    default_bn = x_num[7:9]
    default_bl = bl
    default_sid = sid
    
    parsed_block_infos = parse_plus_block_info(x_num=x_num, scale=scale)
    for pbi in parsed_block_infos:
        if default_bn == pbi["bn"] and default_bl == pbi["bl"] and default_sid == pbi["sid"]:
            continue
        else:
            plus_entry = deepcopy(entry)
            plus_entry["Post-1905 Block Number"] = pbi["bn"]
            plus_entry["Post-1905 Block Letter"] = pbi["bl"]
            plus_entry["Post-1905 Sheet ID"] = pbi["sid"]
        
        plus_entries.append(plus_entry)
    
    return plus_entries


def create_notes_map(lines: list[str], labels: list[str]) -> dict[int, str]:
    """Create a mapping from notes lines to the references they should be notes for

    Args:
        lines (list[str]): Lines from a cell in one of the input documents
        labels (list[str]): Labels for the cell lines - `ref` or `note`

    Raises:
        ValueError: If there are no references among the labels, in which case there's nothing to map to

    Returns:
        dict[int, str]: A mapping from notes to references
    """
    if all([l == "note" for l in labels]):
        raise ValueError("All labels are notes, some labels must be references")

    notes_map = {i:"" for i, label in enumerate( labels) if label == "ref"}
    preceding_ref = -1
    all_line_notes = ""
    for i, (line, label) in enumerate(zip(lines, labels)):
        if label == "ref":
            preceding_ref = i
        elif label == "note" and preceding_ref == -1:
            all_line_notes += line + "\n"
        elif label == "note" and preceding_ref > -1:
            notes_map[preceding_ref] += line + "\n"

    for k in notes_map:
        notes_map[k] += all_line_notes

    return notes_map


def extract_references(row: pd.Series, periods: list[str]) -> dict[str,dict[str,str]]:
    """Extract all X/ or W/ references from a row mapped to period.
    Modify any lines in row that have a split '+' reference

    Args:
        row (pd.Series): row from a map list document
        periods (list[str]): the time periods covered by the map list columns

    Returns:
        dict[str,str]: an X/ or W/ ref : period mapping used to output in the new data model
    """
    # References
    strong_year_re = re.compile(r" \d{4,4}$")
    weak_year_re = re.compile(r" \d{4,4}")
    references = {}
    all_ref_note = ""

    for period in periods:
        col_1 = period + "_1"
        col_2 = period + "_2"
        if not pd.isna(row.loc[col_2]):
            lines_labels = [l.strip().split(" /// ") for l in row.loc[col_2].split("\n")]
            raw_lines, raw_labels = [l[0] for l in lines_labels], [l[1] for l in lines_labels]
            lines, labels = raw_lines.copy(), raw_labels.copy()
        else:
            continue
        
        # Only notes in a col_2
        if all([l == "note" for l in labels]):
            all_ref_note += f"{period} {row.loc[col_1]}: {'\n'.join(lines)}"
            continue

        modified_lines_to_remove = []
        # fix split line '+' references
        for i, l in enumerate(lines[:-1]):

            strong_year_in_line = strong_year_re.search(l)
            weak_year_in_line = weak_year_re.search(l)
            strong_year_in_next_line = strong_year_re.search(lines[i+1])
            line_to_mod = not strong_year_in_line and not weak_year_in_line and strong_year_in_next_line

            if "X/" in l and "+" in l and line_to_mod:
                logging.info(f"reference with plus, multiline: {l} // {lines[i+1]}")
                modified_line = l.strip() + " " + lines[i+1].strip()
                lines[i] = modified_line
                modified_lines_to_remove.append(i+1)
                if labels[i] == labels[i+1]:
                    raise ValueError(f"Label for line to concatenate doesn't match succeeding label: {lines[i]}  // {lines[i+1]}")
        
        for i in modified_lines_to_remove:
            del lines[i]
            del labels[i]

        row.loc[col_2] = "\n".join(lines)

        # Any other combination of notes and references
        notes_map = create_notes_map(lines, labels)
        
        for i, l in enumerate(lines):
            refs = find_refs(l)
            strong_year_in_line = strong_year_re.search(l)
            weak_year_in_line = weak_year_re.search(l)
            # breakpoint()
            if refs and len(lines) == 1:
                logging.info(f"reference single line: {l}")
                references.update({l: {"Period": period, "Notes":notes_map[i]}})
            elif refs and "+" not in l:
                logging.info(f"reference simple: {l}")
                references.update({l: {"Period": period, "Notes":notes_map[i]}})
            elif "X/" in l and "+" in l and strong_year_in_line:
                logging.info(f"reference with plus, strong year re: {l}")
                references.update({l: {"Period": period, "Notes":notes_map[i]}})
            elif "X/" in l and "+" in l and weak_year_in_line:
                logging.info(f"reference with plus, weak year re: {l}")
                references.update({l: {"Period": period, "Notes":notes_map[i]}})

    for v in references.values():
        v["Notes"] += all_ref_note

    if not references and all_ref_note:
        return {"NOTE_ONLY": {"Notes": all_ref_note}}
    else:
        return references


def process_6col_row(row: pd.Series, source: str, scale: str, metadata: dict[str, str]) -> list[dict[str, str | None]]:
    """Process a 6 col map row into the current data model

    Args:
        row (pd.Series): A row from a .doc/.xlsx file with information about a map sheet
        source (str): The filename the row came from
        scale (str): One of "One Inch", "Half Inch", "Quarter Inch". The scale of the map as a string.
        metadata (dict[str, str]): Metadata for the row, extracted from the footer of a 6 col document
    
    Returns:
        list[dict[str, str|None]]: A list of entries extracted from the row
    """
    entries = []
    entry_template: dict[str, None|str] = {
        "Source File": source,
        "Series Title": f"Survey of India India and Adjacent Countries {scale} Series",
        "Scale": {"Quarter Inch": "1:253,440", "Half Inch": "1:126,720", "One Inch": "63,360"}[scale],
        "Published": None,
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
        "Notes": ""
    }
    
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

    references = extract_references(row, periods)
            
    if "NOTE_ONLY" in references:
        entry = entry_template
        entry["Notes"] = references["NOTE_ONLY"]["Notes"]
        entries.append(entry)
        return entries

    elif not references:
        entry = entry_template
        entries.append(entry)
        return entries
    
    time_period = {"Post-1905": ">1905", "1886-1905": "1886-1905", "Pre-1886": "<1886"}
    for ref, ref_info in references.items():
        entry = deepcopy(entry_template)
        period = ref_info["Period"]
        entry["Time Period"] = time_period[period]
        entry["Published"] = "Y"
        if ref_info["Notes"]:
            entry["Notes"] = ref_info["Notes"]
            logging.info(f"reference line includes note: {ref_info["Notes"]}")

        # Year and Reference
        if len(ref.split()) == 2:
            x_num, year = ref.split()
        elif len(ref.split()) > 2:
            split_ref = ref.split()
            x_num, year = split_ref[0], split_ref[1]

        entry["Print Date"] = year
        if "/" in year:
            logging.info(f"slash split year: {year}")
            entry["Print Date"] = year.split("/")[1]
            entry["Edition Date"] = year.split("/")[0]
            entry["Notes"] += f"\nPrint Date: {year}. Reference in source {source} indicates earlier Edition Date: {ref}\n"  # ty:ignore[unsupported-operator]

        entry["Full Reference"] = "IOR/" + x_num
        entry["Parent Reference"] = "/".join(entry["Full Reference"].split("/")[:3])

        # Related References
        other_refs = references.copy()
        del other_refs[ref]

        for ref, ref_info in other_refs.items():
            related_refs = f"{ref_info["Period"]} Related References"
            entry[related_refs] += "\n" + ref  # ty:ignore[unsupported-operator]
            entry[related_refs] = entry[related_refs].lstrip("\n")  # ty:ignore[unresolved-attribute]
                        
        # Source column header/footer
        entry["Notes"] += f"\nSource period column header text: \n{metadata[f"{period}_header"]}\n"  # ty:ignore[unsupported-operator]
        entry["Notes"] += f"\nSource period column footer text: \n{metadata[f"{period}_footer"]}"
        entry["Notes"] = entry["Notes"].strip("\n")
        
        entries.append(entry)
        
        if "+" in x_num and entry["Time Period"] == ">1905":
            plus_entries = extract_plus_references(x_num=x_num, scale=scale, bl=bl, sid=sid, entry=entry)
            entries.extend(plus_entries)
        
    return entries


def process_2col_row(row: pd.Series, source: str, target_df: pd.DataFrame, scale: str) -> None:
    """Process a 2 column row from a Y series spreadsheet
    Y series contain extra information about map sheets
    This function uses that information to enrich existing rows in a dataframe processed from a 6 col spreadsheet

    Args:
        row (pd.Series): Row from a Y series spreadsheet
        source (str): The file name of the Y series spreadsheet
        target_df (pd.DataFrame): The dataframe to update with enriched metadata

    Returns:
        None
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

        if scale == "Quarter Inch":
            if "+" in block_info:
                parsed_block_infos = parse_plus_block_info(x_num=block_info, scale=scale)
            elif len(block_info) == 2:
                parsed_block_infos = [{"bn": block_info[0], "bl": block_info[1], "sid": None}]
            elif len(block_info) == 4:
                parsed_block_infos = [{"bn": block_info[0:3], "bl": block_info[3], "sid": None}]
            else:
                parsed_block_infos = [{"bn": block_info[:2], "bl": block_info[2], "sid": None}]
        else:
            if "+" in block_info:
                parsed_block_infos = parse_plus_block_info(x_num=block_info, scale=scale)
            elif len(block_info) == 3:
                parsed_block_infos = [{"bn": block_info[:2], "bl": block_info[2], "sid": None}]
            else:
                parsed_block_infos = [{"bn": block_info.split("/")[0][:2], "bl": block_info.split("/")[0][2], "sid": block_info.split("/")[1]}]
        
        for pbi in parsed_block_infos:
            bn = pbi["bn"]
            bl = pbi["bl"]
            sid = pbi["sid"]
            
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

    # TODO check for W/ refs as well
    ref_re = re.compile(r"(?<![NS])[XW]/\d{1,7}/[\d\w/+]{1,}(?=\s)")
    input_refs = ref_re.findall(combined_input_text)
    input_iors = set(["IOR/" + ref for ref in input_refs])
    #  IOR/X/9052/53M/SW checked and removed as incorrect findall of IOR/X/9052/53M/SW+M/SE
    #  IOR/X/9051/38K checked and removed as incomplete reference to a One Inch 38K ref
    #  IOR/X/2083/1 & /16 checked and removed as notes rather than references
    #  IOR/X/9373/195/1904 checked and removed as misprint, corrected to X/9373/195 1904 in postcorrect_df
    input_iors = input_iors - {'IOR/X/9052/53M/SW', 'IOR/X/9051/38K', 'IOR/X/2083/1', 'IOR/X/2083/16', 'IOR/X/9373/195/1904'}
    output_iors = set(output["Full Reference"].dropna()) - {'IOR/X/9051/38K'}
    missed_long_w_refs = {ior for ior in output_iors - input_iors if "/W/" in ior}
    #  ref_re above is too simple to catch long W references, so remove these from the output side
    output_iors = output_iors - missed_long_w_refs
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
    pass

    
