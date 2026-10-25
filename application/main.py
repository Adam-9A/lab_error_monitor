TABLE_COLUMNS = ( "id", "date", "time", "nodetype", "module",
                  "errorcode", "moreinfo", "sampleID", "carrierID", "offline" )


from tkinter import messagebox
from graphical_ui import ErrorMonitor
from database import ensure_db, init_db
import tkinter as tk


def main() -> None:
    # Ensure DB exists. If missing, initialize schema + indexes.
    try:
        ensure_db()
        # ensure_db() only creates if missing; init_db() is safe and idempotent,
        # so calling it won't hurt and guarantees indexes exist.
        init_db()
    except Exception as e:
        # If DB is broken, don't launch a half-working GUI.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Database error", f"Failed to initialize database:\n{e}")
        return

    root = tk.Tk()
    ErrorMonitor(root)
    root.mainloop()



if __name__ == "__main__":
    main()
