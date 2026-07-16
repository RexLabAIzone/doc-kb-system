#!/usr/bin/env python3
"""
GUI for Document Health Check Tool.
Uses PySide6 if available, falls back gracefully.
"""

import os
import sys
import threading
import time
import logging

logger = logging.getLogger("gui")

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar,
        QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit,
        QGroupBox, QGridLayout, QSplitter, QMessageBox, QTabWidget,
        QComboBox, QStatusBar,
    )
    from PySide6.QtCore import Qt, QThread, Signal, QTimer
    from PySide6.QtGui import QFont, QColor, QBrush, QPalette
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False

from config import setup_logging, OUTPUT_DIR, WORKERS, SCAN_ROOT
from health_checker import HealthChecker

logger = setup_logging("gui")


class ScanWorker(QThread):
    progress_update = Signal(int, int)
    file_scanned = Signal(str)
    check_complete = Signal(object)
    status_update = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.checker = HealthChecker(config)

    def run(self):
        try:
            self.status_update.emit("Scanning directory...")
            files = self.checker.run_scan()
            self.status_update.emit(f"Scan complete: {len(files)} files. Checking files...")

            results = self.checker.run_checks(files)
            self.status_update.emit(f"Check complete: {len(results)} files checked.")

            self.checker.export(results)

            if self.config.get("RUN_AI"):
                self.status_update.emit("Running AI analysis...")
                self.checker.analyze(results)
                self.status_update.emit("AI analysis complete.")

            self.check_complete.emit(self.checker)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def cancel(self):
        self.checker.cancel()


class HealthCheckGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.checker = None
        self.worker = None
        self.config = {}
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("Document Health Check Tool")
        self.setMinimumSize(1200, 800)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        top_layout = QHBoxLayout()

        dir_layout = QVBoxLayout()
        dir_label = QLabel("Scan Directory:")
        self.dir_input = QLineEdit(SCAN_ROOT)
        self.dir_input.setPlaceholderText("Select directory to scan...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_input)
        dir_row.addWidget(browse_btn)
        dir_layout.addWidget(dir_label)
        dir_layout.addLayout(dir_row)
        top_layout.addLayout(dir_layout)

        options_group = QGroupBox("Options")
        options_layout = QGridLayout()

        options_layout.addWidget(QLabel("Workers:"), 0, 0)
        self.workers_input = QLineEdit(str(WORKERS))
        self.workers_input.setMaximumWidth(60)
        options_layout.addWidget(self.workers_input, 0, 1)

        self.ai_check = QPushButton("AI Analysis: OFF")
        self.ai_check.setCheckable(True)
        self.ai_check.clicked.connect(lambda: self.ai_check.setText(
            "AI Analysis: ON" if self.ai_check.isChecked() else "AI Analysis: OFF"
        ))
        options_layout.addWidget(self.ai_check, 0, 2)

        self.start_btn = QPushButton("Start Check")
        self.start_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 8px 20px;")
        self.start_btn.clicked.connect(self._start_check)
        options_layout.addWidget(self.start_btn, 0, 3)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold; padding: 8px 20px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_check)
        options_layout.addWidget(self.stop_btn, 0, 4)

        options_group.setLayout(options_layout)
        top_layout.addWidget(options_group)
        main_layout.addLayout(top_layout)

        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        progress_layout.addWidget(self.progress_bar)

        self.file_counter = QLabel("Files: 0")
        progress_layout.addWidget(self.file_counter)
        self.status_label = QLabel("Ready")
        progress_layout.addWidget(self.status_label)
        main_layout.addLayout(progress_layout)

        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        stats_group = QGroupBox("Summary Statistics")
        stats_layout = QGridLayout()
        self.total_label = QLabel("Total: 0")
        stats_layout.addWidget(self.total_label, 0, 0)
        self.ok_label = QLabel("OK: 0")
        self.ok_label.setStyleSheet("color: green;")
        stats_layout.addWidget(self.ok_label, 0, 1)
        self.warn_label = QLabel("Warning: 0")
        self.warn_label.setStyleSheet("color: orange;")
        stats_layout.addWidget(self.warn_label, 1, 0)
        self.err_label = QLabel("Error: 0")
        self.err_label.setStyleSheet("color: red;")
        stats_layout.addWidget(self.err_label, 1, 1)
        stats_group.setLayout(stats_layout)
        left_layout.addWidget(stats_group)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "OK", "Warning", "Error"])
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_combo)
        left_layout.addLayout(filter_layout)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(["File", "Ext", "Category", "Status", "Issues", "Duration"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSortingEnabled(True)
        left_layout.addWidget(self.results_table)

        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        export_group = QGroupBox("Export")
        export_layout = QHBoxLayout()
        self.export_excel_btn = QPushButton("Export Excel")
        self.export_excel_btn.clicked.connect(self._export_excel)
        self.export_excel_btn.setEnabled(False)
        export_layout.addWidget(self.export_excel_btn)

        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(self._export_csv)
        self.export_csv_btn.setEnabled(False)
        export_layout.addWidget(self.export_csv_btn)

        self.export_html_btn = QPushButton("Export HTML")
        self.export_html_btn.clicked.connect(self._export_html)
        self.export_html_btn.setEnabled(False)
        export_layout.addWidget(self.export_html_btn)

        self.ai_btn = QPushButton("Run AI Analysis")
        self.ai_btn.clicked.connect(self._run_ai)
        self.ai_btn.setEnabled(False)
        export_layout.addWidget(self.ai_btn)

        export_group.setLayout(export_layout)
        right_layout.addWidget(export_group)

        ai_group = QGroupBox("AI Analysis")
        ai_layout = QVBoxLayout()
        self.ai_text = QTextEdit()
        self.ai_text.setReadOnly(True)
        self.ai_text.setPlaceholderText("AI analysis results will appear here...")
        ai_layout.addWidget(self.ai_text)
        ai_group.setLayout(ai_layout)
        right_layout.addWidget(ai_group)

        splitter.addWidget(right_panel)
        splitter.setSizes([700, 500])
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.all_results = []

    def _browse_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory", self.dir_input.text())
        if directory:
            self.dir_input.setText(directory)

    def _start_check(self):
        scan_root = self.dir_input.text().strip()
        if not scan_root or not os.path.isdir(scan_root):
            QMessageBox.warning(self, "Error", f"Invalid directory: {scan_root}")
            return

        try:
            workers = int(self.workers_input.text())
        except ValueError:
            workers = WORKERS

        self.config = {
            "SCAN_ROOT": scan_root,
            "WORKERS": workers,
            "OUTPUT_DIR": OUTPUT_DIR,
            "RESUME_FILE": "./.scan_progress.json",
            "RESUME": False,
            "AI_MODEL": "qwen2.5:7b",
            "OLLAMA_URL": "http://192.168.99.210:11434",
            "RUN_AI": self.ai_check.isChecked(),
        }

        self.all_results = []
        self.results_table.setRowCount(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(0)
        self.file_counter.setText("Files: 0")
        self.status_label.setText("Working...")

        self.worker = ScanWorker(self.config)
        self.worker.progress_update.connect(self._on_progress)
        self.worker.file_scanned.connect(self._on_file_scanned)
        self.worker.check_complete.connect(self._on_check_complete)
        self.worker.status_update.connect(self.status_label.setText)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _stop_check(self):
        if self.worker:
            self.worker.cancel()
        self.status_label.setText("Cancelling...")

    def _on_progress(self, current, total):
        self.progress_bar.setMaximum(total if total > 0 else 100)
        self.progress_bar.setValue(current)
        self.file_counter.setText(f"Files: {current}")

    def _on_file_scanned(self, filepath):
        pass

    def _on_check_complete(self, checker):
        self.checker = checker
        self.all_results = checker.check_results
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Complete")

        total = len(self.all_results)
        ok_count = sum(1 for r in self.all_results if r["status"] == "ok")
        warn_count = sum(1 for r in self.all_results if r["status"] == "warning")
        err_count = sum(1 for r in self.all_results if r["status"] == "error")

        self.total_label.setText(f"Total: {total}")
        self.ok_label.setText(f"OK: {ok_count}")
        self.warn_label.setText(f"Warning: {warn_count}")
        self.err_label.setText(f"Error: {err_count}")

        self._populate_table(self.all_results)

        self.export_excel_btn.setEnabled(True)
        self.export_csv_btn.setEnabled(True)
        self.export_html_btn.setEnabled(True)
        self.ai_btn.setEnabled(True)

        self.status_bar.showMessage(f"Complete: {total} files checked ({ok_count} OK, {warn_count} warnings, {err_count} errors)")

    def _on_error(self, error_msg):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Error")
        QMessageBox.critical(self, "Error", f"An error occurred:\n{error_msg}")

    def _populate_table(self, results):
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(results))

        for row, r in enumerate(results):
            name_item = QTableWidgetItem(r["name"])
            name_item.setToolTip(r["path"])
            self.results_table.setItem(row, 0, name_item)
            self.results_table.setItem(row, 1, QTableWidgetItem(r["ext"]))
            self.results_table.setItem(row, 2, QTableWidgetItem(r["category"]))

            status_item = QTableWidgetItem(r["status"])
            if r["status"] == "ok":
                status_item.setForeground(QBrush(QColor("#28a745")))
            elif r["status"] == "warning":
                status_item.setForeground(QBrush(QColor("#ffc107")))
            else:
                status_item.setForeground(QBrush(QColor("#dc3545")))
            self.results_table.setItem(row, 3, status_item)

            issues_str = "; ".join(i["message"] for i in r.get("issues", [])[:3])
            self.results_table.setItem(row, 4, QTableWidgetItem(issues_str))
            dur_item = QTableWidgetItem(f"{r.get('duration_ms', 0):.0f}ms")
            self.results_table.setItem(row, 5, dur_item)

            if r["status"] == "error":
                for col in range(6):
                    self.results_table.item(row, col).setBackground(QColor("#fff5f5"))
            elif r["status"] == "warning":
                for col in range(6):
                    self.results_table.item(row, col).setBackground(QColor("#fffef5"))

        self.results_table.setSortingEnabled(True)

    def _apply_filter(self, filter_text):
        if not self.all_results:
            return
        if filter_text == "All":
            filtered = self.all_results
        else:
            filtered = [r for r in self.all_results if r["status"] == filter_text.lower()]
        self._populate_table(filtered)

    def _export_excel(self):
        if not self.all_results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel", "health_report.xlsx", "Excel (*.xlsx)")
        if path:
            from reporter import export_excel
            export_excel(self.all_results, path)
            self.status_bar.showMessage(f"Excel report saved: {path}")

    def _export_csv(self):
        if not self.all_results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "health_report.csv", "CSV (*.csv)")
        if path:
            from reporter import export_csv
            export_csv(self.all_results, path)
            self.status_bar.showMessage(f"CSV report saved: {path}")

    def _export_html(self):
        if not self.all_results:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save HTML", "health_report.html", "HTML (*.html)")
        if path:
            from ai_analyzer import generate_report_html
            ai_text = self.ai_text.toPlainText()
            html = generate_report_html(self.all_results, ai_text)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.status_bar.showMessage(f"HTML report saved: {path}")

    def _run_ai(self):
        if not self.checker or not self.all_results:
            return
        self.ai_btn.setEnabled(False)
        self.ai_text.setText("Running AI analysis...")
        self.status_bar.showMessage("AI analysis in progress...")

        def _do_ai():
            try:
                analysis = self.checker.analyze()
                self.ai_text.setText(analysis)
                self.status_bar.showMessage("AI analysis complete")
            except Exception as e:
                self.ai_text.setText(f"AI analysis failed:\n{str(e)}")
                self.status_bar.showMessage("AI analysis failed")
            finally:
                self.ai_btn.setEnabled(True)

        thread = threading.Thread(target=_do_ai, daemon=True)
        thread.start()


def launch_gui():
    if not PYSIDE_AVAILABLE:
        print("PySide6 is not installed. GUI is unavailable.")
        print("Install with: pip install PySide6")
        print("Falling back to CLI mode.")
        print()
        print("To use CLI mode, run: python -m doc_health_check.cli /path/to/scan")
        return False

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f5f7fa"))
    palette.setColor(QPalette.WindowText, QColor("#333"))
    app.setPalette(palette)

    window = HealthCheckGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
