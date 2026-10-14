from datetime import datetime
from Foundation import NSTask, NSPipe, NSData


def _escape_as(s: str) -> str:
    """Escape a string for safe interpolation inside AppleScript double-quoted strings."""
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '')


def _run_applescript(script: str) -> str:
    """Runs AppleScript via NSTask (posix_spawn, no fork). Thread-safe."""
    stdin_pipe = NSPipe.pipe()
    stdout_pipe = NSPipe.pipe()
    stderr_pipe = NSPipe.pipe()

    task = NSTask.alloc().init()
    task.setLaunchPath_('/usr/bin/osascript')
    task.setArguments_(['-'])
    task.setStandardInput_(stdin_pipe)
    task.setStandardOutput_(stdout_pipe)
    task.setStandardError_(stderr_pipe)
    task.launch()

    data = script.encode('utf-8')
    stdin_pipe.fileHandleForWriting().writeData_(NSData.dataWithBytes_length_(data, len(data)))
    stdin_pipe.fileHandleForWriting().closeFile()

    stdout = bytes(stdout_pipe.fileHandleForReading().readDataToEndOfFile()).decode('utf-8').strip()
    stderr = bytes(stderr_pipe.fileHandleForReading().readDataToEndOfFile()).decode('utf-8').strip()
    task.waitUntilExit()

    if task.terminationStatus() != 0:
        msg = stderr or stdout or "(no error output)"
        raise RuntimeError(f"AppleScript error: {msg}")
    return stdout


def _date_setter(date_str: str, time_str: str = "") -> str:
    """
    Returns AppleScript snippet setting variable `d` to the given date (and optional time).
    date_str: YYYY-MM-DD
    time_str: HH:MM (24h). If empty, sets to 00:00 (start of day / no alarm time).
    """
    t = time_str.strip() if time_str else "00:00"
    dt = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M")
    return f"""
set d to current date
set year of d to {dt.year}
set month of d to {dt.month}
set day of d to {dt.day}
set hours of d to {dt.hour}
set minutes of d to {dt.minute}
set seconds of d to 0"""


def ensure_list(list_name: str) -> None:
    """Creates the reminder list if it doesn't already exist."""
    safe_name = _escape_as(list_name)
    script = f"""
tell application "Reminders"
    if not (exists list "{safe_name}") then
        make new list with properties {{name:"{safe_name}"}}
    end if
end tell
"""
    _run_applescript(script)


def create_reminder(
    title: str,
    notes: str,
    due_date_str: str,
    list_name: str,
    due_time_str: str = "",
) -> None:
    """
    Creates a reminder with a due date (and optional time) in the specified list.
    due_time_str: HH:MM 24h. If provided, the reminder will alert at that time.
    If omitted, the reminder lands at midnight (no timed alert).
    """
    safe_title = _escape_as(title)
    safe_notes = _escape_as(notes)
    safe_list = _escape_as(list_name)
    script = f"""
tell application "Reminders"
    tell list "{safe_list}"
        {_date_setter(due_date_str, due_time_str)}
        set dueDate to d
        make new reminder with properties {{name:"{safe_title}", body:"{safe_notes}", due date:dueDate, remind me date:dueDate}}
    end tell
end tell
"""
    _run_applescript(script)


def list_open_reminders(list_name: str) -> list[dict]:
    """Returns open (non-completed) reminders from the list as dicts: [{"title": ..., "due": ...}]"""
    safe_list = _escape_as(list_name)
    script = f"""
tell application "Reminders"
    if not (exists list "{safe_list}") then
        return ""
    end if
    set output to ""
    set openReminders to (reminders of list "{safe_list}" whose completed is false)
    repeat with r in openReminders
        set rName to name of r
        try
            set rDue to (due date of r) as string
        on error
            set rDue to "no date"
        end try
        set output to output & rName & tab & rDue & "\n"
    end repeat
    return output
end tell
"""
    try:
        raw = _run_applescript(script)
    except RuntimeError:
        return []

    reminders = []
    for line in raw.strip().splitlines():
        if "\t" in line:
            parts = line.split("\t", 1)
            reminders.append({"title": parts[0], "due": parts[1]})
    return reminders


