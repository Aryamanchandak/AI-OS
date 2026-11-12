# Version: V2
from datetime import datetime, date
from Foundation import NSTask, NSPipe, NSData


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


def _date_setter(date_str: str, time_str: str = "09:00") -> str:
    """
    Returns AppleScript snippet that sets variable `d` to the given date+time.
    date_str: YYYY-MM-DD
    time_str: HH:MM (24h)
    """
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return f"""
set d to current date
set year of d to {dt.year}
set month of d to {dt.month}
set day of d to {dt.day}
set hours of d to {dt.hour}
set minutes of d to {dt.minute}
set seconds of d to 0"""


def create_timed_event(
    summary: str,
    date_str: str,
    start_time: str,
    duration_minutes: int,
    description: str,
    calendar_name: str
) -> None:
    """Creates a timed event in the specified Apple Calendar."""
    safe_summary = summary.replace('"', '\\"')
    safe_desc = description.replace('"', '\\"')
    script = f"""
tell application "Calendar"
    launch
    tell calendar "{calendar_name}"
        {_date_setter(date_str, start_time)}
        set startDate to d
        set endDate to startDate + ({int(duration_minutes)} * minutes)
        make new event with properties {{summary:"{safe_summary}", start date:startDate, end date:endDate, description:"{safe_desc}"}}
    end tell
end tell
"""
    _run_applescript(script)


def create_allday_event(
    summary: str,
    date_str: str,
    description: str,
    calendar_name: str
) -> None:
    """Creates an all-day event (e.g. deadline) in the specified Apple Calendar."""
    safe_summary = summary.replace('"', '\\"')
    safe_desc = description.replace('"', '\\"')
    script = f"""
tell application "Calendar"
    launch
    tell calendar "{calendar_name}"
        {_date_setter(date_str, "00:00")}
        set eventDate to d
        set eventEndDate to eventDate + (1 * days)
        make new event with properties {{summary:"{safe_summary}", start date:eventDate, end date:eventEndDate, allday event:true, description:"{safe_desc}"}}
    end tell
end tell
"""
    _run_applescript(script)


def move_event(
    original_title: str,
    original_date: str,
    original_start: str,
    new_date: str,
    new_start: str,
    duration_minutes: int,
    calendar_name: str,
) -> None:
    """Moves an existing timed event to a new date/time by finding it via title + original time."""
    safe_title = original_title.replace('"', '\\"')
    script = f"""
tell application "Calendar"
    launch
    tell calendar "{calendar_name}"
        {_date_setter(original_date, "00:00")}
        set searchStart to d
        set searchEnd to searchStart + (86399)
        set matchedEvent to missing value
        set evts to (every event whose start date >= searchStart and start date <= searchEnd)
        repeat with e in evts
            if summary of e is "{safe_title}" then
                set matchedEvent to e
                exit repeat
            end if
        end repeat
        if matchedEvent is missing value then
            error "Event not found: {safe_title} on {original_date}"
        end if
        {_date_setter(new_date, new_start)}
        set newStart to d
        set newEnd to newStart + ({int(duration_minutes)} * minutes)
        set start date of matchedEvent to newStart
        set end date of matchedEvent to newEnd
    end tell
end tell
"""
    _run_applescript(script)


def delete_event(title: str, date_str: str, calendar_name: str) -> None:
    """Deletes the first matching open event by title on a given date (best-effort rollback)."""
    safe_title = title.replace('"', '\\"')
    script = f"""
tell application "Calendar"
    launch
    tell calendar "{calendar_name}"
        {_date_setter(date_str, "00:00")}
        set dayStart to d
        set dayEnd to dayStart + (86399)
        set evts to (every event whose start date >= dayStart and start date <= dayEnd)
        repeat with e in evts
            if summary of e is "{safe_title}" then
                delete e
                exit repeat
            end if
        end repeat
    end tell
end tell
"""
    _run_applescript(script)


