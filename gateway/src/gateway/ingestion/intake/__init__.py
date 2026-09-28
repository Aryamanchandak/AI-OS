"""Pre-ingestion funnel for turning dropped files into reviewed Markdown."""

from gateway.ingestion.intake.base import Extractor, IntakeResult
from gateway.ingestion.intake.funnel import (
    DownstreamUnavailableError,
    FunnelFileResult,
    FunnelRunReport,
    PreparedFile,
    UnroutableFileError,
    move_published_source,
    prepare_file,
    publish_prepared,
    route_file,
    run_funnel,
    scan_drop_folder,
)

__all__ = [
    "DownstreamUnavailableError",
    "Extractor",
    "FunnelFileResult",
    "FunnelRunReport",
    "IntakeResult",
    "PreparedFile",
    "UnroutableFileError",
    "move_published_source",
    "prepare_file",
    "publish_prepared",
    "route_file",
    "run_funnel",
    "scan_drop_folder",
]
