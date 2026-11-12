# Runtime boundary

**Worker.** Discord keeps a long-lived gateway connection, so a reconnect loop or SDK failure must not share Gateway's crash domain. It is registered but disabled by default.
