import os

FILE_CATEGORIES = {
    "text": {".txt", ".md", ".csv", ".html", ".htm", ".xml", ".json", ".yaml", ".yml", ".ini", ".conf", ".log", ".bat", ".sh", ".ps1", ".py", ".js", ".ts", ".css", ".sql", ".r", ".lua", ".php", ".rb", ".pl", ".swift", ".kt", ".scala", ".tex", ".rst", ".org"},
    "office_doc": {".doc", ".docx", ".odt", ".rtf"},
    "office_spreadsheet": {".xls", ".xlsx", ".ods"},
    "office_presentation": {".ppt", ".pptx", ".odp"},
    "pdf": {".pdf"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".ico", ".svg", ".eps", ".raw", ".cr2", ".nef", ".arw"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".ape", ".aiff"},
    "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".mpeg", ".mpg", ".m4v", ".3gp", ".ts", ".mts", ".m2ts"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst"},
    "ebook": {".mobi", ".epub", ".azw3", ".umd", ".cbr", ".cbz", ".djvu"},
    "binary": {".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".iso", ".img", ".vhd"},
    "font": {".ttf", ".otf", ".woff", ".woff2", ".eot"},
}

EXTENSION_MAP = {}
for category, extensions in FILE_CATEGORIES.items():
    for ext in extensions:
        EXTENSION_MAP[ext.lower()] = category


def get_category(ext):
    if not ext:
        return "unknown"
    ext = ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    return EXTENSION_MAP.get(ext, "unknown")


def is_supported(ext):
    return get_category(ext) != "unknown"


def get_extensions_for_category(category):
    return FILE_CATEGORIES.get(category, set())
