import re
import shutil
import tempfile
import os

def extract_pdf_text(path: str) -> str:
    try:
        import fitz
        doc = fitz.open(path)
        num_pages = len(doc)
        parts = []
        for page in doc:
            text = page.get_text()
            if text:
                parts.append(text)
        result = '\n'.join(parts)
        doc.close()
        if len(result.strip()) >= 50 or num_pages == 0:
            return result
        return _ocr_pdf(path)
    except Exception as e:
        return "[PDF解析失败: {}]".format(e)


def _extract_mobi_result(result) -> str:
    if not (isinstance(result, tuple) and len(result) >= 2):
        return ""
    path = result[1]
    if not os.path.exists(path):
        return ""
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1].lower()
        if ext == '.epub':
            import epub2txt
            return epub2txt.epub2txt(path)
        if ext == '.html':
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
            text = re.sub(r"<[^>]+>", "", html)
            text = text.replace("&nbsp;", " ").replace("&amp;", "&")
            return text
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if os.path.isdir(path):
        parts = []
        for root, dirs, files in os.walk(path):
            for fn in sorted(files):
                if fn.endswith('.html') or fn.endswith('.xhtml'):
                    fp = os.path.join(root, fn)
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        html = f.read()
                    text = re.sub(r"<[^>]+>", "", html)
                    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
                    if text.strip():
                        parts.append(text.strip())
        if parts:
            return "\n\n".join(parts)
    return ""

def extract_mobi_text(path: str) -> str:
    try:
        import mobi
        tmp = tempfile.mkdtemp()
        dst = os.path.join(tmp, "book.mobi")
        shutil.copy2(path, dst)
        result = mobi.extract(dst)
        text = _extract_mobi_result(result)
        if text:
            return text
        return "[MOBI解析失败: 未知格式]"
    except Exception as e:
        return "[MOBI解析失败: {}]".format(e)
    finally:
        try:
            shutil.rmtree(tmp)
        except:
            pass

def extract_epub_text(path: str) -> str:
    try:
        import epub2txt
        tmp = tempfile.mkdtemp()
        dst = os.path.join(tmp, "book.epub")
        shutil.copy2(path, dst)
        text = epub2txt.epub2txt(dst)
        return text
    except Exception as e:
        return "[EPUB解析失败: {}]".format(e)
    finally:
        try:
            shutil.rmtree(tmp)
        except:
            pass

def extract_binary_ebook(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        return extract_pdf_text(path)
    elif ext == '.mobi' or ext == '.azw3':
        return extract_mobi_text(path)
    elif ext == '.epub':
        return extract_epub_text(path)
    elif ext == '.docx':
        try:
            from docx import Document
            doc = Document(path)
            return '\n'.join(p.text for p in doc.paragraphs)
        except Exception as e:
            return "[DOCX解析失败: {}]".format(e)
    elif ext == '.doc':
        try:
            import subprocess
            r = subprocess.run(['antiword', path], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
            r2 = subprocess.run(['antiword', '-m', 'UTF-8', path], capture_output=True, text=True, timeout=10)
            if r2.returncode == 0 and r2.stdout.strip():
                return r2.stdout
            return "[DOC解析失败: antiword无法处理此文件]"
        except Exception as e:
            return "[DOC解析失败: {}]".format(e)
    elif ext == '.rtf':
        try:
            from striprtf.striprtf import rtf_to_text
            with open(path, 'rb') as f:
                raw = f.read()
            try:
                rtf_content = raw.decode('utf-8')
            except:
                import chardet
                enc = chardet.detect(raw).get('encoding', 'utf-8') or 'utf-8'
                rtf_content = raw.decode(enc, errors='replace')
            text = rtf_to_text(rtf_content)
            return text if text.strip() else "[RTF解析失败: 提取结果为空]"
        except Exception as e:  
            return "[RTF解析失败: {}]".format(e)
    return "[不支持的格式: {}]".format(ext)


if __name__ == '__main__':
    import sys
    text = extract_binary_ebook(sys.argv[1])
    print("Extracted {} chars".format(len(text)))
    print(text[:3000])
