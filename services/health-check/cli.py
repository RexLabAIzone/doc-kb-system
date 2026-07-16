#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import signal

from config import setup_logging, OUTPUT_DIR, WORKERS, RESUME_FILE, MAX_FILE_SIZE_MB, SCAN_ROOT
from health_checker import HealthChecker

logger = setup_logging("cli")


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Document Health Check Tool - Scan, analyze, and report on document health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m doc_health_check.cli /data/originals
  python -m doc_health_check.cli /data/originals --workers 16 --output ./reports
  python -m doc_health_check.cli /data/originals --ai --resume
  python -m doc_health_check.cli /data/originals --skip-encoding --skip-openable
        """,
    )

    parser.add_argument("scan_root", nargs="?", default=None,
                        help=f"Directory to scan (default: {SCAN_ROOT})")
    parser.add_argument("--workers", "-w", type=int, default=None,
                        help=f"Number of worker threads (default: {WORKERS})")
    parser.add_argument("--output", "-o", default=None,
                        help=f"Output directory for reports (default: {OUTPUT_DIR})")
    parser.add_argument("--resume", "-r", action="store_true",
                        help="Resume from previous scan progress")
    parser.add_argument("--resume-file", default=None,
                        help=f"Resume checkpoint file (default: {RESUME_FILE})")
    parser.add_argument("--ai", "-a", action="store_true",
                        help="Enable AI analysis via Ollama")
    parser.add_argument("--ai-model", default=None,
                        help="Ollama model for AI analysis (default: qwen2.5:7b)")
    parser.add_argument("--ollama-url", default=None,
                        help="Ollama API URL (default: http://192.168.99.210:11434)")
    parser.add_argument("--max-size", type=int, default=None,
                        help=f"Max file size in MB to check (default: {MAX_FILE_SIZE_MB})")
    parser.add_argument("--skip-encoding", action="store_true",
                        help="Skip encoding checks")
    parser.add_argument("--skip-openable", action="store_true",
                        help="Skip openability checks")
    parser.add_argument("--skip-corruption", action="store_true",
                        help="Skip corruption checks")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--version", action="store_true",
                        help="Show version and exit")

    args = parser.parse_args(argv)

    if args.version:
        try:
            from . import __version__
            print(f"Document Health Check Tool v{__version__}")
        except ImportError:
            print("Document Health Check Tool v1.0.0")
        return

    config = {
        "SCAN_ROOT": args.scan_root or SCAN_ROOT,
        "OUTPUT_DIR": args.output or OUTPUT_DIR,
        "WORKERS": args.workers or WORKERS,
        "RESUME_FILE": args.resume_file or RESUME_FILE,
        "RESUME": args.resume,
        "AI_MODEL": args.ai_model or "qwen2.5:7b",
        "OLLAMA_URL": args.ollama_url or "http://192.168.99.210:11434",
        "MAX_FILE_SIZE_MB": args.max_size or MAX_FILE_SIZE_MB,
        "CHECK_ENCODING": not args.skip_encoding,
        "CHECK_OPENABLE": not args.skip_openable,
        "CHECK_CORRUPTION": not args.skip_corruption,
    }

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    scan_root = config["SCAN_ROOT"]
    if not os.path.exists(scan_root):
        logger.error("Scan root does not exist: %s", scan_root)
        sys.exit(1)
    if not os.path.isdir(scan_root):
        logger.error("Scan root is not a directory: %s", scan_root)
        sys.exit(1)

    checker = HealthChecker(config)

    def signal_handler(signum, frame):
        logger.warning("Received signal %d, cancelling...", signum)
        checker.cancel()
        print("\nCancelling... (this may take a moment)")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        result = checker.full_check()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Progress has been saved.")
        sys.exit(1)

    if result.get("cancelled"):
        print("\nCheck was cancelled.")
        sys.exit(1)

    files_count = result["files_scanned"]
    paths = result["export_paths"]
    duration = result["duration_seconds"]

    print(f"\n{'=' * 60}")
    print(f"  CHECK COMPLETE")
    print(f"  Files scanned: {files_count:,}")
    print(f"  Duration: {duration:.1f} seconds")
    print(f"  Reports:")
    for fmt, p in paths.items():
        if p and os.path.exists(p):
            print(f"    - {fmt.upper()}: {p}")
    print(f"{'=' * 60}")

    if args.ai and result.get("ai_analysis"):
        print(f"\nAI Analysis:")
        print(result["ai_analysis"])


if __name__ == "__main__":
    main()