def list_all_open_reminders() -> list[dict]:
    """
    Returns all incomplete reminders from ALL lists.
    Each dict: {"title": str, "due": "YYYY-MM-DD" | None, "list": str, "created": "YYYY-MM-DD" | None}
    """
    script = """
tell application "Reminders"
    set output to ""
    repeat with aList in every list
        set listName to name of aList
        set openItems to (reminders of aList whose completed is false)
        set itemCount to count of openItems
        if itemCount > 0 then
            set rNames to name of every reminder of aList whose completed is false
            repeat with i from 1 to itemCount
                set r to item i of openItems
                set rName to item i of rNames
                try
                    set rDue to (due date of r)
                    set rDueStr to ((year of rDue as string) & "-" & text -2 thru -1 of ("0" & (month of rDue as integer) as string) & "-" & text -2 thru -1 of ("0" & (day of rDue) as string))
                on error
                    set rDueStr to "none"
                end try
                try
                    set rCreated to (creation date of r)
                    set rCreatedStr to ((year of rCreated as string) & "-" & text -2 thru -1 of ("0" & (month of rCreated as integer) as string) & "-" & text -2 thru -1 of ("0" & (day of rCreated) as string))
                on error
                    set rCreatedStr to "none"
                end try
                set output to output & rName & tab & rDueStr & tab & listName & tab & rCreatedStr & "\n"
            end repeat
        end if
    end repeat
    return output
end tell
"""
    try:
        raw = _run_applescript(script)
    except RuntimeError:
        return []

    reminders = []
    for line in raw.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            reminders.append({
                "title": parts[0],
                "due": parts[1] if parts[1] != "none" else None,
                "list": parts[2],
                "created": parts[3] if parts[3] != "none" else None,
            })
    return reminders


def update_reminder_date(title: str, list_name: str, new_date_str: str, new_time_str: str = "") -> None:
    """
    Updates the due date (and optional time) of an existing reminder matched by title.
    new_time_str: HH:MM 24h. If provided, sets a timed alert. If omitted, sets to midnight.
    """
    safe_title = _escape_as(title)
    safe_list = _escape_as(list_name)
    script = f"""
tell application "Reminders"
    tell list "{safe_list}"
        {_date_setter(new_date_str, new_time_str)}
        set newDue to d
        set matches to (reminders whose name is "{safe_title}" and completed is false)
        if (count of matches) > 0 then
            set due date of item 1 of matches to newDue
            set remind me date of item 1 of matches to newDue
        else
            error "No open reminder found with title \\"{safe_title}\\" in list \\"{safe_list}\\""
        end if
    end tell
end tell
"""
    _run_applescript(script)


def delete_reminder(title: str, list_name: str) -> None:
    """Deletes the first open reminder matching title in the list (best-effort rollback)."""
    safe_title = _escape_as(title)
    safe_list = _escape_as(list_name)
    script = f"""
tell application "Reminders"
    tell list "{safe_list}"
        set matches to (reminders whose name is "{safe_title}" and completed is false)
        if (count of matches) > 0 then
            delete item 1 of matches
        end if
    end tell
end tell
"""
    _run_applescript(script)


def clear_list(list_name: str) -> None:
    """Deletes all reminders in a list (used to refresh the 'Today' list)."""
    safe_list = _escape_as(list_name)
    script = f"""
tell application "Reminders"
    if exists list "{safe_list}" then
        delete every reminder of list "{safe_list}"
    else
        make new list with properties {{name:"{safe_list}"}}
    end if
end tell
"""
    _run_applescript(script)


def complete_reminder(title: str, list_name: str) -> None:
    """Marks the first reminder matching the title as complete."""
    safe_title = _escape_as(title)
    safe_list = _escape_as(list_name)
    script = f"""
tell application "Reminders"
    tell list "{safe_list}"
        set matches to (reminders whose name is "{safe_title}" and completed is false)
        if (count of matches) > 0 then
            set completed of item 1 of matches to true
        end if
    end tell
end tell
"""
    _run_applescript(script)