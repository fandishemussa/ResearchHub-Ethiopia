from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import SOURCES
from .downloader import DocumentDownloadRunner, write_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download publicly accessible PDF, DOC, and DOCX research documents from BDU, WKU, and AAU repositories."
    )
    parser.add_argument("--source", choices=[*SOURCES.keys(), "all"], required=True)
    parser.add_argument("--output-dir", default="downloads")
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Maximum metadata records to inspect per source",
    )
    parser.add_argument(
        "--max-downloads",
        type=int,
        default=None,
        help="Maximum successful/existing documents per source",
    )
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument(
        "--from-date", default=None, help="OAI-PMH incremental date, e.g. 2026-01-01"
    )
    parser.add_argument("--set", dest="set_spec", default=None, help="OAI-PMH setSpec")
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Read timeout in seconds for slow downloads",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=15,
        help="Number of retry and resume attempts",
    )
    parser.add_argument(
        "--delay", type=float, default=1.5, help="Polite delay after every request"
    )
    parser.add_argument("--max-file-size-mb", type=int, default=250)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--all-pdfs",
        "--all-documents",
        dest="all_pdfs",
        action="store_true",
        help="Download every supported document for each item",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification only for troubleshooting",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    output_dir = Path(args.output_dir)
    keys = list(SOURCES) if args.source == "all" else [args.source]
    exit_code = 0
    for key in keys:
        source = SOURCES[key]
        logging.info("Starting source: %s", source.name)
        runner = DocumentDownloadRunner(
            source,
            output_dir,
            timeout=args.timeout,
            retries=args.retries,
            delay=args.delay,
            verify_tls=not args.insecure,
            overwrite=args.overwrite,
            max_file_size_mb=args.max_file_size_mb,
            all_pdfs=args.all_pdfs,
        )
        try:
            results = runner.run(
                max_records=args.max_records,
                max_downloads=args.max_downloads,
                from_date=args.from_date,
                set_spec=args.set_spec,
                page_size=args.page_size,
                resume=args.resume,
            )
            summary_path = write_summary(output_dir, key, results)
            logging.info("Finished %s. Summary: %s", key, summary_path)
        except KeyboardInterrupt:
            runner.close()
            logging.warning("Cancelled. Run again with --resume.")
            return 130
        except Exception:
            runner.close()
            logging.exception("Source %s failed", key)
            exit_code = 1
    return exit_code
