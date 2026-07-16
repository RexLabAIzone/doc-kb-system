import os
import json
import hashlib
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque

from tqdm import tqdm

from file_types import get_category
from config import setup_logging

logger = setup_logging("scanner")
_scan_cancel = threading.Event()


def cancel_scan():
    _scan_cancel.set()


def reset_cancel():
    _scan_cancel.clear()


def is_cancelled():
    return _scan_cancel.is_set()


def scan_directory(root_path, workers=8, resume_file=None):
    reset_cancel()
    all_files = []
    if resume_file and os.path.exists(resume_file):
        try:
            with open(resume_file) as f:
                seen_hashes = set(json.load(f))
            logger.info("Loaded %d previously scanned file hashes", len(seen_hashes))
        except Exception as e:
            logger.warning("Failed to load resume file: %s", e)
            seen_hashes = set()
    else:
        seen_hashes = set()
    processed_hashes = set(seen_hashes)
    root_path = os.path.abspath(root_path)
    if not os.path.exists(root_path):
        return all_files
    save_interval = 500
    file_queue = deque([root_path])
    with tqdm(desc="Scanning files", unit="files", leave=True) as pbar:
        while file_queue and not is_cancelled():
            cur = file_queue.popleft()
            try:
                entries = list(os.scandir(cur))
            except (PermissionError, OSError):
                continue
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False):
                        file_queue.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        fp = e.path
                        fname = e.name
                        ext = os.path.splitext(fname)[1].lower()
                        size = e.stat().st_size
                        mtime = e.stat().st_mtime
                        h = hashlib.md5(fp.encode()).hexdigest()
                        if h in seen_hashes:
                            continue
                        all_files.append(
                            {
                                "path": fp,
                                "name": fname,
                                "ext": ext,
                                "size": size,
                                "category": get_category(ext),
                                "mtime": mtime,
                            }
                        )
                        processed_hashes.add(h)
                        pbar.update(1)
                        if len(processed_hashes) % save_interval == 0 and resume_file:
                            with open(resume_file, "w") as f:
                                json.dump(list(processed_hashes), f)
                except OSError:
                    continue
        if resume_file:
            with open(resume_file, "w") as f:
                json.dump(list(processed_hashes), f)
    logger.info("Scan complete: %d files", len(all_files))
    return all_files


def resume_scan(root_path, resume_file=None):
    if resume_file and os.path.exists(resume_file):
        with open(resume_file) as f:
            seen = set(json.load(f))
        total = len(seen)
    else:
        seen = set()
        total = 0
    new_files = []
    root_path = os.path.abspath(root_path)
    if not os.path.exists(root_path):
        return new_files, total
    q = deque([root_path])
    with tqdm(desc="Resume scanning", unit="files", leave=True) as pbar:
        while q:
            cur = q.popleft()
            try:
                entries = list(os.scandir(cur))
            except (PermissionError, OSError):
                continue
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False):
                        q.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        h = hashlib.md5(e.path.encode()).hexdigest()
                        if h not in seen:
                            ext = os.path.splitext(e.name)[1].lower()
                            new_files.append(
                                {
                                    "path": e.path,
                                    "name": e.name,
                                    "ext": ext,
                                    "size": e.stat().st_size,
                                    "category": get_category(ext),
                                    "mtime": e.stat().st_mtime,
                                }
                            )
                        pbar.update(1)
                except OSError:
                    continue
    return new_files, total