def get_week_events(calendar_name: str) -> list[dict]:
    """
    Returns events for the next 7 days from the specified calendar.
    Each dict: {"title": str, "date": "YYYY-MM-DD", "start": "HH:MM", "end": "HH:MM", "allday": bool}
    """
    today = date.today()
    week_end = today + __import__('datetime').timedelta(days=7)
    script = f"""
tell application "Calendar"
    launch
    tell calendar "{calendar_name}"
        {_date_setter(today.isoformat(), "00:00")}
        set rangeStart to d
        {_date_setter(week_end.isoformat(), "23:59")}
        set rangeEnd to d
        set evts to (every event whose start date >= rangeStart and start date <= rangeEnd)
        set output to ""
        repeat with e in evts
            set eTitle to summary of e
            set eStart to start date of e
            set eEnd to end date of e
            set eAllDay to allday event of e
            set eDate to ((year of eStart as string) & "-" & text -2 thru -1 of ("0" & (month of eStart as integer) as string) & "-" & text -2 thru -1 of ("0" & (day of eStart) as string))
            set eStartTime to (text -2 thru -1 of ("0" & (hours of eStart) as string)) & ":" & (text -2 thru -1 of ("0" & (minutes of eStart) as string))
            set eEndTime to (text -2 thru -1 of ("0" & (hours of eEnd) as string)) & ":" & (text -2 thru -1 of ("0" & (minutes of eEnd) as string))
            if eAllDay then
                set eAllDayStr to "true"
            else
                set eAllDayStr to "false"
            end if
            set output to output & eTitle & tab & eDate & tab & eStartTime & tab & eEndTime & tab & eAllDayStr & "\n"
        end repeat
        return output
    end tell
end tell
"""
    try:
        raw = _run_applescript(script)
    except RuntimeError:
        return []

    events = []
    for line in raw.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 5:
            events.append({
                "title": parts[0],
                "date": parts[1],
                "start": parts[2],
                "end": parts[3],
                "allday": parts[4].strip().lower() == "true",
            })
    return events


def edit_event(
    title: str,
    date_str: str,
    calendar_name: str,
    new_title: str | None = None,
    new_description: str | None = None,
    new_duration_minutes: int | None = None,
) -> None:
    """Edit an existing event's title, description, or duration without rescheduling it."""
    safe_title = title.replace('"', '\\"')
    updates = []
    if new_title is not None:
        safe_new_title = new_title.replace('"', '\\"')
        updates.append(f'set summary of matchedEvent to "{safe_new_title}"')
    if new_description is not None:
        safe_desc = new_description.replace('"', '\\"')
        updates.append(f'set description of matchedEvent to "{safe_desc}"')
    if new_duration_minutes is not None:
        updates.append(f"set end date of matchedEvent to (start date of matchedEvent) + ({int(new_duration_minutes)} * minutes)")
    if not updates:
        return
    update_block = "\n        ".join(updates)
    script = f"""
tell application "Calendar"
    launch
    tell calendar "{calendar_name}"
        {_date_setter(date_str, "00:00")}
        set dayStart to d
        set dayEnd to dayStart + (86399)
        set matchedEvent to missing value
        set evts to (every event whose start date >= dayStart and start date <= dayEnd)
        repeat with e in evts
            if summary of e is "{safe_title}" then
                set matchedEvent to e
                exit repeat
            end if
        end repeat
        if matchedEvent is missing value then
            error "Event not found: {safe_title} on {date_str}"
        end if
        {update_block}
    end tell
end tell
"""
    _run_applescript(script)


def get_today_events(calendar_name: str) -> list[dict]:
    """
    Returns today's events from the specified calendar as a list of dicts:
    [{"title": "...", "start": "..."}]
    """
    today = date.today()
    script = f"""
tell application "Calendar"
    launch
    tell calendar "{calendar_name}"
        {_date_setter(today.isoformat(), "00:00")}
        set dayStart to d
        set dayEnd to dayStart + (86399)
        set evts to (every event whose start date >= dayStart and start date <= dayEnd)
        set output to ""
        repeat with e in evts
            set output to output & (summary of e) & tab & ((start date of e) as string) & "\n"
        end repeat
        return output
    end tell
end tell
"""
    try:
        raw = _run_applescript(script)
    except RuntimeError:
        return []

    events = []
    for line in raw.strip().splitlines():
        if "\t" in line:
            parts = line.split("\t", 1)
            events.append({"title": parts[0], "start": parts[1]})
    return events
