# Computer-Use skill

Drive a named macOS window through cua-driver, trying extraction first, supplied
hotkeys next, the Electron page branch when configured, accessibility judgment,
and finally vision. The skill chooses the cheapest applicable path.

Required metadata: app and goal. Supply expect for a visible postcondition or
expect_window_title for an independently checked window title. A model declaring
done is insufficient proof. read_only permits pure extraction.

Optional keys enable deterministic input. electron_debugging_port enables the
page tool; expect_active_tab checks the active editor tab exactly. The runner
launches a separate editor profile and supplies its pid and window_id. force_path
is a diagnostic escape hatch; assignment runs must leave it unset.

Missing driver permissions or an unavailable app require human setup. Do not
replan around them. Every successful run must have a finalized native recording.
