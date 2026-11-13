"""Command-line entry point for checks, reports, local answers and a labelled offline demo."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_watch
from .demo import run_demo
from .monitor import Monitor
from .report import save_brief
from .store import Store


def write_brief(state, monitor):
    path = save_brief(state, monitor)
    print(f'Brief: {path.resolve()}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Zero-spend, local public-page watchlist')
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'watch.toml')
    parser.add_argument('--state', type=Path, default=Path('.watchlist'))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='Fetch only due selected pages; preserve limits across restarts')
    commands.add_parser('report', help='Regenerate the local Markdown brief without network access')
    commands.add_parser('demo', help='Show the whole journey with synthetic content and no network calls')
    serve = commands.add_parser('serve', help='Open the local dashboard at http://127.0.0.1:8765')
    serve.add_argument('--port', type=int, default=8765)
    answer = commands.add_parser('answer', help='Complete an existing pending item locally')
    answer.add_argument('item', type=int)
    answer.add_argument('--decision', choices=('finding', 'ignored'), required=True)
    answer.add_argument('--answer', required=True)
    args = parser.parse_args(argv)
    store = None
    try:
        watch = load_watch(args.config)
        store = Store(args.state / 'watch.db', watch)
        monitor = Monitor(watch, store)
        if args.command == 'serve':
            from .web import create_server
            with create_server(watch, args.state, args.port) as server:
                print(f'Local dashboard: http://127.0.0.1:{server.server_port}', flush=True)
                print('Manual checks only. Press Ctrl+C to stop.', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
            return 0
        elif args.command == 'demo':
            print('SIMULATED DEMO: synthetic changes on the configured URLs; no network or model calls.')
            run_demo(watch, store, args.state)
        elif args.command == 'check':
            if (args.state / '.simulated').exists():
                raise ValueError('Use a separate --state directory for real monitoring; this state contains a simulated demo')
            results = monitor.check()
            for result in results:
                print(f'{result["status"]}: {result["url"]}')
            write_brief(args.state, monitor)
            return 1 if any(result['status'] == 'failed' for result in results) else 0
        elif args.command == 'answer':
            store.answer(args.item, args.decision, args.answer, datetime.now(timezone.utc))
            print(f'Completed item {args.item} as {args.decision}; no external action taken.')
        write_brief(args.state, monitor)
        return 0
    except (ValueError, TypeError, OSError, RuntimeError, KeyError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
