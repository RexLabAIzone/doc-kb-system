import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

from config import setup_logging, WORKERS, OUTPUT_DIR, RESUME_FILE
from scanner import scan_directory, resume_scan, cancel_scan, reset_cancel
from checker import check_file as _check_single
from reporter import export_excel, export_csv, generate_summary_text
from ai_analyzer import analyze_results, generate_report_html

logger = setup_logging("health_checker")


class HealthChecker:
    def __init__(self, config=None):
        self.config = config or {}
        self.scan_root = self.config.get("SCAN_ROOT", "/data/originals")
        self.workers = int(self.config.get("WORKERS", WORKERS))
        self.output_dir = self.config.get("OUTPUT_DIR", OUTPUT_DIR)
        self.resume_file = self.config.get("RESUME_FILE", RESUME_FILE)
        self.ai_model = self.config.get("AI_MODEL", "qwen2.5:7b")
        self.ollama_url = self.config.get("OLLAMA_URL", "http://192.168.99.210:11434")
        self.scanned_files = []
        self.check_results = []
        self.ai_analysis = None
        self._cancel_event = threading.Event()
        self._check_lock = threading.Lock()
        self._scan_lock = threading.Lock()

    def cancel(self):
        self._cancel_event.set()
        cancel_scan()

    def reset(self):
        self._cancel_event.clear()
        reset_cancel()
        self.scanned_files = []
        self.check_results = []
        self.ai_analysis = None

    @property
    def is_cancelled(self):
        return self._cancel_event.is_set()

    def run_scan(self):
        self.scanned_files = scan_directory(
            self.scan_root,
            workers=self.workers,
            resume_file=self.resume_file if self.config.get("RESUME") else None,
        )
        return self.scanned_files

    def run_checks(self, files=None, workers=None):
        if files is None:
            files = self.scanned_files
        if workers is None:
            workers = self.workers
        results = []
        lock = threading.Lock()
        with tqdm(total=len(files), desc="Checking files", unit="file") as pbar:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                fmap = {executor.submit(_check_single, f): f for f in files}
                for future in as_completed(fmap):
                    if self.is_cancelled:
                        break
                    try:
                        r = future.result()
                    except Exception as e:
                        f = fmap[future]
                        r = {
                            "path": f["path"],
                            "name": f["name"],
                            "ext": f["ext"],
                            "size": f["size"],
                            "category": f["category"],
                            "status": "error",
                            "issues": [
                                {
                                    "severity": "error",
                                    "type": "thread_error",
                                    "message": str(e),
                                }
                            ],
                            "encoding": None,
                            "charset_confidence": None,
                            "page_count": None,
                            "image_dimensions": None,
                            "duration_ms": 0,
                            "ai_summary": None,
                        }
                    with lock:
                        results.append(r)
                    pbar.update(1)
        self.check_results = results
        return results

    def export(self, reports=None):
        if reports is None:
            reports = self.check_results
        os.makedirs(self.output_dir, exist_ok=True)
        paths = {}
        paths["xlsx"] = os.path.join(self.output_dir, "health_report.xlsx")
        paths["csv"] = os.path.join(self.output_dir, "health_report.csv")
        export_excel(reports, paths["xlsx"])
        export_csv(reports, paths["csv"])
        txt = os.path.join(self.output_dir, "health_summary.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write(generate_summary_text(reports))
        paths["txt"] = txt
        if self.ai_analysis:
            paths["html"] = os.path.join(self.output_dir, "health_report.html")
            with open(paths["html"], "w", encoding="utf-8") as f:
                f.write(generate_report_html(reports, self.ai_analysis))
        return paths

    def analyze(self, reports=None):
        if reports is None:
            reports = self.check_results
        self.ai_analysis = analyze_results(
            reports, model=self.ai_model, ollama_url=self.ollama_url
        )
        return self.ai_analysis

    def full_check(self):
        self.reset()
        self.run_scan()
        if not self.is_cancelled:
            self.run_checks()
            self.export()
            self.analyze()
        return {
            "files_scanned": len(self.scanned_files),
            "results": self.check_results,
            "ai_analysis": self.ai_analysis,
        }
