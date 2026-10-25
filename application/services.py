import os
from xml.etree.ElementTree import ParseError
from parser import parse_error_log, force_parse_unfinished_xml, file_already_processed, mark_file_processed
from database import ensure_db, insert_log_entries

def import_xml_into_database(filepath: str) -> int:
    # Main orchestrator. Calls parser for ONE raw XML, converts each "entry/error" into a tuple, calls db for insert
    # Returns number of entries parsed in one XML file (not necessarily inserted -> UNIQUE CONs. + INSERT OR IGNORE )
    ensure_db()     #since this runs first, error_log table is there before processed_files table
    if file_already_processed(filepath):
        return 0

    errors : list [dict[str, str | None]] = [] #each dict will be a full xml error.
    try:
        errors.extend(parse_error_log(filepath))
    except ParseError:
        errors.extend(force_parse_unfinished_xml(filepath)) #should the file grow later, it will be parsed again
                                                    # since the import criteria for file_already_processed is mtime

    if not errors:
        mark_file_processed(filepath)
        return 0

    #converting each dict (error) from errors into a tuple, so in the end we have a list of tuples (all errors from one file)
    converted_errors : list[tuple[str | None, ...]]= [( e["date"], e["time"], e.get("nodetype"), e.get("module"),
                                                        e.get("errorcode"), e.get("moreinfo"), e.get("sampleID"),
                                                        e.get("carrierID"), e.get("offline"), e.get("full_string") )
                                                        for e in errors ]
    insert_log_entries(converted_errors)
    mark_file_processed(filepath)
    return len(converted_errors)

def import_folder_into_database(folder: str) -> int:
    total_converted_errors = 0 #how many total errors from multiple xml files have been converted from xml to dicts to tuples

    for file_name in sorted(os.listdir(folder)):
        if not file_name.lower().endswith(".xml"):
            continue
        full_file_path = os.path.join(folder, file_name)

        try:
            converted_errors = import_xml_into_database(full_file_path)
            total_converted_errors += converted_errors
        except Exception as e:
            print(f"[ERROR] Failed to parse {file_name}: {e}")

    return total_converted_errors

def import_unfinished_xml_into_database(filepath: str) -> int:
    ensure_db()
    if file_already_processed(filepath):
        return 0

    errors : list [dict[str, str | None]] = [] #each dict will be a full xml error.

    errors.extend(force_parse_unfinished_xml(filepath)) #should the file grow later, it will be parsed again
                                                    # since the import criteria for file_already_processed is mtime

    if not errors:
        mark_file_processed(filepath)
        return 0

    #converting each dict (error) from errors into a tuple, so in the end we have a list of tuples (all errors from one file)
    converted_errors : list[tuple[str | None, ...]]= [( e["date"], e["time"], e.get("nodetype"), e.get("module"),
                                                        e.get("errorcode"), e.get("moreinfo"), e.get("sampleID"),
                                                        e.get("carrierID"), e.get("offline"), e.get("full_string") )
                                                        for e in errors ]
    insert_log_entries(converted_errors)
    mark_file_processed(filepath)
    return len(converted_errors)