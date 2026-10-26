import os
import sqlite3
import xml.etree.ElementTree as ETree
from utils import parse_any_datetime, split_date_time, app_dir

#region Database functions

DB_NAME = os.path.join(app_dir(), "error_log.db") #probably redundant, need to check this later

def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_NAME)

def ensure_file_registry() -> None:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(""" CREATE TABLE IF NOT EXISTS processed_files (
                    filepath TEXT PRIMARY KEY,
                    mtime REAL )    """ )                           # REAL == floating-point numbers
    conn.commit()
    conn.close()

def file_already_processed(filepath: str) -> bool:
    # Returns true if file exists with same mtime in registry table
    ensure_file_registry()

    try:
        mtime = os.path.getmtime(filepath)
    except OSError:
        return True # if file vanished, skip

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(" SELECT mtime FROM processed_files WHERE filepath = ?",
                (filepath,) )
    row = cur.fetchone()
    conn.close()

    return row is not None and row[0] == mtime

def mark_file_processed(filepath: str) -> None:
    # Stores/updates file mtime after successful parse
    ensure_file_registry()
    mtime = os.path.getmtime(filepath)

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(""" INSERT INTO processed_files ( filepath, mtime )
                    VALUES (?, ?) 
                    ON CONFLICT(filepath) DO UPDATE SET mtime = excluded.mtime """, (filepath, mtime)) # had a label_update problem because I had written "ON_CONFLICT"
    conn.commit()
    conn.close()
#endregion

#region Helper functions
ModuleNodeMap = {   # Module and analyzer names have been anonymized for data protection
                    ("CX", 22)  : "CX/1",   ("CX", 23)  : "CX/2",   ("CX", 24)  : "CX/3",
                    ("SAA", 27) : "SA/1",   ("SAA", 29) : "SA/2",   ("SAA", 30) : "SA/3",
                    ("CM", 9)   : "CM/1",   ("CM", 10)  : "CM/2",   ("CM", 11)  : "CM/3",
                    ("IM", 32)  : "IM/1",   ("IM", 33)  : "IM/2",   ("AK11", 50): "A/11",
                    ("DCE", 5)  : "DCE/1",  ("DCE", 6)  : "DCE/2",  ("YSS", 26) : "YSS/1",
                    ("LEZ", 12) : "LEZ/1",  ("LEZ", 11) : "LEZ/2",  ("YSS", 28) : "YSS/2",
                    ("98k", 4)  : "M/98/1", ("87k", 8)  : "M/87/2",                         }

def get_module_name(module_name: str | None, node_id: int | str | None) -> str:
    module_name = (module_name or "").strip()
    try:
        node_id = int(str(node_id).strip())
    except (TypeError, ValueError):
        node_id = None

    if module_name == "":
        if node_id is None:
            return ""
        matches = [name for (raw_name, r_id), name in ModuleNodeMap.items() if node_id == r_id]
        return matches[0] if len(matches) == 1 else ""

    temporary_solution = str(module_name + " " + str(node_id) )
    return ModuleNodeMap.get( (module_name, node_id), temporary_solution )

def normalize_sample_id(sid: str | None) -> str | None:
    if sid and sid.startswith("&D"):
        return sid[2:]
    return sid

def get_text_for_live_parse(elem: ETree.Element, name: str) -> str | None:
    text = elem.findtext(name) or elem.findtext(name.lower()) #in case new xml-files nest information as child-tags instead of attributes
    if text is not None:
        return text

    if name in elem.attrib: #quick attribute check
        return elem.attrib[name]

    name_lower = name.lower() #this loop .lower()'s the dict's key, so if key is "nOdEiD" we still find it using name
    for key, value in elem.attrib.items():
        if key.lower() == name_lower:
            return value

    return None
#endregion

#region Parsing functions

#main parser
def parse_error_log(filepath: str) ->  list[dict]:
    entries : list[dict[str, str | None]] = []

    context  = ETree.iterparse(filepath, events=("start", "end"))
    _, root = next(context) #to be able to delete each branch of the main-tag later.

    for event, elem in context:
        if event != "end":
            continue
        if elem.tag != "Error":
            continue
        try:
            dt = parse_any_datetime(elem.attrib.get("timestamp"))
            date, time = split_date_time(dt)
            module = get_module_name(elem.attrib.get("nodetype"), elem.attrib.get("nodeID"))
            sample_id = normalize_sample_id(elem.attrib.get("sampleID"))

            entry = { "date" : date, #xml lines without a date are skipped with the except block.
                      "time" : time, #same as date, further infos in parse_any_datetime
                      "nodetype" : elem.attrib.get("nodetype"),
                      "module" : module,
                      "errorcode" : elem.attrib.get("errorcode"),
                      "moreinfo" : elem.attrib.get("moreinfo"),
                      "sampleID" : sample_id,
                      "carrierID" : elem.attrib.get("carriedID"),
                      "offline" : elem.attrib.get("offline"),
                      "full_string" : ETree.tostring(elem, encoding="unicode") }
            entries.append(entry)
        except (ValueError, TypeError):
            pass #malformed entry or one missing date/time are ignored
        finally:
            elem.clear()      #element is cleared, but still attached as an empty "branch" to element tree
            root.remove(elem) #since Python builds a full tree in the background even with iterparse, best to delete the "branch" immediately for memory

    return entries

#fallback parser
def force_parse_unfinished_xml(filepath: str) -> list[dict]:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
        content = file.read()

    if "</automationErrorLog>" not in content:
        content += "\n</automationErrorLog>"

    root = ETree.fromstring(content)
    entries: list[dict[str, str | None]] = []

    for elem in root.findall("Error"):
        try:
            dt = parse_any_datetime(elem.attrib.get("timestamp"))
            date, time = split_date_time(dt)
            module = get_module_name(elem.attrib.get("nodetype"), elem.attrib.get("nodeID"))
            sample_id = normalize_sample_id(elem.attrib.get("sampleID"))

            entry = {"date": date,  # xml lines without a date are skipped with the except block.
                     "time": time,  # same as date, further infos in parse_any_datetime
                     "nodetype": elem.attrib.get("nodetype"),
                     "module": module,
                     "errorcode": elem.attrib.get("errorcode"),
                     "moreinfo": elem.attrib.get("moreinfo"),
                     "sampleID": sample_id,
                     "carrierID": elem.attrib.get("carriedID"),
                     "offline": elem.attrib.get("offline"),
                     "full_string": ETree.tostring(elem, encoding="unicode")}
            entries.append(entry)
        except (ValueError, TypeError):
            pass  # malformed entry or one missing date/time are ignored

    return entries

#real-time parser
def parse_one_live_error(xml_text: str) -> dict[str, str | None]:
    elem: ETree.Element = ETree.fromstring(xml_text)

    parsed_timestamp = parse_any_datetime(get_text_for_live_parse(elem, "timestamp"))
    date, time = split_date_time(parsed_timestamp)
    module = get_module_name(get_text_for_live_parse(elem, "nodeID"), get_text_for_live_parse(elem, "nodetype"))
    sample_id = normalize_sample_id(get_text_for_live_parse(elem, "sampleID"))

    return {  "date" : date,
              "time" : time,
              "nodetype" : elem.attrib.get("nodetype"),
              "module" : module,
              "errorcode" : elem.attrib.get("errorcode"),
              "moreinfo" : elem.attrib.get("moreinfo"),
              "sampleID" : sample_id,
              "carrierID" : elem.attrib.get("carrierID"),
              "offline" : elem.attrib.get("offline"),
              "full_string" : ETree.tostring(elem, encoding="unicode") }

#endregion