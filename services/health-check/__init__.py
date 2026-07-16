from config import (
    SCAN_ROOT, OUTPUT_DIR, WORKERS, RESUME_FILE,
    AI_MODEL, OLLAMA_URL, MAX_FILE_SIZE_MB,
    CHECK_ENCODING, CHECK_OPENABLE, CHECK_CORRUPTION,
    SUSPICIOUS_CHARS_THRESHOLD,
)
from file_types import FILE_CATEGORIES, EXTENSION_MAP, get_category, is_supported
from scanner import scan_directory, resume_scan, cancel_scan
from checker import check_file
from reporter import export_excel, export_csv, generate_summary_text
from ai_analyzer import analyze_results, generate_report_html
from health_checker import HealthChecker
from cli import main as cli_main

__version__ = "1.0.0"
__all__ = [
    "SCAN_ROOT", "OUTPUT_DIR", "WORKERS", "RESUME_FILE",
    "AI_MODEL", "OLLAMA_URL", "MAX_FILE_SIZE_MB",
    "CHECK_ENCODING", "CHECK_OPENABLE", "CHECK_CORRUPTION",
    "SUSPICIOUS_CHARS_THRESHOLD",
    "FILE_CATEGORIES", "EXTENSION_MAP", "get_category", "is_supported",
    "scan_directory", "resume_scan", "cancel_scan",
    "check_file",
    "export_excel", "export_csv", "generate_summary_text",
    "analyze_results", "generate_report_html",
    "HealthChecker",
    "cli_main",
]
