# Administration UI decision

`glc_v5/static/channels.html` is replaced by the React shell at `/channels`.
The shell preserves setup instructions, redacted credential presence, explicit
activation, webhook URLs, and health/boundary status.

The legacy dashboard, help, and observability pages are not channel setup
surfaces and are retained until their own shell/API parity is delivered. This
avoids removing a capability before an equivalent exists.
