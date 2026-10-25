from collections import defaultdict, deque
from datetime import datetime, timedelta
import os
import re
from utils import parse_any_datetime
from parser import parse_one_live_error

class ErrorEvent:
    def __init__(self, date: str, time: str, module: str | None, errorcode: str | None, moreinfo: str | None):
        timestamp = date + " " + time
        self.dt = parse_any_datetime(timestamp)
        self.module = module
        self.errorcode = errorcode
        self.moreinfo = moreinfo

class LiveXMLTracker:
    def __init__(self):
        self.current_file: str | None = None
        self.last_size: int = 0
        self.encoding = None # reading in bytes first so that we can tell certainly where the file was read last time
        self.buffer: str = "" # this will contain the raw XML lines as strings, there may be unfinished entries.
        self.first_file = True # implemented this to avoid "old_errors" being inserted into RTMonitor and the resulting spam

                                                 #   <Error ........"/>
        self.pattern: re.Pattern[str] = re.compile(r"<Error\b[^>]*/>") # * match zero or more characters

    def read_new_errors(self, filepath: str) -> list[dict[str, str | None]]:
        if self.first_file:
            self._set_start(filepath)

        self._reset_state_for_new_file(filepath)

        byte_xml_text = self._read_new_bytes(filepath)
        if not byte_xml_text:
            return []

        self._ensure_encoding(byte_xml_text)
        self.buffer += byte_xml_text.decode(self.encoding, errors="ignore")
        entries: list[dict[str, str | None ]] = self._convert_str_text_to_entries()


        return entries

    def _set_start(self, filepath: str) -> None:
        self.first_file = False

        self.current_file = filepath

        self.current_size = os.path.getsize(filepath) # avoids RT_Monitor spam bug for already pre-written lines

        self.last_size = self.current_size

    def _reset_state_for_new_file(self, filepath: str, hard_reset: bool = False) -> None:
        if self.current_file == filepath and not hard_reset:
            return

        self.current_file = filepath
        self.last_size = 0
        self.encoding = None
        self.buffer = ""

    def _read_new_bytes(self, filepath: str) -> bytes:
        try:
            current_size = os.path.getsize(filepath)
        except OSError:
            return b""

        if self.last_size > current_size:
            self._reset_state_for_new_file(filepath, True)

        with open(filepath, "rb") as file_handle:
            file_handle.seek(self.last_size)
            content = file_handle.read()
            self.last_size = file_handle.tell()

        return content

    def _ensure_encoding(self, xml_byte_text: bytes) -> None:
        if self.encoding is None:
            self.encoding = self._detect_encoding(xml_byte_text)

    def _convert_str_text_to_entries(self) -> list[dict[str, str | None]]:
        entries_from_xml: list[dict[str, str | None]] = []

        while True:
            entry_match = self.pattern.search(self.buffer) # based on the pattern, isolate each full error
            if not entry_match:
                break
            completed_str_entry = entry_match.group(0)   # entry_match is a match object containing multiple data
            self.buffer = self.buffer[entry_match.end():] # we don't to parse the same error multiple times

            entry: dict[str, str | None] | None = self._call_parse_one_live_error(completed_str_entry)
            if entry is not None:
                entries_from_xml.append(entry)

        return entries_from_xml

    @staticmethod
    def _call_parse_one_live_error(raw_entry: str) -> dict[str, str | None] | None:
        try:
            return parse_one_live_error(raw_entry)
        except Exception:
            return None

    @staticmethod
    def _detect_encoding(xml_byte_text: bytes) -> str:
        if xml_byte_text.startswith(b"\xff\xfe") or xml_byte_text.startswith(b"\xfe\xff"):
            return "utf-16"  # easier to return then directly assign self.encoding, that's why static
        elif xml_byte_text.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"

        sniff_of_byte_text = xml_byte_text[:200].decode("ascii", errors="ignore").lower()  # skip "Unicode Decode Error"
        # ascii because it works well for examining ordinary XML declarations
        if "encoding" not in sniff_of_byte_text:
            return "utf-8"

        match = re.search(r'encoding=["\']([^"\']+)["\']', sniff_of_byte_text)
        return match.group(1) if match else "utf-8"

class RealTimeMonitor:
    def __init__(self):
        self.global_errors: dict[str | None, deque[datetime]] = defaultdict(deque)
        self.module_errors: dict[tuple[str | None, str | None], deque[datetime]] = defaultdict(deque)
        self.last_module_alert: dict[tuple[str | None, str | None], datetime | None] = {}
        self.last_global_alert: dict[str | None, datetime | None] = {}
        self.suppress_global_until: dict[str | None, datetime] = {}
        self.module_window = timedelta(minutes=5)
        self.global_window = timedelta(minutes=2)
        self.limit = 5

    def ingest(self, event: ErrorEvent) -> str | None:
        now = event.dt

        if event.errorcode is None:
            return None

        module_msg = self._check_module(event, now)
        if  module_msg:
            self.suppress_global_until[event.errorcode] = now + self.global_window

        if self.suppress_global_until.get(event.errorcode, datetime.min) > now:
            return None

        return self._check_global(event, now)

    def _check_module(self, event: ErrorEvent, now: datetime) -> str | None:
        key = event.module, event.errorcode
        dt_times: deque[datetime] = self.module_errors[key]
        self._append_and_prune(dt_times, now, self.module_window)

        last = self.last_module_alert.get(key)
        if not self._should_alert(len(dt_times), last, now, self.module_window):
            return None

        self.last_module_alert[key] = now
        minutes = self.module_window.total_seconds()//60
        exact_time = datetime.now().strftime("%H:%M:%S")

        return (f"{exact_time} {event.module}: Error '{event.errorcode}' - {event.moreinfo} occurred"
                f"{self.limit} times in the last {minutes} minutes" )

    def _check_global(self, event: ErrorEvent, now:datetime) -> str | None:
        key = event.errorcode
        dt_times: deque[datetime] = self.global_errors[key]
        self._append_and_prune(dt_times, now, self.global_window)

        last = self.last_global_alert.get(key)
        if not self._should_alert(len(dt_times), last, now, self.global_window):
            return None

        self.last_global_alert[key] = now
        minutes = self.global_window.total_seconds() // 60
        exact_time = datetime.now().strftime("%H:%M:%S")

        return (f"{exact_time} GLOBAL: Error '{event.errorcode}' - {event.moreinfo} occurred"
                f"{self.limit} times in the last {minutes} minutes")

    @staticmethod
    def _append_and_prune(dt_times: deque[datetime], now: datetime, window: timedelta) -> None:
        dt_times.append(now)
        while dt_times and now - dt_times[0] > window:
            dt_times.popleft()

    def _should_alert(self, count: int, last_alert: datetime | None, now: datetime, window: timedelta) -> bool:
        if count < self.limit:
            return False
        return last_alert is None or now - last_alert > window # if the last alert has been over 5 minutes ago