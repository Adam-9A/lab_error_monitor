import os
import glob
import time
import threading
import tkinter as tk
from _collections_abc import Callable
from tkinter import filedialog, messagebox, ttk
from services import import_xml_into_database, import_folder_into_database, import_unfinished_xml_into_database
from database import get_values_for_filter, fetch_entries_page, fetch_filtered_page, fetch_full_string_by_id, insert_live_log_entries
from rt_monitoring import RealTimeMonitor, LiveXMLTracker, ErrorEvent

class ErrorMonitor:
    #region Init + Build
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Error Monitor")

        self.page_limit = 500 # how many rows to fetch
        self.page_offset = 0 # how many rows to skip before fetching
        self.current_filters: dict[str, str | None] = {}
        self.entries_loaded = 0

        self.node_cache: list[str] = []     # Stores the available nodetypes/modules from the database.
        self.module_cache: list[str] = []   # refresh_filter_options() retrieves them using get_values_for_filter()
                                            # and passes them to the ttk.Combobox self.node_box
                                            # self.node_box is linked to self.node_var (stores user's current selection)
                                            # self._collect_filters reads it
        self.monitoring = False
        self.filepath = None
        self.start_button_clicked = False   # to avoid clear_filters page_loading bug if used before start

        self.rt_monitor = RealTimeMonitor()
        self.live_tracker = LiveXMLTracker()

        self._build_layout()

        self.refresh_combobox_options() #refresh_distinct_cashes
        self.blacklisted_errors = set()

    def _build_layout(self) -> None:
        self._build_top_bar()
        self._build_table()
        self._build_alert_bar()
        self._build_filters()

    def _build_top_bar(self) -> None:
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=5)

        data_for_button = (("Start", self.show_initial_page),
                           ("Load more", self.load_next_page),
                           ("Select Folder", self.parse_multiple_files),
                           ("Select File", self.parse_single_file)  )

        self.status_label = tk.Label(top, text="Ready")
        self.status_label.pack(side="right", padx=15)

        for name, command in data_for_button:
            button = tk.Button(top, text=name, command=command)
            if name == "Load more":
                button.pack(side="right", padx=5)
            else:
                button.pack(side="left", padx=5)

        self.monitor_button = tk.Button(top, text="Real-Time Monitoring", command=self.start_monitoring, state="disabled") #idea was that monitoring should only start once normal files have been laden, but maybe I will change this
        self.monitor_button.pack(side="left", padx=5)

    def _build_table(self) -> None:
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        column_info = {"id": (0, False), "date": (80, True), "time": (80, True), "nodetype": (70, True),
                       "module": (70, True), "errorcode": (70, True), "moreinfo": (270, True),
                       "sampleID": (70, True), "carrierID": (0, False), "offline": (0, False)}

        self.tree = ttk.Treeview(tree_frame, columns=list(column_info.keys()), show="headings", yscrollcommand=scrollbar.set) # select_mode = extended by default
        scrollbar.config(command=self.tree.yview)

        for column, (width, stretch) in column_info.items():
            self.tree.heading(column, text=column)
            width = column_info.get(column, (80, True))[0]
            stretch = column_info.get(column, (80, True))[1]
            self.tree.column(column, width=width, stretch=stretch)

        self.tree.pack(fill="both", expand=True)

    def _build_alert_bar(self) -> None:
        self.alert_frame = tk.Frame(self.root)
        self.alert_frame.pack(fill="x", padx=10, pady=5)

        scrollbar = tk.Scrollbar(self.alert_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.alert_box = tk.Listbox(self.alert_frame, height=3, yscrollcommand=scrollbar.set)
        self.alert_box.pack(fill="x", expand=True)
        scrollbar.config(command=self.alert_box.yview)

    def _build_filters(self) -> None:
        filter_frame = tk.LabelFrame(self.root, text="Filters")
        filter_frame.pack(fill="x", padx=10, pady=5)

        self._build_time_filters(filter_frame)
        self._build_entity_filters(filter_frame)
        self._build_filter_buttons(filter_frame)
        self._build_show_about(filter_frame) # not part of filter-functionality, maybe I will add an extra frame for it later

    def _build_time_filters(self, parent: tk.Widget) -> None:
        self.date_from = tk.Entry(parent, width=12)
        self.date_to = tk.Entry(parent, width=12)
        self.time_from= tk.Entry(parent, width=12)
        self.time_to = tk.Entry(parent, width=12)

        tk.Label(parent, text="Date from").grid(row=0, column=0)
        self.date_from.grid                    (row=0, column=1)
        tk.Label(parent, text="to").grid       (row=0, column=2)
        self.date_to.grid                      (row=0, column=3)

        tk.Label(parent, text="Time from").grid(row=0, column=4)
        self.time_from.grid                    (row=0, column=5)
        tk.Label(parent, text="to").grid       (row=0, column=6)
        self.time_to.grid                      (row=0, column=7)

    def _build_entity_filters(self, parent: tk.Widget) -> None:
        self.node_var = tk.StringVar() # stores users current selection in the node_box dropdown.
        self.module_var = tk.StringVar() # later we retrieve that value using node_var.get() to get DB entries under that "column"
        self.node_box = ttk.Combobox(parent, textvariable=self.node_var, state="readonly", width=12) #values = (), none assigned yet
        self.module_box = ttk.Combobox(parent, textvariable=self.module_var, state="readonly", width=12) #during this stage the dropdown is empty

        self.errorcode_entry = tk.Entry(parent, width=15)
        self.sampleID_entry = tk.Entry(parent, width=15)

        tk.Label(parent, text="Node").grid  (row=1, column=0)
        self.node_box.grid                  (row=1, column=1)
        tk.Label(parent, text="Module").grid(row=1, column=2)
        self.module_box.grid                (row=1, column=3)

        tk.Label(parent, text="Error").grid (row=1, column=4)
        self.errorcode_entry.grid           (row=1, column=5)
        tk.Label(parent, text="SampleID").grid(row=1, column=6)
        self.sampleID_entry.grid              (row=1, column=7)

    def _build_filter_buttons(self, parent: tk.Widget) -> None:
        apply_button = tk.Button(parent, text="Apply filters", command=self.apply_filters)
        clear_button = tk.Button(parent, text="Clear", command=self.clear_filters)
        self.full_string_btn = tk.Button(parent, text="Show original XML line", command=self.show_original_xml_string)
        self.black_list_btn = tk.Button(parent, text="Blacklist error", command=self.add_error_to_blacklist)

        apply_button.grid           (row=2, column=5, pady=5)
        clear_button.grid           (row=2, column=6, pady=5)
        self.full_string_btn.grid   (row=2, column=7, pady=10, padx=10)
        self.black_list_btn.grid    (row=2, column=9, pady=10, padx=10)

    def _build_show_about(self, parent: tk.Widget) -> None:
        tk.Button(parent, text="About", width=1, command=self.show_about).grid(row=2, column=0)
    #endregion

    #region Motors + Treeview operations (assigned to button commands)
    def clear_table(self) -> None:
        all_lines = self.tree.get_children()    # returns IDs of the rows in the table
        self.tree.delete(*all_lines)            # * asterisk operator: unpack tuple/list into separate arguments

    def insert_rows(self, rows: list[tuple[int | str | None, ...]]) -> None:
        for line in rows:
            self.tree.insert("", "end", values=line)  # populates the table with the retrieved tuples from DB

    def insert_live_rows(self, rows: tuple[tuple[str | None, ...], ...], ids: tuple[int | None, ...]) -> None:
        count = 0
        for entry, db_id in zip(rows, ids):
            if db_id is None: # since duplicate entries are ignored in the db, the row_id may be None.
                continue
            one_line = (db_id,) + entry # tuple concatenation: db_id is turned into a tuple first
            self.tree.insert("", 0, values=one_line)
            count += 1


        self.entries_loaded += count
        self.tree.yview_moveto(0) # to see each new insert line immediately
        self.status_label.config(text=f"Live: {self.entries_loaded} entries")

    @staticmethod
    def _convert_error_dict_to_row(error: dict[str, str | None]) -> tuple[str | None, ...]:
        keys = ["date", "time", "nodetype", "module", "errorcode", "moreinfo",
                "sampleID", "carrierID", "offline", "full_string"]

        return tuple(error[key] for key in keys)

    def show_initial_page(self) -> None:
        self.start_button_clicked = True
        self.page_offset = 0 # how many rows to skip
        self.entries_loaded = 0
        self.current_filters: dict[str, str | None] = {}

        self.clear_table()

        lines: list[tuple[int | str | None, ...]] = fetch_entries_page(self.page_limit, self.page_offset)
        self.insert_rows(lines)
        self.entries_loaded += len(lines)

        self.monitor_button.config(state="normal")
        self.status_label.config(text=f"Loaded {self.entries_loaded} entries")

    def load_next_page(self) -> None:
        self.page_offset += self.page_limit

        lines: list[tuple[int | str | None, ...]] = []
        if self.current_filters:
            lines.extend(fetch_filtered_page(self.current_filters, self.page_limit, self.page_offset))
        else:
            lines.extend(fetch_entries_page(self.page_limit, self.page_offset))

        if not lines:
            self.status_label.config(text="No more entries")
            return

        self.insert_rows(lines)
        self.entries_loaded += len(lines)
        self.status_label.config(text=f"Loaded {self.entries_loaded} entries")
    #endregion

    #region Filtering
    def apply_filters(self) -> None:
        self.current_filters = self._collect_filters()
        self.page_offset = 0
        self.entries_loaded = 0

        self.clear_table()

        lines: list[tuple[str | int | None, ...]] = []
        lines.extend(fetch_filtered_page(self.current_filters, self.page_limit, self.page_offset))


        self.insert_rows(lines)
        self.entries_loaded += len(lines)
        self.status_label.config(text=f"Filtered: {self.entries_loaded} entries")

    def clear_filters(self) -> None:
        text_filter_widgets: tuple[tk.Entry, ...] = ( self.date_from, self.date_to, self.time_from,
                                                      self.time_to, self.errorcode_entry, self.sampleID_entry)

        for widget in text_filter_widgets:
            widget.delete(0, tk.END) # tk.Entry method that removes text from field (start, end)

        self.node_var.set("")
        self.module_var.set("")
        if self.start_button_clicked:
            self.show_initial_page()

    def _collect_filters(self) -> dict:
        return {    "date_from": self.date_from.get() or None,
                    "date_to": self.date_to.get() or None,
                    "time_from": self.time_from.get() or None,
                    "time_to": self.time_to.get() or None,
                    "nodetype": self.node_var.get() or None,
                    "module": self.module_var.get() or None,
                    "errorcode": self.errorcode_entry.get() or None,
                    "sampleID": self.sampleID_entry.get() or None       }

    def refresh_combobox_options(self) -> None:
        self.node_cache: list[str] = get_values_for_filter("nodetype")   # Refreshes cache with distinct DB nodetypes available in node_box dropdown (for user selection).
        self.module_cache: list[str] = get_values_for_filter("module")  # node_var shows/saves the selection

        self.node_box["values"] = self.node_cache # attribute-access mechanism
        self.module_box["values"] = self.module_cache # we are inserting our options directly into the widget.

    def configure_black_list(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Blacklist")
        window.geometry("800x400")

        text = tk.Text(window, wrap="word", font=("Consolas", 14))
        text.pack(fill="both", expand=True)

        for a in self.blacklisted_errors:
            text.insert("end", f"{a}\n")

        text.config(state="disabled") # by default, text is editable by user

        remove_from_bl_button = tk.Button(window, text="Remove", command=self.remove_error_from_blacklist)
        remove_from_bl_button.pack(side="right", padx=5)

    def add_error_to_blacklist(self) -> None:
        selected_line_id: tuple[str, ...] = self.tree.selection() # tuple of treeview item IDs e.g. ("I001", "I002", ...)

        if not selected_line_id:
            messagebox.showwarning("No row selected", "Please select a row first")
            return

        item_id = selected_line_id[0] # in case multiple lines (item IDs) are selected, take the first one only
        values_in_row = self.tree.item(item_id, "values")

        errorcode = values_in_row[5]
        self.blacklisted_errors.add(errorcode)

        # the following code snippet needs to be isolated in its own function and be called during each page refresh/load

        row_id: str # this is just the IDs of the line!
        for row_id in self.tree.get_children(): # retrieve all current lines (item IDs) from table
            row_value = self.tree.item(row_id, "values")
            corresponding_error: str = row_value[5]
            if corresponding_error in self.blacklisted_errors:
                self.tree.delete(row_id)

    def remove_error_from_blacklist(self) -> None:
        pass # work in progress

    def show_original_xml_string(self) -> None:
        selected_line_id = self.tree.selection()

        if not selected_line_id:
            messagebox.showwarning("No row selected", "Please select a row first")
            return

        treeview_id = selected_line_id[0] # in case multiple lines were selected
        values_in_row = self.tree.item(treeview_id, "values")

        if not values_in_row[0]:    # DB is searched using id for the original_xml_string
            messagebox.showinfo("Warning", "No database ID found") # technically, this is the ID displayed in the treeview, but corresponds to the record's ID in the DB.
            return # Guard clause: stop if the selected row has no database ID

        db_id = int(values_in_row[0]) # id in DB is defined as INTEGER!
        original_full_string = fetch_full_string_by_id(db_id)

        if original_full_string is None:
            messagebox.showinfo("Warning", "No string is available for the selected row")
            return

        window = tk.Toplevel(self.root)
        window.title("Original XML String")
        window.geometry("800x100")

        text = tk.Text(window, wrap="word", font=("Consolas", 14))
        text.pack(fill="both", expand=True)
        text.insert("1.0", original_full_string) #1.0 == line 1, character 0 == very beginning of text widget
        text.config(state="disabled")
    #endregion

    #region Parsing with Threading
    def _run_background_task(self, task: Callable[[], int], on_success: Callable[[int], None]) -> None:
        def worker():
            try:
                count = task()
            except Exception as exc: # this happens from my created thread, basically "knocking" on the main thread
                self.root.after(0, lambda msg = str(exc): messagebox.showerror("Parse error", msg))
                return

            self.root.after(0, lambda value=count: on_success(value) ) # calls passes "on_success" function
            # program's main thread runs the tkinter event loop -> processes gui events
            # 0 means "as soon as tkinter can process it"

        threading.Thread(target=worker, daemon=True).start() # creates and stars background thread

    def _on_parse_done(self, count: int) -> None:
        self.refresh_combobox_options()
        self.show_initial_page()
        messagebox.showinfo("Done", f"Parsed {count} entries")

    def parse_single_file(self) -> None:
        filepath = filedialog.askopenfilename(filetypes=[("XML files", "*.xml")]) # (displayed name, pattern actually used)
        if not filepath:
            messagebox.showwarning("No file", "Select an XML file first")
            return

        self.status_label.config(text="Parsing ...")
        self._run_background_task(task=lambda: import_xml_into_database(filepath), on_success=self._on_parse_done)

    def parse_multiple_files(self) -> None:
        folder = filedialog.askdirectory(title="Select folder containing XML files")
        if not folder:
            return

        self.status_label.config(text="Parsing folder ...")
        self._run_background_task(task=lambda: import_folder_into_database(folder), on_success=self._on_parse_done)
    #endregion

    #region Real-Time Monitoring (need divide responsibilities)
    def start_monitoring(self) -> None:
        folder = filedialog.askdirectory(title="Select folder to monitor")
        if not folder:
            messagebox.showinfo("None selected", "Select a viable folder")
            return

        self.monitoring = True
        self.monitor_button.config(state="disabled")
        self.status_label.config(text="Live monitoring is ongoing")
        threading.Thread(target=self._monitor_folder, args=(folder,), daemon=True).start()
        # args passes positional arguments to a thread's target function
        # self.monitor_folder(*args) -> unpacks the one-element tuple into the str

    def _monitor_folder(self, folder: str) -> None:
        while self.monitoring:
            newest: str | None = self._get_newest_xml_file(folder)
            if newest is None:
                time.sleep(1) # 1 second
                continue

            try:
                self._process_live_file(newest)
            except Exception as exc:
                print("MONITOR ERROR:", exc)
                self._handle_monitoring_error(exc)

            time.sleep(1)

    @staticmethod
    def _get_newest_xml_file(folder: str) -> str | None:
        xml_files : list[str] # the paths as strings
        xml_files = glob.glob(os.path.join(folder, "*.xml")) # os.path.join builds a search pattern, e.g. "C:/Logs/*xml"
        if not xml_files:                                   # glob.glob(...) finds files matching that pattern
            return None

        return max(xml_files, key=os.path.getmtime) # since newest file has highest mtime -> max()

    def _process_live_file(self, filepath: str) -> None:
        if os.path.getsize(filepath) > 0:
            self.entries_loaded += import_unfinished_xml_into_database(filepath)
            info = f"Live: {self.entries_loaded} entries"
            self.root.after(0, lambda a=info: self.status_label.config(text=a))
            self.root.after(0, lambda : self.show_initial_page())

        new_entries: list[dict[str, str | None]] = self.live_tracker.read_new_errors(filepath)
        if not new_entries:
            return


        rows_for_db: list[tuple[str | None, ...]] = [self._convert_error_dict_to_row(entry) for entry in new_entries]
        db_ids: list[int | None] = insert_live_log_entries(rows_for_db)

        # ["date", "time", "nodetype", "module", "errorcode", "moreinfo", "sampleID", "carrierID", "offline", "full_string"]

        rows_for_graphical_ui: list[tuple[str | None, ...]] = [row[:9] for row in rows_for_db] # don't need the full_string here
        rows_for_class: list[tuple[str | None, ...]] = [row[0:2] + row [3:6] for row in rows_for_db]

        self.root.after(0, lambda ents=tuple(rows_for_graphical_ui), ids=tuple(db_ids): self.insert_live_rows(ents, ids))
        self.root.after(0, lambda ents=tuple(rows_for_class): self._ingest_live_alerts(ents))
        self.root.after(0, self.refresh_combobox_options)

    def _ingest_live_alerts(self, entries: tuple[tuple[str | None, ...], ...]) -> None:

        visualisation_entries: tuple[tuple[str | None, ...], ...] = (

            ("2026-10-24", "14:30:00", "ModuleA", "E101", "Connection failed"),

            ("2026-10-24", "14:31:00", "ModuleB", "E205", None),

            ("2026-10-24", "14:32:00", "ModuleC", "E301", "Timeout"),           )


        for entry in entries:
            #date, time, module, errorcode, moreinfo
            if entry[3] in self.blacklisted_errors:
                continue


            date, time_ = entry[0:2] # to avoid IDE's type checker yellow underline
            date: str
            time_: str
            event = ErrorEvent(date=date, time=time_, module=entry[2], errorcode=entry[3], moreinfo=entry[4])

            msg = self.rt_monitor.ingest(event)
            if msg is not None:
                self.alert_box.insert(0, "Live Alert " + msg)
                # messagebox.showwarning("Live Alert", msg) older approach, turned out very "annoying"

    def _handle_monitoring_error(self, exc: Exception) -> None:
        message = str(exc)
        self.root.after(0, lambda msg=message: self.status_label.config(text=f"Monitoring error: {msg}") )
    #endregion

    #region Extras
    def show_about(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("About")
        window.geometry("350x180")

        information = ( "Error Monitor\n" "Version 1.1\n\n" "Developed by Adam Abdulaev\n"
                        "2025-2026\n\n" "XML parsing, real-time monitoring,\n" "error analysis and filtering." )

        text = tk.Label(window, justify="left", text=information) #justify: how multiple lines of text are aligned inside the widget
        text.pack(padx=20, pady=20)
    #endregion