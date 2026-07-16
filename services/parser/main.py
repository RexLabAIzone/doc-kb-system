import os, time, hashlib, psycopg2, sys, subprocess, tempfile, json
from pathlib import Path

def log(msg):
    print(msg, flush=True)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'postgres'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'dbname': os.getenv('DB_NAME', 'docdb'),
    'user': os.getenv('DB_USER', 'docadmin'),
    'password': os.getenv('DB_PASS', 'changeit'),
}
DOC_ROOT = Path(os.getenv('DOC_ROOT', '/data/originals'))
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '3600'))
SUPPORTED_EXT = {'.txt', '.pdf', '.epub', '.mobi', '.azw3', '.doc', '.docx', '.md', '.html', '.htm', '.csv', '.xls', '.xlsx', '.ppt', '.pptx', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'}
TEXT_EXT = {'.txt', '.md', '.csv', '.html', '.htm'}

def get_db():
    for i in range(30):
        try:
            return psycopg2.connect(**DB_CONFIG)
        except psycopg2.OperationalError:
            if i == 0:
                log(f"DB not ready, retrying... ({i+1}/30)")
            time.sleep(2)
    raise

def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def extract_text(path, ext):
    try:
        if ext in TEXT_EXT:
            for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'big5', 'utf-16']:
                try:
                    with open(path, 'r', encoding=enc, errors='strict') as f:
                        data = f.read(200000)
                    return data
                except:
                    continue
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read(200000)
        elif ext == '.pdf':
            return extract_pdf(path)
        elif ext == '.docx':
            return extract_docx(path)
        elif ext in {'.doc', '.xls', '.xlsx', '.ppt', '.pptx'}:
            return extract_libreoffice(path)
        elif ext in {'.png', '.jpg', '.jpeg', '.tiff', '.bmp'}:
            return extract_ocr(path)
        elif ext == '.epub':
            return extract_libreoffice(path)
        else:
            return extract_libreoffice(path)
    except Exception as e:
        log(f"Extract error {path}: {e}")
        return ''

def extract_pdf(path):
    try:
        import fitz
        doc = fitz.open(path)
        text = ''
        for page in doc:
            text += page.get_text() or ''
        doc.close()
        if len(text.strip()) < 50:
            log(f"PDF has little text, trying OCR: {path}")
            text = ocr_images_from_pdf(path)
        return text[:200000]
    except Exception as e:
        log(f"PyMuPDF error: {e}")
        return ''

def ocr_images_from_pdf(path):
    try:
        import fitz
        import pytesseract
        doc = fitz.open(path)
        text = ''
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=200)
            img_path = f'/tmp/ocr_page_{i}.png'
            pix.save(img_path)
            try:
                text += pytesseract.image_to_string(img_path, lang='chi_sim+eng') + '\n'
            except:
                pass
            os.unlink(img_path)
        doc.close()
        return text[:200000]
    except:
        return ''

def extract_docx(path):
    try:
        import docx
        doc = docx.Document(path)
        return '\n'.join(p.text for p in doc.paragraphs)[:200000]
    except:
        return ''

def extract_libreoffice(path):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ['soffice', '--headless', '--convert-to', 'txt:Text', '--outdir', tmp, str(path)],
                capture_output=True, text=True, timeout=60,
                env={'HOME': '/tmp', 'PATH': '/usr/bin:/usr/local/bin'}
            )
            txt_files = list(Path(tmp).glob('*.txt'))
            if txt_files:
                return txt_files[0].read_text(encoding='utf-8', errors='replace')[:200000]
    except subprocess.TimeoutExpired:
        log(f"LibreOffice timeout: {path}")
    except Exception as e:
        log(f"LibreOffice error: {e}")
    return ''

def extract_ocr(path):
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        return text[:200000]
    except:
        return ''

def scan_files():
    if not DOC_ROOT.exists():
        return []
    files = []
    dirs = [DOC_ROOT]
    seen = set()
    while dirs and len(files) < 5000:
        d = dirs.pop(0)
        try:
            entries = list(d.iterdir())
        except PermissionError:
            continue
        for f in entries:
            if f.name.startswith('.'):
                continue
            if f.is_dir():
                if len(dirs) < 200:
                    dirs.append(f)
                continue
            if f.suffix.lower() not in SUPPORTED_EXT:
                continue
            try:
                rel = str(f.relative_to(DOC_ROOT))
            except ValueError:
                continue
            files.append((rel, f))
    return files

def process_files():
    conn = get_db()
    cur = conn.cursor()
    while True:
        log(f"Scanning {DOC_ROOT}...")
        files = scan_files()
        log(f"Found {len(files)} files")
        for rel, fpath in files:
            try:
                cur.execute("SELECT id, is_processed, file_hash FROM documents WHERE file_path=%s", (str(fpath),))
                row = cur.fetchone()
                fhash = file_hash(fpath)
                if row:
                    if not row[1] or row[2] != fhash:
                        pass
                    else:
                        continue
                name = fpath.name
                ext = fpath.suffix.lower()
                size = fpath.stat().st_size
                content = extract_text(fpath, ext)
                char_count = len(content) if content else 0
                if row:
                    cur.execute("""
                        UPDATE documents SET file_hash=%s, file_size=%s, content_text=%s,
                            char_count=%s, is_processed=TRUE, updated_at=NOW()
                        WHERE id=%s
                    """, (fhash, size, content, char_count, row[0]))
                else:
                    cur.execute("""
                        INSERT INTO documents (file_path, file_name, file_ext, file_size,
                            file_hash, content_text, char_count, is_processed)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)
                    """, (str(fpath), name, ext, size, fhash, content, char_count))
                conn.commit()
                log(f"Parsed: {name} ({char_count} chars)")
            except Exception as e:
                log(f"Error processing {fpath}: {e}")
                conn.rollback()
        log(f"Sleeping {SCAN_INTERVAL}s...")
        time.sleep(SCAN_INTERVAL)

if __name__ == '__main__':
    log("Doc Parser starting...")
    process_files()
