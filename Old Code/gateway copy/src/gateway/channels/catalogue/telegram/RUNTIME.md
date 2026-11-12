# Runtime boundary

**Worker.** Telegram long-polling holds an indefinite loop and is supervised with cancellation-safe shutdown and exponential backoff. Its Gateway address comes from `config/services.yaml`; it is disabled by default.

After activation, run `python -m gateway.channels.catalogue.telegram.worker` under the host process supervisor.
