import os
import logging

SCAN_ROOT = "/data/originals"
OUTPUT_DIR = "./reports"
WORKERS = 8
RESUME_FILE = "./.scan_progress.json"
AI_MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://192.168.99.210:11434"
MAX_FILE_SIZE_MB = 500
CHECK_ENCODING = True
CHECK_OPENABLE = True
CHECK_CORRUPTION = True
SUSPICIOUS_CHARS_THRESHOLD = 0.15

LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

def setup_logging(name="doc-health-check", level=None):
    logger = logging.getLogger(name)
    if level is None:
        level = LOG_LEVEL
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    return logger

def get_config_from_env():
    import os as _os
    cfg = {}
    for key in ["SCAN_ROOT", "OUTPUT_DIR", "WORKERS", "RESUME_FILE",
                 "AI_MODEL", "OLLAMA_URL", "MAX_FILE_SIZE_MB",
                 "CHECK_ENCODING", "CHECK_OPENABLE", "CHECK_CORRUPTION",
                 "SUSPICIOUS_CHARS_THRESHOLD"]:
        env_val = _os.environ.get(f"DHC_{key}")
        if env_val is not None:
            cfg[key] = env_val
    return cfg
