import os, psycopg2, json, hashlib, secrets, re, threading
import httpx
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel
from fastapi import FastAPI, Query, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from contextlib import asynccontextmanager
from elasticsearch import Elasticsearch
from concurrent.futures import ThreadPoolExecutor, as_completed
from jose import jwt as jose_jwt
from collections import Counter

DB_URL = os.getenv('DB_URL', 'postgresql://docadmin:changeit@postgres:5432/docdb')
ES_URL = os.getenv('ES_URL', 'http://elasticsearch:9200')
JWT_SECRET = os.getenv('SECRET_KEY', 'doc-system-secret-key-change-me')
JWT_ALGO = 'HS256'

def get_db():
    return psycopg2.connect(DB_URL)

def get_es():
    return Elasticsearch(ES_URL)

ES_INDEX = 'documents'
ES_MAPPING = {
    "settings": {
        "analysis": {
            "analyzer": {
                "ik_smart_analyzer": {"type": "custom", "tokenizer": "ik_smart"},
                "ik_max_word_analyzer": {"type": "custom", "tokenizer": "ik_max_word"}
            }
        },
        "index": {"number_of_shards": 1, "number_of_replicas": 0}
    },
    "mappings": {
        "properties": {
            "id": {"type": "long"},
            "file_name": {"type": "text", "analyzer": "ik_max_word", "fields": {"keyword": {"type": "keyword"}}},
            "file_ext": {"type": "keyword"},
            "file_path": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "ik_max_word"},
            "category": {"type": "keyword"},
            "author": {"type": "text", "analyzer": "ik_smart"},
            "summary": {"type": "text", "analyzer": "ik_smart"},
            "char_count": {"type": "integer"},
            "created_at": {"type": "date"}
        }
    }
}

def _ensure_es_index():
    try:
        es = get_es()
        if not es.indices.exists(index=ES_INDEX):
            es.indices.create(index=ES_INDEX, body=ES_MAPPING)
            print("  ES index created")
        return es
    except Exception as e:
        print(f"  ES init warning: {e}")
        return None

def _index_doc_to_es(doc_id, file_name, content_text, file_ext, file_path, category, author, summary, char_count, created_at):
    try:
        es = get_es()
        doc = {
            "id": doc_id,
            "file_name": file_name,
            "file_ext": file_ext,
            "file_path": file_path,
            "content": (content_text or '')[:50000],
            "category": category or '',
            "author": author or '',
            "summary": summary or '',
            "char_count": char_count or 0,
            "created_at": created_at.isoformat() if created_at else datetime.now().isoformat(),
        }
        es.index(index=ES_INDEX, id=doc_id, body=doc, refresh='wait_for')
        return True
    except Exception as e:
        print(f"  ES index error doc {doc_id}: {e}")
        return False

def _bulk_index_all_docs():
    _ensure_es_index()
    conn = get_db()
    cur = conn.cursor('es_cursor')
    cur.itersize = 200
    cur.execute("""
        SELECT d.id, d.file_name, d.content_text, d.file_ext, d.file_path,
               COALESCE(c.category,'') as category,
               COALESCE(c.key_points->>'author','') as author,
               COALESCE(c.summary,'') as summary,
               d.char_count, d.created_at
        FROM documents d
        LEFT JOIN doc_categories c ON c.doc_id = d.id
        WHERE d.content_text IS NOT NULL AND d.content_text != ''
        ORDER BY d.id
    """)
    es = get_es()
    from elasticsearch.helpers import streaming_bulk
    def _gen():
        for r in cur:
            yield {
                "_index": ES_INDEX, "_id": r[0],
                "_source": {
                    "id": r[0], "file_name": r[1], "file_ext": r[3], "file_path": r[4],
                    "content": (r[2] or '')[:50000], "category": r[5] or '',
                    "author": r[6] or '', "summary": r[7] or '',
                    "char_count": r[8] or 0,
                    "created_at": r[9].isoformat() if r[9] else datetime.now().isoformat(),
                }
            }
    try:
        success = 0
        for ok, info in streaming_bulk(es, _gen(), chunk_size=100):
            if ok:
                success += 1
        print(f"  ES bulk indexed {success} docs")
    except Exception as e:
        print(f"  ES bulk index error: {e}")
    finally:
        cur.close(); conn.close()

def _index_doc_to_es_by_id(doc_id):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT d.id, d.file_name, d.content_text, d.file_ext, d.file_path,
                   COALESCE(c.category,'') as category,
                   COALESCE(c.key_points->>'author','') as author,
                   COALESCE(c.summary,'') as summary,
                   d.char_count, d.created_at
            FROM documents d
            LEFT JOIN doc_categories c ON c.doc_id = d.id
            WHERE d.id = %s
        """, (doc_id,))
        r = cur.fetchone()
        cur.close(); conn.close()
        if r:
            _index_doc_to_es(*r)
    except Exception as e:
        print(f"  ES index_by_id error doc {doc_id}: {e}")

def _index_doc_to_es_single(rows):
    for r in rows:
        try:
            _index_doc_to_es(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9])
        except:
            pass

def ngram_similarity(text_a: str, text_b: str, n: int = 8) -> float:
    if not text_a or not text_b:
        return 0.0
    a_clean = re.sub(r'\s+', '', text_a)[:5000]
    b_clean = re.sub(r'\s+', '', text_b)[:5000]
    if not a_clean or not b_clean:
        return 0.0
    shingles_a = set(a_clean[i:i+n] for i in range(len(a_clean)-n+1))
    shingles_b = set(b_clean[i:i+n] for i in range(len(b_clean)-n+1))
    if not shingles_a or not shingles_b:
        return 0.0
    intersection = len(shingles_a & shingles_b)
    union = len(shingles_a | shingles_b)
    return intersection / union if union else 0.0

CACHE_ROOT = Path(os.getenv('OUTPUT_ROOT', '/data/output'))

CREATE_OPLOG_TABLE = """
CREATE TABLE IF NOT EXISTS operation_log (
    id BIGSERIAL PRIMARY KEY,
    user_name TEXT DEFAULT 'system',
    action TEXT NOT NULL,
    target_type TEXT,
    target_id BIGINT,
    details JSONB,
    before_state JSONB,
    after_state JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
)
"""

def log_operation(user, action, target_type=None, target_id=None, details=None, before=None, after=None):
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO operation_log (user_name, action, target_type, target_id, details, before_state, after_state)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
        """, (user, action, target_type, target_id,
              json.dumps(details, ensure_ascii=False) if details else None,
              json.dumps(before, ensure_ascii=False) if before else None,
              json.dumps(after, ensure_ascii=False) if after else None))
        conn.commit(); cur.close(); conn.close()
    except:
        pass

def _run_ddl_with_retry(cur):
    import time
    ddl_statements = [
        ("CREATE_SOURCES_TABLE", CREATE_SOURCES_TABLE),
        ("CREATE_OPLOG_TABLE", CREATE_OPLOG_TABLE),
        ("documents.content_path", "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_path TEXT"),
        ("documents.is_cached", "ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_cached BOOLEAN DEFAULT FALSE"),
        ("vector extension", "CREATE EXTENSION IF NOT EXISTS vector"),
        ("doc_embeddings", """
            CREATE TABLE IF NOT EXISTS doc_embeddings (
                doc_id BIGINT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                embedding vector(1024),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """),
        ("idx_doc_embeddings", "CREATE INDEX IF NOT EXISTS idx_doc_embeddings_doc_id ON doc_embeddings(doc_id)"),
        ("doc_relations", """
            CREATE TABLE IF NOT EXISTS doc_relations (
                id BIGSERIAL PRIMARY KEY,
                doc_id_a BIGINT NOT NULL REFERENCES documents(id),
                doc_id_b BIGINT NOT NULL REFERENCES documents(id),
                relation_type TEXT NOT NULL DEFAULT 'similar',
                similarity_score REAL DEFAULT 0,
                merge_status TEXT DEFAULT 'pending',
                merged_doc_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """),
        ("users", """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """),
        ("organize_rules", """
            CREATE TABLE IF NOT EXISTS organize_rules (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                pattern TEXT NOT NULL,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """),
    ]
    for name, sql in ddl_statements:
        for i in range(3):
            try:
                cur.execute("SET lock_timeout = '5s'")
                cur.execute(sql)
                break
            except Exception as e:
                if i < 2:
                    cur.connection.rollback()
                    time.sleep(1)
                else:
                    print(f"  DDL {name} failed: {e}")
    cur.execute("SELECT COUNT(*) FROM organize_rules")
    if cur.fetchone()[0] == 0:
        defaults = [
            ('按分类/年份', '{category}/{year}/{file_name}', True),
            ('按分类/作者', '{category}/{author}/{file_name}', True),
            ('按体裁/年份', '{genre}/{year}/{file_name}', True),
            ('按作者', '{author}/{file_name}', True),
            ('按分类', '{category}/{file_name}', True),
        ]
        for name, pattern, is_def in defaults:
            cur.execute("INSERT INTO organize_rules (name, pattern, is_default) VALUES (%s,%s,%s)", (name, pattern, is_def))
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        admin_hash = hash_password('admin123')
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,'admin')", ('admin', admin_hash))

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        conn = get_db(); cur = conn.cursor()
        _run_ddl_with_retry(cur)
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f"  lifespan startup warning: {e}")
    for d in ['cache', 'organized', 'merged']:
        (CACHE_ROOT / d).mkdir(parents=True, exist_ok=True)
    import threading
    t = threading.Thread(target=_continuous_scan_loop, args=(300,), daemon=True)
    t.start()
    t2 = threading.Thread(target=_batch_pipeline_worker, daemon=True)
    t2.start()
    # t3 disabled: _bulk_index_all_docs can be triggered via API
    yield

app = FastAPI(title="Document Knowledge Base API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return RedirectResponse(url="http://192.168.99.210:80")

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/api/stats")
def stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM documents")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM doc_categories")
    classified = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM documents WHERE content_text != '' AND content_text IS NOT NULL")
    parsed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM doc_embeddings")
    embedded = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM doc_relations")
    relations = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {"total": total, "classified": classified, "parsed": parsed,
            "embedded": embedded, "relations": relations}

@app.get("/api/documents")
def list_docs(q: str = '', limit: int = 50, offset: int = 0, type: str = 'fulltext'):
    conn = get_db()
    cur = conn.cursor()
    total = 0
    if q:
        if type == 'semantic':
            q_emb = get_embedding(q)
            if q_emb:
                sql = """
                    SELECT d.id, d.file_name, d.file_ext, d.file_size, d.char_count,
                           c.category, c.tags, c.summary, d.created_at,
                           1 - (e.embedding <=> %s::vector) AS similarity,
                           LEFT(d.content_text, 200) AS snippet
                    FROM documents d
                    LEFT JOIN doc_categories c ON c.doc_id = d.id
                    JOIN doc_embeddings e ON e.doc_id = d.id
                    ORDER BY e.embedding <=> %s::vector
                    LIMIT %s OFFSET %s
                """
                cur.execute(sql, (q_emb, q_emb, limit, offset))
            else:
                sql = """
                    SELECT d.id, d.file_name, d.file_ext, d.file_size, d.char_count,
                           c.category, c.tags, c.summary, d.created_at, 0 AS similarity, '' AS snippet
                    FROM documents d
                    LEFT JOIN doc_categories c ON c.doc_id = d.id
                    WHERE 1=0
                """
                cur.execute(sql)
        else:
            try:
                es = get_es()
                es_result = es.search(index=ES_INDEX, body={
                    "query": {"multi_match": {"query": q, "fields": ["file_name^3", "content", "summary^2", "author"]}},
                    "highlight": {"fields": {"content": {"fragment_size": 200, "number_of_fragments": 1}, "file_name": {}}},
                    "from": offset, "size": limit,
                    "track_total_hits": True,
                })
                total = es_result['hits']['total']['value']
                ids = [int(h['_id']) for h in es_result['hits']['hits']]
                highlights = {int(h['_id']): h.get('highlight', {}) for h in es_result['hits']['hits']}
                if ids:
                    placeholders = ','.join(['%s'] * len(ids))
                    id_order = ','.join(str(x) for x in ids)
                    sql = f"""
                        SELECT d.id, d.file_name, d.file_ext, d.file_size, d.char_count,
                               c.category, c.tags, c.summary, d.created_at, NULL::float AS similarity,
                               LEFT(d.content_text, 200) AS snippet
                        FROM documents d
                        LEFT JOIN doc_categories c ON c.doc_id = d.id
                        WHERE d.id IN ({placeholders})
                        ORDER BY array_position(ARRAY[{id_order}]::bigint[], d.id)
                    """
                    cur.execute(sql, ids)
                    rows = cur.fetchall()
                    items = []
                    for r in rows:
                        hl = highlights.get(r[0], {})
                        snippet = None
                        if 'content' in hl:
                            snippet = hl['content'][0]
                        elif 'file_name' in hl:
                            snippet = hl['file_name'][0]
                        items.append({
                            "id": r[0], "file_name": r[1], "file_ext": r[2], "file_size": r[3],
                            "char_count": r[4], "category": r[5], "tags": r[6] or [],
                            "summary": r[7], "created_at": str(r[8]) if r[8] else None,
                            "similarity": None,
                            "snippet": snippet or (r[10] if len(r) > 10 else None),
                        })
                    cur.close(); conn.close()
                    return {"items": items, "total": total}
            except:
                pass
            cur.execute("SELECT COUNT(*) FROM documents WHERE file_name ILIKE %s", (f'%{q}%',))
            total = cur.fetchone()[0]
            sql = """
                SELECT d.id, d.file_name, d.file_ext, d.file_size, d.char_count,
                       c.category, c.tags, c.summary, d.created_at, NULL::float AS similarity,
                       LEFT(d.content_text, 200) AS snippet
                FROM documents d
                LEFT JOIN doc_categories c ON c.doc_id = d.id
                WHERE d.file_name ILIKE %s
                ORDER BY d.char_count DESC LIMIT %s OFFSET %s
            """
            cur.execute(sql, (f'%{q}%', limit, offset))
    else:
        sql = """
            SELECT d.id, d.file_name, d.file_ext, d.file_size, d.char_count,
                   c.category, c.tags, c.summary, d.created_at, NULL::float AS similarity,
                   NULL AS snippet
            FROM documents d
            LEFT JOIN doc_categories c ON c.doc_id = d.id
            ORDER BY d.created_at DESC LIMIT %s OFFSET %s
        """
        cur.execute(sql, (limit, offset))
    rows = cur.fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r[0], "file_name": r[1], "file_ext": r[2], "file_size": r[3],
            "char_count": r[4], "category": r[5], "tags": r[6] or [],
            "summary": r[7], "created_at": str(r[8]) if r[8] else None,
            "similarity": round(r[9], 4) if len(r) > 9 and r[9] else None,
            "snippet": r[10] if len(r) > 10 else None,
        })
    cur.close()
    conn.close()
    return {"items": items, "total": total or len(items)}

@app.get("/api/categories")
def get_categories():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.category, COUNT(*) as cnt
        FROM doc_categories c GROUP BY c.category ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"category": r[0], "count": r[1]} for r in rows]

@app.get("/api/documents/relations")
def list_relations(limit: int = 50, offset: int = 0, type: str = 'similar'):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.id, r.doc_id_a, r.doc_id_b, r.similarity_score, r.merge_status,
               r.merged_doc_id, r.created_at,
               da.file_name as name_a, db.file_name as name_b
        FROM doc_relations r
        LEFT JOIN documents da ON da.id = r.doc_id_a
        LEFT JOIN documents db ON db.id = r.doc_id_b
        WHERE r.relation_type = %s AND r.merge_status = 'pending'
        ORDER BY r.similarity_score DESC LIMIT %s OFFSET %s
    """, (type, limit, offset))
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM doc_relations WHERE relation_type=%s AND merge_status='pending'", (type,))
    total = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {
        "total": total,
        "items": [{
            "id": r[0], "doc_id_a": r[1], "doc_id_b": r[2],
            "similarity_score": r[3], "merge_status": r[4],
            "merged_doc_id": r[5], "created_at": str(r[6]) if r[6] else None,
            "doc_a_name": r[7], "doc_b_name": r[8],
        } for r in rows]
    }

@app.get("/api/documents/by-category/{category}")
def docs_by_category(category: str, limit: int = 50):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.file_name, d.char_count, c.summary
        FROM documents d
        JOIN doc_categories c ON c.doc_id = d.id
        WHERE c.category = %s ORDER BY d.char_count DESC LIMIT %s
    """, (category, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "file_name": r[1], "char_count": r[2], "summary": r[3]} for r in rows]

ORIGINALS_ROOT = Path(os.getenv('DOCUMENTS_ROOT', '/data/originals'))

def _find_file(file_path: str, file_name: str) -> Path:
    fp = Path(file_path)
    if fp.is_absolute() and fp.exists():
        return fp
    if file_path:
        rooted = ORIGINALS_ROOT / file_path
        if rooted.exists():
            return rooted
    if file_name and ORIGINALS_ROOT.exists():
        for d in ORIGINALS_ROOT.iterdir():
            if d.is_dir():
                candidate = d / file_name
                if candidate.exists():
                    return candidate
                for sub in d.iterdir():
                    if sub.is_dir():
                        candidate2 = sub / file_name
                        if candidate2.exists():
                            return candidate2
        candidate = ORIGINALS_ROOT / file_name
        if candidate.exists():
            return candidate
    return None

def _repair_garbled(text: str) -> str:
    noop = lambda t: t
    if not text:
        return text
    ff = chr(65533)
    garbage_chars = sum(1 for c in text[:500] if c == ff)
    if garbage_chars == 0:
        return text
    try:
        repaired = text.encode('latin-1', errors='replace').decode('gbk', errors='replace')
        if repaired != text and repaired.count(ff) < text.count(ff):
            return repaired
    except:
        pass
    return text

def read_content(doc_id: int, content_text: str, content_path: str = None, file_path: str = None, file_name: str = ''):
    ext = Path(file_name or '').suffix.lower()
    # For binary ebook formats, always extract fresh from file (DB content_text is raw binary)
    if ext in BINARY_EBOOK_EXTS:
        fp = _find_file(file_path or '', file_name or '')
        if fp:
            ebook_text = extract_ebook(str(fp))
            if ebook_text:
                return ebook_text
        if content_path:
            cp = Path(content_path)
            if cp.exists():
                ebook_text = extract_ebook(str(cp))
                if ebook_text:
                    return ebook_text
        return '[无法提取文本内容]'
    if content_text:
        repaired = _repair_garbled(content_text)
        if repaired != content_text:
            return repaired
        return content_text
    if content_path:
        cp = Path(content_path)
        if cp.exists():
            enc = detect_encoding(str(cp))
            try:
                return cp.read_text(encoding=enc, errors='replace')
            except:
                pass
    fp = _find_file(file_path or '', file_name or '')
    if fp:
        enc = detect_encoding(str(fp))
        try:
            return fp.read_text(encoding=enc, errors='replace')
        except:
            pass
    if content_path is None:
        for f in (CACHE_ROOT / 'cache').glob(f"{doc_id}_*"):
            if f.exists():
                enc = detect_encoding(str(f))
                try:
                    return f.read_text(encoding=enc, errors='replace')
                except:
                    pass
    return ''

MAX_READ_CHARS = 200_000

@app.get("/api/documents/by-metadata")
def docs_by_metadata(author: str = '', year: int = 0, genre: str = '', limit: int = 50, offset: int = 0):
    conn = get_db(); cur = conn.cursor()
    conditions = []
    params = []
    if author:
        conditions.append("c.key_points->>'author' = %s"); params.append(author)
    if year:
        conditions.append("(c.key_points->>'publish_year')::int = %s"); params.append(str(year))
    if genre:
        conditions.append("c.key_points->>'genre' = %s"); params.append(genre)
    where = " AND ".join(conditions) if conditions else "TRUE"
    sql = f"""
        SELECT d.id, d.file_name, d.file_ext, d.char_count,
               c.category, c.tags, c.summary, c.key_points
        FROM documents d
        JOIN doc_categories c ON c.doc_id = d.id
        WHERE {where}
        ORDER BY d.char_count DESC LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    cur.execute(sql, params)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{
        "id": r[0], "file_name": r[1], "file_ext": r[2], "char_count": r[3],
        "category": r[4], "tags": r[5] or [], "summary": r[6],
        "key_points": r[7] if isinstance(r[7], dict) else json.loads(r[7]) if r[7] else {},
    } for r in rows]

@app.post("/api/documents/repair-garbled")
def repair_garbled(limit: int = 100):
    import threading
    t = threading.Thread(target=_repair_garbled_batch, args=(limit,), daemon=True)
    t.start()
    return {"status": "repair_started", "message": "后台修复中，处理前{}篇".format(limit)}

@app.post("/api/documents/check-txt-encoding")
def check_txt_encoding(limit: int = 500, offset_id: int = 0):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT id, file_path, file_name, LEFT(content_text, 500) AS preview
        FROM documents WHERE file_ext = '.txt' AND id > %s
        ORDER BY id LIMIT %s
    """, (offset_id, limit))
    rows = cur.fetchall()
    results = []
    for doc_id, fp, fname, preview in rows:
        issues = []
        if preview and chr(65533) in preview:
            issues.append("contain U+FFFD")
        if preview and len(preview.strip()) < 50:
            issues.append("too short")
        full_path = _find_file(fp, fname)
        if full_path and full_path.exists():
            raw = full_path.read_bytes()
            for enc in ['gb18030', 'utf-8', 'gbk', 'big5']:
                try:
                    raw.decode(enc)
                    break
                except:
                    continue
            else:
                issues.append("undecodable raw bytes")
        results.append({"id": doc_id, "file_name": fname, "preview": (preview or '')[:100], "issues": issues})
    cur.close(); conn.close()
    return {"items": results, "total": len(results), "last_id": rows[-1][0] if rows else None}

@app.post("/api/documents/batch-parse-all")
def batch_parse_all():
    if _batch_parse_all_status["running"]:
        return {"status": "already_running", "current": _batch_parse_all_status["current"],
                "total": _batch_parse_all_status["total"], "errors": _batch_parse_all_status["errors"]}
    import threading
    t = threading.Thread(target=_batch_parse_all_worker, daemon=True)
    t.start()
    return {"status": "started", "message": "对所有未解析文档进行解析"}

_batch_parse_all_status = {"running": False, "current": 0, "total": 0, "errors": 0, "phase": "idle"}

def _batch_parse_all_worker():
    _batch_parse_all_status["running"] = True
    _batch_parse_all_status["errors"] = 0
    _batch_parse_all_status["phase"] = "parsing"
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT id, file_path, file_name, file_ext FROM documents
            WHERE (content_text IS NULL OR content_text = '')
            AND file_ext NOT IN ('.pdf', '.merged')
            ORDER BY id
        """)
        rows = cur.fetchall(); cur.close(); conn.close()
        _batch_parse_all_status["total"] = len(rows)
        for i, (doc_id, file_path, file_name, file_ext) in enumerate(rows):
            _batch_parse_all_status["current"] = i + 1
            try:
                fp = _find_file(file_path, file_name)
                if not fp or not fp.exists():
                    continue
                if fp.stat().st_size > 104857600:
                    continue
                ext = fp.suffix.lower()
                if ext in BINARY_EBOOK_EXTS:
                    text = extract_ebook(str(fp))
                else:
                    text = fp.read_text(encoding=detect_encoding(str(fp)), errors='replace')
                if text is not None and not text.startswith('['):
                    conn2 = get_db(); cur2 = conn2.cursor()
                    if text:
                        cur2.execute("UPDATE documents SET content_text=%s, char_count=%s WHERE id=%s",
                                    (text, len(text), doc_id))
                    else:
                        cur2.execute("UPDATE documents SET content_text='(no extractable text)', char_count=0 WHERE id=%s",
                                    (doc_id,))
                    conn2.commit(); cur2.close(); conn2.close()
            except Exception:
                _batch_parse_all_status["errors"] += 1
    except Exception as e:
        print(f"  batch-parse-all error: {e}")
    _batch_parse_all_status["running"] = False
    _batch_parse_all_status["phase"] = "done"

@app.post("/api/documents/check-and-fix-txt")
def check_and_fix_txt(limit: int = 500, offset_id: int = 0):
    if _check_txt_status["running"]:
        return {"status": "already_running", "current": _check_txt_status["current"],
                "total": _check_txt_status["total"]}
    import threading
    t = threading.Thread(target=_check_and_fix_txt_worker, args=(limit, offset_id), daemon=True)
    t.start()
    return {"status": "started", "message": "后台检查修复 .txt 文件中"}

_check_txt_status = {"running": False, "current": 0, "total": 0, "fixed": 0, "skipped": 0}

def _check_and_fix_txt_worker(limit, offset_id):
    _check_txt_status["running"] = True
    _check_txt_status["fixed"] = 0
    _check_txt_status["skipped"] = 0
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT id, file_path, file_name FROM documents
            WHERE file_ext = '.txt' AND id > %s ORDER BY id LIMIT %s
        """, (offset_id, limit))
        rows = cur.fetchall(); cur.close(); conn.close()
        _check_txt_status["total"] = len(rows)
        for i, (doc_id, file_path, file_name) in enumerate(rows):
            _check_txt_status["current"] = i + 1
            try:
                fp = _find_file(file_path, file_name)
                if not fp or not fp.exists():
                    _check_txt_status["skipped"] += 1
                    continue
                raw = fp.read_bytes()
                best_content = None; best_enc = None
                for enc in ['gb18030', 'utf-8', 'gbk', 'gb2312', 'big5']:
                    try:
                        decoded = raw.decode(enc)
                        if best_content is None or decoded.count(chr(65533)) < best_content.count(chr(65533)):
                            best_content = decoded
                            best_enc = enc
                    except:
                        continue
                if best_content is None:
                    import chardet
                    det = chardet.detect(raw)
                    if det and det.get('encoding'):
                        try:
                            best_content = raw.decode(det['encoding'], errors='replace')
                            best_enc = det['encoding']
                        except:
                            best_content = raw.decode('utf-8', errors='replace')
                            best_enc = 'utf-8/replace'
                conn2 = get_db(); cur2 = conn2.cursor()
                cur2.execute("SELECT content_text FROM documents WHERE id=%s", (doc_id,))
                existing = cur2.fetchone()
                existing_text = existing[0] if existing else ''
                if existing_text != best_content:
                    cur2.execute("UPDATE documents SET content_text=%s, char_count=%s WHERE id=%s",
                                (best_content, len(best_content), doc_id))
                    _check_txt_status["fixed"] += 1
                else:
                    _check_txt_status["skipped"] += 1
                conn2.commit(); cur2.close(); conn2.close()
            except Exception as e:
                print(f"  check-txt id={doc_id} error: {e}")
                _check_txt_status["skipped"] += 1
    except Exception as e:
        print(f"  check-and-fix-txt error: {e}")
    _check_txt_status["running"] = False

@app.get("/api/documents/check-txt-status")
def get_check_txt_status():
    return _check_txt_status

@app.get("/api/documents/batch-parse-all-status")
def get_batch_parse_all_status():
    return _batch_parse_all_status

@app.post("/api/documents/batch-parse-pdf")
def batch_parse_pdf(limit: int = 100, offset_id: int = 0):
    if _batch_parse_pdf_status["running"]:
        return {"status": "already_running", "current": _batch_parse_pdf_status["current"],
                "total": _batch_parse_pdf_status["total"]}
    import threading
    t = threading.Thread(target=_batch_parse_pdf_worker, args=(limit, offset_id), daemon=True)
    t.start()
    return {"status": "started", "message": f"PDF batch parsing started, max {limit}"}

_batch_parse_pdf_status = {"running": False, "current": 0, "total": 0, "errors": 0}

def _batch_parse_pdf_worker(limit, offset_id):
    _batch_parse_pdf_status["running"] = True
    _batch_parse_pdf_status["errors"] = 0
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT id, file_path, file_name FROM documents
            WHERE file_ext = '.pdf' AND (content_text IS NULL OR content_text = '')
            AND id > %s ORDER BY id LIMIT %s
        """, (offset_id, limit))
        rows = cur.fetchall(); cur.close(); conn.close()
        _batch_parse_pdf_status["total"] = len(rows)
        for i, (doc_id, file_path, file_name) in enumerate(rows):
            _batch_parse_pdf_status["current"] = i + 1
            try:
                fp = _find_file(file_path, file_name)
                if not fp or not fp.exists() or fp.stat().st_size > 524288000:
                    continue
                from ebook_reader import extract_pdf_text
                text = extract_pdf_text(str(fp))
                if text and not text.startswith("["):
                    conn2 = get_db(); cur2 = conn2.cursor()
                    if text:
                        cur2.execute("UPDATE documents SET content_text=%s, char_count=%s WHERE id=%s",
                                    (text, len(text), doc_id))
                    else:
                        cur2.execute("UPDATE documents SET content_text='(no extractable text)', char_count=0 WHERE id=%s",
                                    (doc_id,))
                    conn2.commit(); cur2.close(); conn2.close()
            except:
                _batch_parse_pdf_status["errors"] += 1
    except:
        pass
    _batch_parse_pdf_status["running"] = False

@app.get("/api/documents/batch-parse-pdf-status")
def get_batch_parse_pdf_status():
    return _batch_parse_pdf_status

@app.get("/api/knowledge-graph")
def get_knowledge_graph(types: str = "", limit: int = 500):
    from knowledge_graph import get_graph_data
    entity_types = types.split(",") if types else None
    return get_graph_data(entity_types, limit)

@app.get("/api/knowledge-graph/entities")
def search_kg_entities(q: str = "", type: str = "", limit: int = 50):
    from knowledge_graph import search_entities
    return search_entities(q, type or None, limit)

@app.post("/api/knowledge-graph/extract")
def trigger_kg_extraction(limit: int = 200):
    import threading
    from knowledge_graph import process_all_classified
    t = threading.Thread(target=process_all_classified, args=(limit,), daemon=True)
    t.start()
    return {"status": "extraction_started", "message": "后台提取实体中"}

@app.post("/api/knowledge-graph/similarity")
def trigger_kg_similarity():
    import threading
    from knowledge_graph import build_similarity_relations
    t = threading.Thread(target=build_similarity_relations, daemon=True)
    t.start()
    return {"status": "similarity_started", "message": "后台构建相似关系中"}

@app.get("/api/recommendations/{doc_id}")
def get_recommendations(doc_id: int, limit: int = 10):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT embedding::text FROM doc_embeddings WHERE doc_id=%s", (doc_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return []
    vec_text = row[0]
    cur.execute("""
        SELECT d.id, d.file_name, d.file_ext, d.char_count,
               c.category, c.summary,
               1 - (e.embedding <=> %s::vector) AS score
        FROM doc_embeddings e
        JOIN documents d ON d.id = e.doc_id
        LEFT JOIN doc_categories c ON c.doc_id = d.id
        WHERE e.doc_id != %s
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
    """, (vec_text, doc_id, vec_text, limit))
    results = [{
        "id": r[0], "file_name": r[1], "file_ext": r[2],
        "char_count": r[3], "category": r[4], "summary": r[5],
        "score": float(r[6]) if r[6] else 0,
    } for r in cur.fetchall()]
    cur.close(); conn.close()
    return results

@app.post("/api/documents/batch-parse")
def trigger_batch_parse():
    started = _start_pipeline()
    return {"status": "started" if started else "already_running"}

@app.get("/api/documents/pipeline-status")
def get_pipeline_status():
    return _pipeline_status

@app.get("/api/documents/{doc_id}")


def get_doc(doc_id: int, max_size: int = MAX_READ_CHARS):
    conn = get_db()
    cur = conn.cursor()
    sql = """
        SELECT d.id, d.file_path, d.file_name, d.file_ext, d.file_size, d.file_hash,
               d.content_text, d.page_count, d.char_count, d.created_at, d.updated_at,
               c.category, c.tags, c.summary, c.key_points, COALESCE(d.content_path, '')
        FROM documents d
        LEFT JOIN doc_categories c ON c.doc_id = d.id
        WHERE d.id = %s
    """
    cur.execute(sql, (doc_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(404, "Document not found")
    content_text = row[6]
    content_path = row[15]
    file_path = row[1]
    content = read_content(doc_id, content_text, content_path, file_path, row[2])
    truncated = len(content) > max_size if content else False
    if truncated:
        content = content[:max_size]
    return {
        "id": row[0], "file_path": row[1], "file_name": row[2], "file_ext": row[3],
        "file_size": row[4], "file_hash": row[5], "content_text": content,
        "page_count": row[7], "char_count": row[8], "created_at": str(row[9]) if row[9] else None,
        "updated_at": str(row[10]) if row[10] else None, "category": row[11],
        "tags": row[12] or [], "summary": row[13], "key_points": row[14],
        "truncated": truncated, "total_chars": len(content) if truncated else None,
    }

@app.get("/api/documents/{doc_id}/view")
def view_doc(doc_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT file_name, content_text, content_path, file_path FROM documents WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(404, "Document not found")
    fname, content_text, content_path, file_path = row
    content = read_content(doc_id, content_text, content_path, file_path, fname)
    content = (content or '')[:MAX_READ_CHARS]
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        f'<title>{fname}</title>'
        '<style>body{max-width:800px;margin:0 auto;padding:20px;line-height:1.8;font-size:16px;}'
        'h1{border-bottom:1px solid #eee;padding-bottom:10px;}</style></head>'
        f'<body><h1>{fname}</h1>'
        '<pre style="white-space:pre-wrap;word-break:break-word;">'
        f'{content}</pre></body></html>'
    )
    return HTMLResponse(html)

@app.post("/api/documents/merge/{relation_id}")
def merge_docs(relation_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT doc_id_a, doc_id_b FROM doc_relations WHERE id=%s", (relation_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(404, "Relation not found")
    doc_id_a, doc_id_b = row
    cur.execute("SELECT file_name, content_text FROM documents WHERE id=%s", (doc_id_a,))
    row_a = cur.fetchone()
    cur.execute("SELECT file_name, content_text FROM documents WHERE id=%s", (doc_id_b,))
    row_b = cur.fetchone()
    if not row_a or not row_b:
        cur.close(); conn.close()
        raise HTTPException(404, "Source document not found")
    merged_name = f"merged_{row_a[0]}_{row_b[0]}"
    merged_text = ""
    if row_a[1]:
        merged_text += f"=== {row_a[0]} ===\n\n{row_a[1]}\n\n"
    if row_b[1]:
        merged_text += f"=== {row_b[0]} ===\n\n{row_b[1]}\n\n"
    cur.execute("""
        INSERT INTO documents (file_path, file_name, file_ext, content_text, char_count, is_processed)
        VALUES (%s, %s, '.merged', %s, %s, TRUE) RETURNING id
    """, (f"/merged/{merged_name}", merged_name, merged_text, len(merged_text)))
    merged_id = cur.fetchone()[0]
    cur.execute("UPDATE doc_relations SET merge_status='merged', merged_doc_id=%s WHERE id=%s",
                (merged_id, relation_id))
    conn.commit()
    cur.close(); conn.close()
    return {"status": "merged", "merged_doc_id": merged_id}

class OrganizeRequest(BaseModel):
    target_dir: str = '/data/organized'
    ids: list[int] = []
    delete_originals: bool = False
    dry_run: bool = False
    rule_id: int = None
    custom_pattern: str = None

def _apply_rule(pattern: str, doc: dict) -> str:
    import re
    fields = {
        'category': doc.get('category', '未分类'),
        'year': str(doc.get('year', 'unknown')),
        'author': doc.get('author', '佚名'),
        'genre': doc.get('genre', '未分类'),
        'file_name': doc.get('file_name', ''),
        'file_ext': doc.get('file_ext', ''),
        'id': str(doc.get('id', '')),
    }
    result = pattern
    for key, val in fields.items():
        safe = re.sub(r'[\\/:*?"<>|]', '_', str(val)) if val else '_'
        result = result.replace('{' + key + '}', safe)
    result = re.sub(r'/+', '/', result).strip('/')
    return result

@app.post("/api/documents/organize")
def organize_docs(req: OrganizeRequest):
    conn = get_db()
    cur = conn.cursor()
    if req.ids:
        placeholders = ','.join(['%s'] * len(req.ids))
        sql = f"""
            SELECT d.id, d.file_name, d.file_path, d.file_ext,
                   COALESCE(c.category, '未分类') as category,
                   EXTRACT(YEAR FROM d.created_at) as year,
                   COALESCE(c.key_points->>'author', '') as author,
                   COALESCE(c.key_points->>'genre', '') as genre
            FROM documents d
            LEFT JOIN doc_categories c ON c.doc_id = d.id
            WHERE d.id IN ({placeholders})
            ORDER BY d.id
        """
        cur.execute(sql, req.ids)
    else:
        cur.execute("""
            SELECT d.id, d.file_name, d.file_path, d.file_ext,
                   COALESCE(c.category, '未分类') as category,
                   EXTRACT(YEAR FROM d.created_at) as year,
                   COALESCE(c.key_points->>'author', '') as author,
                   COALESCE(c.key_points->>'genre', '') as genre
            FROM documents d
            LEFT JOIN doc_categories c ON c.doc_id = d.id
            ORDER BY d.id LIMIT 200
        """)
    rows = cur.fetchall()
    if req.rule_id:
        cur.execute("SELECT pattern FROM organize_rules WHERE id=%s", (req.rule_id,))
        rule_row = cur.fetchone()
        pattern = rule_row[0] if rule_row else '{category}/{year}/{file_name}'
    elif req.custom_pattern:
        pattern = req.custom_pattern
    else:
        pattern = '{category}/{year}/{file_name}'
    base = Path(req.target_dir)
    plan = []
    copied = 0
    deleted = 0
    for r in rows:
        doc = {
            "id": r[0], "file_name": r[1], "file_path": r[2], "file_ext": r[3],
            "category": r[4], "year": int(r[5]) if r[5] else 0,
            "author": r[6] or '', "genre": r[7] or '',
        }
        rel = _apply_rule(pattern, doc)
        target = base / rel
        plan.append({
            "id": doc["id"], "file_name": doc["file_name"],
            "file_path": doc["file_path"], "category": doc["category"],
            "year": doc["year"], "author": doc["author"], "genre": doc["genre"],
            "target_path": str(target), "old_path": doc["file_path"],
        })
        if not req.dry_run:
            src = Path(doc["file_path"])
            if src.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    import shutil
                    shutil.copy2(str(src), str(target))
                    copied += 1
                    if req.delete_originals:
                        src.unlink()
                        cur.execute("UPDATE documents SET file_path=%s WHERE id=%s", (str(target), doc["id"]))
                        deleted += 1
                except Exception as e:
                    plan[-1]['error'] = str(e)
    if not req.dry_run:
        conn.commit()
        log_operation('system', 'organize', target_type='documents',
                      details={"target_dir": req.target_dir, "delete_originals": req.delete_originals},
                      before={"plan": [{"id":p["id"],"old_path":p["old_path"],"new_path":str(p["target_path"])} for p in plan]},
                      after={"copied": copied, "deleted": deleted})
    cur.close(); conn.close()
    return {"total": len(plan), "copied": copied, "deleted": deleted, "dry_run": req.dry_run, "plan": plan}

@app.get("/api/organize/rules")
def list_organize_rules():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, name, pattern, is_default FROM organize_rules ORDER BY is_default DESC, id")
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"id": r[0], "name": r[1], "pattern": r[2], "is_default": r[3]} for r in rows]

class RuleCreate(BaseModel):
    name: str
    pattern: str

@app.post("/api/organize/rules")
def create_organize_rule(rule: RuleCreate):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO organize_rules (name, pattern) VALUES (%s,%s) RETURNING id", (rule.name, rule.pattern))
    rid = cur.fetchone()[0]; conn.commit(); cur.close(); conn.close()
    return {"id": rid, "status": "created"}

@app.delete("/api/organize/rules/{rule_id}")
def delete_organize_rule(rule_id: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM organize_rules WHERE id=%s AND is_default=FALSE", (rule_id,))
    deleted = cur.rowcount; conn.commit(); cur.close(); conn.close()
    if not deleted:
        raise HTTPException(404, "Rule not found or is default")
    return {"status": "deleted"}

@app.get("/api/organize/suggest/{doc_id}")
def suggest_organize(doc_id: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.file_name, d.content_text,
               COALESCE(c.category, '') as category,
               COALESCE(c.key_points->>'author', '') as author,
               COALESCE(c.key_points->>'genre', '') as genre
        FROM documents d LEFT JOIN doc_categories c ON c.doc_id = d.id
        WHERE d.id=%s
    """, (doc_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row:
        raise HTTPException(404, "Not found")
    text = (row[2] or '')[:2000]
    try:
        resp = httpx.post(os.getenv('OLLAMA_URL', 'http://ollama:11434') + '/api/generate',
            json={"model": "qwen2.5:7b", "prompt": f"分析以下文本，返回最适合的分类（从：小说/历史/科技/经济管理/教育/文学/生活/哲学/军事/医学/宗教/政治法律/传记/自然科学 中选择一个）和体裁（从：玄幻/仙侠/都市/言情/历史/武侠/科幻/悬疑/恐怖/军事/游戏/轻小说 中选择一个）。只返回JSON：{{'category':'','genre':''}}\n\n文本：{text[:1500]}", "stream": False, "options": {"num_predict": 128}},
            timeout=60)
        data = resp.json()
        raw = data.get('response', '').strip()
        import re
        m = re.search(r'\{[^}]+\}', raw)
        if m:
            result = json.loads(m.group())
        else:
            result = {"category": row[3] or '其他', "genre": row[5] or '未分类'}
    except:
        result = {"category": row[3] or '其他', "genre": row[5] or '未分类'}
    result["file_name"] = row[1]
    result["current_category"] = row[3]
    result["current_author"] = row[4]
    return result

# ===== Document Sources Management =====

CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS doc_sources (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    path            TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'local',
    mount_config    JSONB,
    enabled         BOOLEAN DEFAULT TRUE,
    last_scanned    TIMESTAMPTZ,
    file_count      INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
)
"""

@app.get("/api/sources")
def list_sources():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, path, source_type, enabled, last_scanned, file_count, created_at FROM doc_sources ORDER BY id")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{
        "id": r[0], "name": r[1], "path": r[2], "source_type": r[3],
        "enabled": r[4], "last_scanned": str(r[5]) if r[5] else None,
        "file_count": r[6], "created_at": str(r[7]) if r[7] else None,
    } for r in rows]

class SourceCreate(BaseModel):
    name: str
    path: str
    source_type: str = 'local'
    mount_config: dict = {}

@app.post("/api/sources")
def create_source(src: SourceCreate):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM doc_sources WHERE path=%s", (src.path,))
    if cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(400, "Source path already exists")
    cur.execute("""
        INSERT INTO doc_sources (name, path, source_type, mount_config)
        VALUES (%s,%s,%s,%s) RETURNING id
    """, (src.name, src.path, src.source_type, json.dumps(src.mount_config) if src.mount_config else '{}'))
    src_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return {"id": src_id, "status": "created"}

@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM doc_sources WHERE id=%s", (source_id,))
    deleted = cur.rowcount
    conn.commit()
    cur.close(); conn.close()
    if not deleted:
        raise HTTPException(404, "Source not found")
    return {"status": "deleted"}

@app.post("/api/sources/{source_id}/scan")
def scan_source(source_id: int, cleanup: bool = False):
    import threading
    def _run():
        c, d = scan_source_inner(source_id, cleanup=cleanup)
        print("  scan source {} done: {} added, {} cleaned".format(source_id, c, d))
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "scan_started", "message": "后台扫描中"}

@app.post("/api/sources/scan-all")
def scan_all_sources(cleanup: bool = False):
    import threading
    def _run_all():
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id FROM doc_sources WHERE enabled=TRUE")
        ids = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        for sid in ids:
            c, d = scan_source_inner(sid, cleanup=cleanup)
            print("  scan source {}: {} added, {} cleaned".format(sid, c, d))
    t = threading.Thread(target=_run_all, daemon=True)
    t.start()
    return {"status": "scan_started", "message": "后台扫描中"}

def scan_source_inner(source_id: int, cleanup: bool = False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, path, name FROM doc_sources WHERE id=%s AND enabled=TRUE", (source_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return 0
    src_id, src_path, src_name = row
    base = Path(src_path)
    count = 0
    deleted = 0
    SUPPORTED_EXTS = {'.txt','.pdf','.epub','.mobi','.azw3','.doc','.docx','.md','.html','.htm','.csv'}
    if base.exists():
        existing_paths = set()
        for f in base.rglob('*'):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS and not f.name.startswith('.'):
                existing_paths.add(str(f))
                try:
                    cur.execute("SELECT id FROM documents WHERE file_path=%s", (str(f),))
                    if not cur.fetchone():
                        cur.execute("""
                            INSERT INTO documents (file_path, file_name, file_ext, file_size, content_text, char_count)
                            VALUES (%s,%s,%s,%s,'',0)
                        """, (str(f), f.name, f.suffix.lower(), f.stat().st_size))
                        count += 1
                except:
                    pass
        if cleanup and existing_paths:
            cur.execute("""
                SELECT id, file_path FROM documents
                WHERE file_path LIKE %s AND file_path NOT IN (SELECT unnest(%s::text[]))
            """, (src_path + '%', list(existing_paths)))
            stale = cur.fetchall()
            for doc_id, fp in stale:
                cur.execute("DELETE FROM doc_embeddings WHERE doc_id=%s", (doc_id,))
                cur.execute("DELETE FROM doc_categories WHERE doc_id=%s", (doc_id,))
                cur.execute("DELETE FROM documents WHERE id=%s", (doc_id,))
                deleted += 1
    cur.execute("UPDATE doc_sources SET last_scanned=NOW(), file_count=file_count+%s WHERE id=%s", (count, src_id))
    conn.commit()
    cur.close(); conn.close()
    return count, deleted

def _continuous_scan_loop(interval: int = 300):
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    enrich_cycle = 0
    while True:
        try:
            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT id FROM doc_sources WHERE enabled=TRUE")
            ids = [r[0] for r in cur.fetchall()]
            cur.close(); conn.close()
            for sid in ids:
                try:
                    scan_source_inner(sid, cleanup=True)
                except:
                    pass
            # Every 5 scan cycles (~25 min), enrich new unclassified docs in batches
            enrich_cycle += 1
            if enrich_cycle % 5 == 0:
                try:
                    conn2 = get_db(); cur2 = conn2.cursor()
                    cur2.execute("SELECT d.id FROM documents d LEFT JOIN doc_categories c ON c.doc_id = d.id WHERE c.doc_id IS NULL AND d.content_text IS NOT NULL AND length(d.content_text) > 50 ORDER BY d.id LIMIT 200")
                    new_ids = [r[0] for r in cur2.fetchall()]
                    cur2.close(); conn2.close()
                    if new_ids:
                        import threading
                        enrich_lock = threading.Lock()
                        done = 0
                        def _enrich(doc_id):
                            nonlocal done
                            try:
                                _enrich_internal(doc_id)
                            except:
                                pass
                            with enrich_lock:
                                done += 1
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [pool.submit(_enrich, did) for did in new_ids]
                            for f in as_completed(futures):
                                pass
                except:
                    pass
        except:
            pass
        time.sleep(interval)

_pipeline_status = {"running": False, "phase": "idle", "current": 0, "total": 0, "errors": 0}

def _batch_pipeline_worker():
    _pipeline_status["running"] = True
    _pipeline_status["phase"] = "parse"
    try:
        # Phase 1: parse all empty docs
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id, file_path, file_name, file_ext FROM documents WHERE (content_text IS NULL OR content_text = '') AND COALESCE(content_text, '') != '(no extractable text)' AND file_ext NOT IN ('.pdf', '.merged') ORDER BY id")
        rows = cur.fetchall(); cur.close(); conn.close()
        _pipeline_status["total"] = len(rows)
        _pipeline_status["current"] = 0
        _pipeline_status["errors"] = 0
        for i, (doc_id, file_path, file_name, file_ext) in enumerate(rows):
            _pipeline_status["current"] = i + 1
            try:
                fp = _find_file(file_path, file_name)
                if not fp or not fp.exists() or fp.stat().st_size > 104857600:
                    continue
                ext = fp.suffix.lower()
                if ext in BINARY_EBOOK_EXTS:
                    if ext == '.pdf':
                        continue
                    text = extract_ebook(str(fp))
                else:
                    text = fp.read_text(encoding=detect_encoding(str(fp)), errors='replace')
                if text is not None and not text.startswith('['):
                    conn2 = get_db(); cur2 = conn2.cursor()
                    if text:
                        cur2.execute("UPDATE documents SET content_text=%s, char_count=%s WHERE id=%s",
                                    (text, len(text), doc_id))
                    else:
                        cur2.execute("UPDATE documents SET content_text='(no extractable text)', char_count=0 WHERE id=%s",
                                    (doc_id,))
                    conn2.commit(); cur2.close(); conn2.close()
            except Exception:
                _pipeline_status["errors"] += 1
        # Phase 2: enrich all unclassified docs (parallel batches)
        _pipeline_status["phase"] = "enrich"
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT d.id FROM documents d LEFT JOIN doc_categories c ON c.doc_id = d.id WHERE c.doc_id IS NULL AND d.content_text IS NOT NULL AND length(d.content_text) > 50 ORDER BY d.id")
        all_enrich_rows = cur.fetchall(); cur.close(); conn.close()
        _pipeline_status["total"] = len(all_enrich_rows)
        _pipeline_status["current"] = 0
        _pipeline_lock = threading.Lock()
        BATCH_SIZE = 50
        def _enrich_one(doc_id):
            try:
                _enrich_internal(doc_id)
                with _pipeline_lock:
                    _pipeline_status["current"] += 1
            except Exception:
                with _pipeline_lock:
                    _pipeline_status["errors"] += 1
                    _pipeline_status["current"] += 1
        for batch_start in range(0, len(all_enrich_rows), BATCH_SIZE):
            batch = all_enrich_rows[batch_start:batch_start + BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(_enrich_one, doc_id) for (doc_id,) in batch]
                for f in as_completed(futures):
                    pass
        # Phase 3: embed all classified but unembedded docs (parallel batches)
        _pipeline_status["phase"] = "embed"
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT d.id, d.content_text FROM documents d JOIN doc_categories c ON c.doc_id = d.id LEFT JOIN doc_embeddings e ON e.doc_id = d.id WHERE e.doc_id IS NULL AND d.content_text IS NOT NULL AND length(d.content_text) > 50 ORDER BY d.id")
        all_embed_rows = cur.fetchall(); cur.close(); conn.close()
        _pipeline_status["total"] = len(all_embed_rows)
        _pipeline_status["current"] = 0
        _pipeline_lock = threading.Lock()
        BATCH_SIZE = 50
        def _embed_one(doc_id, text):
            try:
                emb = get_embedding(text[:2000])
                if emb:
                    conn2 = get_db(); cur2 = conn2.cursor()
                    cur2.execute("INSERT INTO doc_embeddings (doc_id, embedding) VALUES (%s, %s::vector) ON CONFLICT (doc_id) DO UPDATE SET embedding=%s::vector",
                                (doc_id, emb, emb))
                    conn2.commit(); cur2.close(); conn2.close()
                    try:
                        _index_doc_to_es_by_id(doc_id)
                    except:
                        pass
                with _pipeline_lock:
                    _pipeline_status["current"] += 1
            except Exception:
                with _pipeline_lock:
                    _pipeline_status["errors"] += 1
                    _pipeline_status["current"] += 1
        for batch_start in range(0, len(all_embed_rows), BATCH_SIZE):
            batch = all_embed_rows[batch_start:batch_start + BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(_embed_one, doc_id, text) for (doc_id, text) in batch]
                for f in as_completed(futures):
                    pass
    except Exception as e:
        _pipeline_status["errors"] += 1
    _pipeline_status["running"] = False
    _pipeline_status["phase"] = "done"

def _start_pipeline():
    import threading
    if not _pipeline_status["running"]:
        t = threading.Thread(target=_batch_pipeline_worker, daemon=True)
        t.start()
        return True
    return False

# ===== Metadata & AI Enrichment =====

@app.get("/api/metadata/authors")
def list_authors():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT key_points->>'author' as author, COUNT(*) as cnt
        FROM doc_categories WHERE key_points IS NOT NULL AND key_points->>'author' != ''
        GROUP BY author ORDER BY cnt DESC LIMIT 100
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"author": r[0], "count": r[1]} for r in rows]

@app.get("/api/metadata/years")
def list_years():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT (key_points->>'publish_year')::int as year, COUNT(*) as cnt
        FROM doc_categories WHERE key_points IS NOT NULL AND key_points->>'publish_year' != '0'
        GROUP BY year ORDER BY year DESC LIMIT 100
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"year": r[0], "count": r[1]} for r in rows]

@app.get("/api/metadata/genres")
def list_genres():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT key_points->>'genre' as genre, COUNT(*) as cnt
        FROM doc_categories WHERE key_points IS NOT NULL AND key_points->>'genre' != ''
        GROUP BY genre ORDER BY cnt DESC LIMIT 100
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"genre": r[0], "count": r[1]} for r in rows]

@app.get("/api/metadata/categories")
def list_categories_for_browse():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT category, COUNT(*) as cnt FROM doc_categories GROUP BY category ORDER BY cnt DESC")
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"category": r[0], "count": r[1]} for r in rows]

def _repair_garbled_batch(limit: int = 100):
    try:
        conn = get_db()
        cur = conn.cursor()
        ff = chr(65533)
        cur.execute("""
            SELECT id, file_path, file_name, file_ext FROM documents
            WHERE content_text IS NOT NULL AND content_text != ''
            AND (
                content_text LIKE %s
                OR content_text LIKE %s
                OR content_text LIKE %s
                OR content_text LIKE %s
            )
            AND file_ext IN ('.txt', '.htm', '.html', '.pdf')
            ORDER BY id LIMIT %s
        """, ('%' + ff + '%', '%PDF-%', '%PK%', '%BOOKMOBI%', limit))
        rows = cur.fetchall()
        fixed = 0; failed = 0
        print("Repair: found {} garbled docs".format(len(rows)))
        for doc_id, file_path, file_name, file_ext in rows:
            try:
                fp = _find_file(file_path or '', file_name or '')
                if not fp or not fp.exists():
                    print("  id={} file not found: {}/{}".format(doc_id, file_path, file_name))
                    failed += 1
                    continue
                raw = fp.read_bytes()
                content = None
                if file_ext == '.pdf':
                    from ebook_reader import extract_pdf_text
                    content = extract_pdf_text(str(fp))
                else:
                    if len(raw) >= 3 and raw[:3] == b'\xef\xbb\xbf':
                        try:
                            content = raw[3:].decode('utf-8')
                        except:
                            try:
                                content = raw[3:].decode('utf-8', errors='replace')
                            except:
                                pass
                    if content is None and len(raw) >= 2:
                        if raw[:2] == b'\xff\xfe':
                            try: content = raw.decode('utf-16-le')
                            except: pass
                        elif raw[:2] == b'\xfe\xff':
                            try: content = raw.decode('utf-16-be')
                            except: pass
                    if content is None:
                        try:
                            import chardet
                            det = chardet.detect(raw[:8192])
                            if det and det.get('encoding') and det.get('confidence', 0) > 0.8:
                                enc = det['encoding'].lower().replace('-', '').replace('_', '')
                                if enc in ('utf8', 'ascii'): enc = 'utf-8'
                                try:
                                    content = raw.decode(enc)
                                except:
                                    content = raw.decode(enc, errors='replace')
                        except:
                            pass
                    if content is None:
                        # Try all encodings strictly first
                        for enc in ['gb18030', 'utf-8', 'gbk', 'gb2312', 'big5']:
                            try:
                                content = raw.decode(enc)
                                break
                            except:
                                continue
                    if content is None:
                        # Fallback: pick encoding with fewest U+FFFD
                        best = None
                        best_ff = float('inf')
                        for enc in ['gb18030', 'utf-8', 'gbk', 'gb2312', 'big5']:
                            try:
                                t = raw.decode(enc, errors='replace')
                                ff = t.count(chr(65533))
                                if ff < best_ff:
                                    best, best_ff = t, ff
                            except:
                                continue
                        content = best
                    if content is None:
                        content = raw.decode('utf-8', errors='replace')
                clean = content.replace('\x00', '')
                cur.execute("UPDATE documents SET content_text=%s, char_count=%s WHERE id=%s",
                            (clean, len(clean), doc_id))
                fixed += 1
            except Exception as e:
                print("  id={} error: {}".format(doc_id, e))
                failed += 1
        conn.commit()
        cur.close(); conn.close()
        print("Repair batch done: {} fixed, {} failed (processed {} rows)".format(fixed, failed, len(rows)))
    except Exception as e:
        print("Repair batch CRASHED: {}".format(e))
        import traceback
        traceback.print_exc()

def _enrich_internal(doc_id: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT content_text, file_name FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        cur.close(); conn.close()
        raise HTTPException(404, "Document not found or empty")
    text = row[0][:4000]
    fname = row[1] or ''
    cur.close(); conn.close()

    prompt = (
        'You are an expert at Chinese literature analysis. Analyze the following text and file name. '
        'Return ONLY valid JSON with these fields:\n'
        '- real_title: the actual title of the work (extract from text or filename; clean extensions/suffixes)\n'
        '- author: the author name if found in text, otherwise ""\n'
        '- publish_year: estimated year as integer (0 if unknown)\n'
        '- genre: best-fit genre from: 玄幻, 仙侠, 都市, 言情, 历史, 武侠, 科幻, 悬疑, 恐怖, 军事, 游戏, 轻小说 (infer from content even if uncertain)\n'
        '- language: "Chinese" or "English" based on content\n'
        '- summary: 2-3 sentence summary in Chinese\n'
        '- tags: up to 5 relevant topic tags in Chinese\n'
        '- category: one of ' + str(['小说','历史','哲学','科技','经济管理','教育','文学','其他']) + '\n'
        'Filename: ' + fname + '\n'
        'Text: ' + text[:2500]
    )
    try:
        r = httpx.post(f'{os.getenv("OLLAMA_URL","http://ollama:11434")}/api/generate', json={
            'model': 'qwen2.5:7b', 'prompt': prompt, 'stream': False,
            'options': {'num_predict': 512}
        }, timeout=300)
        resp = r.json().get('response', '')
        cleaned = resp.strip().strip('```json').strip('```').strip()
        result = json.loads(cleaned)
    except Exception as e:
        raise HTTPException(500, f"AI enrichment failed: {e}")

    kp = {
        'real_title': result.get('real_title', ''),
        'author': result.get('author', ''),
        'publish_year': result.get('publish_year', 0),
        'genre': result.get('genre', ''),
        'language': result.get('language', ''),
    }
    cat = result.get('category', '其他')
    tags = result.get('tags', [])
    summary = result.get('summary', '')

    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM doc_categories WHERE doc_id=%s", (doc_id,))
    existing = cur.fetchone()
    if existing:
        cur.execute("""
            UPDATE doc_categories SET category=%s, tags=%s, summary=%s, key_points=%s::jsonb, updated_at=NOW()
            WHERE doc_id=%s
        """, (cat, tags, summary, json.dumps(kp, ensure_ascii=False), doc_id))
    else:
        cur.execute("""
            INSERT INTO doc_categories (doc_id, category, tags, summary, key_points)
            VALUES (%s,%s,%s,%s,%s::jsonb)
        """, (doc_id, cat, tags, summary, json.dumps(kp, ensure_ascii=False)))
    conn.commit(); cur.close(); conn.close()
    return {"status": "enriched", "category": cat, "metadata": kp}

@app.post("/api/documents/{doc_id}/enrich")
def enrich_doc(doc_id: int):
    return _enrich_internal(doc_id)

@app.post("/api/documents/enrich-batch")
def enrich_batch(limit: int = 10):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT d.id FROM documents d
        LEFT JOIN doc_categories c ON c.doc_id = d.id
        WHERE c.doc_id IS NULL AND d.content_text IS NOT NULL AND length(d.content_text) > 50
        ORDER BY d.id LIMIT %s
    """, (limit,))
    ids = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    done = 0
    errors = []
    for doc_id in ids:
        try:
            _enrich_internal(doc_id)
            done += 1
        except Exception as e:
            errors.append({"id": doc_id, "error": str(e)})
    return {"total": len(ids), "enriched": done, "errors": errors}

@app.post("/api/documents/{doc_id}/cache-to-nfs")
def cache_doc_to_nfs(doc_id: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT file_name, content_text, content_path, file_path FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(404, "Document not found")
    fname, content_text, content_path, file_path = row
    if content_path and Path(content_path).exists():
        cur.close(); conn.close()
        return {"status": "already_cached", "path": content_path}
    content = content_text or ''
    if not content and file_path:
        fp = _find_file(file_path, fname)
        if fp:
            enc = detect_encoding(str(fp))
            try:
                content = fp.read_text(encoding=enc, errors='replace')
            except:
                pass
    if not content:
        cur.close(); conn.close()
        raise HTTPException(400, "No content available to cache")
    cache_dir = CACHE_ROOT / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{doc_id}_{fname}.txt"
    cache_path.write_text(content, encoding='utf-8')
    cur.execute("UPDATE documents SET content_path=%s, content_text='' WHERE id=%s", (str(cache_path), doc_id))
    conn.commit(); cur.close(); conn.close()
    return {"status": "cached", "path": str(cache_path)}

# ===== Embeddings & Semantic Search =====

def get_embedding(text: str) -> list:
    try:
        r = httpx.post(f'{os.getenv("OLLAMA_URL","http://ollama:11434")}/api/embed', json={
            'model': 'bge-m3', 'input': text[:1536], 'options': {'batch_size': 512}
        }, timeout=120)
        data = r.json()
        emb = data.get('embeddings', [None])[0]
        return emb if emb else None
    except:
        return None

@app.get("/api/documents/{doc_id}/similar")
def similar_docs(doc_id: int, limit: int = 10):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT embedding FROM doc_embeddings WHERE doc_id=%s", (doc_id,))
    target_emb = cur.fetchone()
    if not target_emb:
        cur.close(); conn.close()
        return []
    cur.execute("""
        SELECT d.id, d.file_name, c.category, 1 - (e.embedding <=> %s::vector) AS sim
        FROM doc_embeddings e
        JOIN documents d ON d.id = e.doc_id
        LEFT JOIN doc_categories c ON c.doc_id = d.id
        WHERE e.doc_id != %s
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
    """, (target_emb[0], doc_id, target_emb[0], limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"id": r[0], "file_name": r[1], "category": r[2], "similarity": round(r[3], 4)} for r in rows]

@app.post("/api/documents/detect-duplicates")
def detect_duplicates(threshold: float = 0.70, ngram_threshold: float = 0.15, limit: int = 200):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT e1.doc_id AS id_a, e2.doc_id AS id_b,
               1 - (e1.embedding <=> e2.embedding) AS vec_sim
        FROM doc_embeddings e1
        JOIN doc_embeddings e2 ON e1.doc_id < e2.doc_id
        WHERE (e1.embedding <=> e2.embedding) < %s
        ORDER BY vec_sim DESC
        LIMIT %s
    """, (1 - threshold, limit))
    candidates = cur.fetchall()
    inserted = 0
    skipped = 0
    for id_a, id_b, vec_sim in candidates:
        cur.execute("SELECT id FROM doc_relations WHERE ((doc_id_a=%s AND doc_id_b=%s) OR (doc_id_a=%s AND doc_id_b=%s)) AND relation_type='similar'",
                    (id_a, id_b, id_b, id_a))
        if cur.fetchone():
            skipped += 1
            continue
        cur.execute("SELECT content_text FROM documents WHERE id=%s", (id_a,))
        text_a = (cur.fetchone() or [None])[0] or ''
        cur.execute("SELECT content_text FROM documents WHERE id=%s", (id_b,))
        text_b = (cur.fetchone() or [None])[0] or ''
        ngram = ngram_similarity(text_a, text_b, 8)
        if ngram >= ngram_threshold:
            combined = round(vec_sim * 0.3 + ngram * 0.7, 4)
            cur.execute("INSERT INTO doc_relations (doc_id_a, doc_id_b, relation_type, similarity_score) VALUES (%s,%s,'similar',%s)",
                        (id_a, id_b, combined))
            inserted += 1
    conn.commit(); cur.close(); conn.close()
    return {"found": len(candidates), "inserted": inserted, "skipped": skipped}

@app.get("/api/documents/compare/{doc_id_a}/{doc_id_b}")
def compare_docs(doc_id_a: int, doc_id_b: int, max_size: int = 50000):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, file_name, content_text FROM documents WHERE id IN (%s,%s)", (doc_id_a, doc_id_b))
    rows = {r[0]: {"file_name": r[1], "content": (r[2] or '')[:max_size]} for r in cur.fetchall()}
    cur.close(); conn.close()
    if len(rows) < 2:
        raise HTTPException(404, "One or both documents not found")
    return {"doc_a": {"id": doc_id_a, **rows[doc_id_a]}, "doc_b": {"id": doc_id_b, **rows[doc_id_b]}}

@app.get("/api/series")
def list_series(limit: int = 100, offset: int = 0):
    from knowledge_graph import get_db as kg_db, search_entities
    return search_entities("", "series", limit)

@app.post("/api/series")
def create_series(name: str, description: str = ""):
    from knowledge_graph import get_db as kg_db, get_or_create_entity
    conn = kg_db(); cur = conn.cursor()
    eid = get_or_create_entity(cur, "series", name.strip(), {"description": description})
    conn.commit(); cur.close(); conn.close()
    return {"id": eid, "name": name, "description": description}

@app.put("/api/series/{series_id}")
def update_series(series_id: int, name: str = None, description: str = None):
    from knowledge_graph import get_db as kg_db
    conn = kg_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM entities WHERE id=%s AND entity_type='series'", (series_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(404, "Series not found")
    updates = []
    params = []
    if name is not None:
        updates.append("name=%s"); params.append(name.strip())
    if description is not None:
        updates.append("metadata=metadata || %s::jsonb"); params.append(json.dumps({"description": description}))
    if updates:
        cur.execute("UPDATE entities SET {} WHERE id=%s".format(", ".join(updates)), params + [series_id])
    conn.commit(); cur.close(); conn.close()
    return {"status": "updated"}

@app.delete("/api/series/{series_id}")
def delete_series(series_id: int):
    from knowledge_graph import get_db as kg_db
    conn = kg_db(); cur = conn.cursor()
    cur.execute("DELETE FROM entity_relations WHERE source_id=%s OR target_id=%s", (series_id, series_id))
    cur.execute("DELETE FROM entities WHERE id=%s AND entity_type='series'", (series_id,))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    if not deleted:
        raise HTTPException(404, "Series not found")
    return {"status": "deleted"}

@app.get("/api/series/{series_id}/documents")
def get_series_docs(series_id: int):
    from knowledge_graph import get_db as kg_db
    conn = kg_db(); cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.name, e.metadata FROM entities e
        JOIN entity_relations r ON r.target_id = e.id
        WHERE r.source_id=%s AND r.relation_type='part_of_series' AND e.entity_type='document'
    """, (series_id,))
    doc_entities = cur.fetchall()
    conn.commit(); cur.close(); conn.close()
    return doc_entities

@app.post("/api/series/{series_id}/documents")
def add_doc_to_series(series_id: int, doc_id: int):
    from knowledge_graph import get_db as kg_db, get_or_create_entity, add_relation
    conn = kg_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM entities WHERE id=%s AND entity_type='series'", (series_id,))
    if not cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(404, "Series not found")
    cur.execute("SELECT file_name FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(404, "Document not found")
    doc_eid = get_or_create_entity(cur, "document", row[0], {"doc_id": doc_id})
    add_relation(cur, "series", series_id, "document", doc_eid, "part_of_series")
    conn.commit(); cur.close(); conn.close()
    return {"status": "added"}

@app.delete("/api/series/{series_id}/documents/{doc_id}")
def remove_doc_from_series(series_id: int, doc_id: int):
    from knowledge_graph import get_db as kg_db
    conn = kg_db(); cur = conn.cursor()
    cur.execute("""
        DELETE FROM entity_relations r USING entities e
        WHERE r.source_id=%s AND r.target_id=e.id
        AND e.metadata->>'doc_id' = %s::text
        AND r.relation_type='part_of_series'
    """, (series_id, str(doc_id)))
    deleted = cur.rowcount
    conn.commit(); cur.close(); conn.close()
    return {"status": "removed" if deleted else "not_found"}

@app.post("/api/documents/{doc_id}/embed")
def embed_doc(doc_id: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT content_text FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        raise HTTPException(404, "Document not found")
    text = row[0] or ''
    if len(text) < 10:
        cur.close(); conn.close()
        raise HTTPException(400, "Content too short to embed")
    emb = get_embedding(text)
    if not emb:
        raise HTTPException(500, "Embedding generation failed")
    cur.execute("INSERT INTO doc_embeddings (doc_id, embedding) VALUES (%s,%s::vector) ON CONFLICT (doc_id) DO UPDATE SET embedding=%s::vector",
                (doc_id, emb, emb))
    conn.commit(); cur.close(); conn.close()
    log_operation('system', 'embed', target_type='document', target_id=doc_id)
    return {"status": "embedded", "doc_id": doc_id, "dimensions": len(emb)}

@app.post("/api/embeddings/generate-batch")
def embed_batch(limit: int = 50):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.content_text FROM documents d
        LEFT JOIN doc_embeddings e ON e.doc_id = d.id
        WHERE e.doc_id IS NULL AND d.content_text IS NOT NULL AND length(d.content_text) > 50
        ORDER BY d.id LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    done = 0
    for doc_id, text in rows:
        emb = get_embedding(text)
        if emb:
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO doc_embeddings (doc_id, embedding) VALUES (%s,%s::vector) ON CONFLICT (doc_id) DO UPDATE SET embedding=%s::vector",
                        (doc_id, emb, emb))
            conn.commit(); cur.close(); conn.close()
            done += 1
    return {"total": len(rows), "embedded": done}

# ===== File Browser & Management =====

ROOT_DIRS = {
    'originals': '/data/originals',
    'output': '/data/output',
    'cache': str(CACHE_ROOT / 'cache'),
    'organized': str(CACHE_ROOT / 'organized'),
}

@app.get("/api/files/list")
def list_files(path: str = '', dir_key: str = 'originals', page: int = 1, page_size: int = 50):
    base = Path(ROOT_DIRS.get(dir_key, ROOT_DIRS['originals']))
    if path:
        target = base / path.lstrip('/')
    else:
        target = base
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Directory not found")
    try:
        all_entries = []
        for f in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                stat = f.stat()
                all_entries.append({
                    "name": f.name,
                    "path": str(f.relative_to(base)),
                    "is_dir": f.is_dir(),
                    "size": stat.st_size if f.is_file() else 0,
                    "modified": str(datetime.fromtimestamp(stat.st_mtime)),
                })
            except:
                pass
        dirs = [e for e in all_entries if e['is_dir']]
        files = [e for e in all_entries if not e['is_dir']]
        total = len(all_entries)
        start = (page - 1) * page_size
        end = start + page_size
        page_entries = dirs + files[start:end] if start < len(dirs) else files[start - len(dirs):end - len(dirs)]
        try:
            rel = str(target.relative_to(base)) if target != base else ''
            parent_rel = str(target.parent.relative_to(base)) if target.parent != base and base in target.parents else ''
        except ValueError:
            rel = ''; parent_rel = ''
        return {
            "current_dir": str(target),
            "relative_path": rel,
            "parent": parent_rel,
            "total": total,
            "page": page,
            "page_size": page_size,
            "dirs": dirs,
            "files": files,
            "entries": dirs + files,
        }
    except PermissionError:
        raise HTTPException(403, "Permission denied")

@app.post("/api/files/delete")
def delete_file(path: str = '', dir_key: str = 'originals'):
    base = Path(ROOT_DIRS.get(dir_key, ROOT_DIRS['originals']))
    target = base / path.lstrip('/')
    if not target.exists():
        raise HTTPException(404, "File not found")
    try:
        if target.is_file():
            target.unlink()
        elif target.is_dir():
            import shutil
            shutil.rmtree(str(target))
        return {"status": "deleted", "path": path}
    except Exception as e:
        raise HTTPException(500, f"Delete failed: {e}")

@app.post("/api/files/rename")
def rename_file(path: str = '', new_name: str = '', dir_key: str = 'originals'):
    base = Path(ROOT_DIRS.get(dir_key, ROOT_DIRS['originals']))
    target = base / path.lstrip('/')
    if not target.exists():
        raise HTTPException(404, "File not found")
    new_path = target.parent / new_name
    try:
        target.rename(new_path)
        return {"status": "renamed", "old_path": path, "new_path": str(new_path.relative_to(base))}
    except Exception as e:
        raise HTTPException(500, f"Rename failed: {e}")

def detect_encoding(path):
    raw = open(path, 'rb').read(8192)
    if len(raw) >= 3 and raw[:3] == b'\xef\xbb\xbf': return 'utf-8'
    if len(raw) >= 2:
        if raw[:2] == b'\xff\xfe': return 'utf-16-le'
        if raw[:2] == b'\xfe\xff': return 'utf-16-be'
    for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'big5', 'shift_jis']:
        try:
            raw.decode(enc)
            return enc
        except:
            continue
    try:
        import chardet
        result = chardet.detect(raw)
        enc = result.get('encoding', 'utf-8') or 'utf-8'
        enc = enc.lower().replace('-', '')
        if enc in ('ascii', 'utf8'): return 'utf-8'
        if enc in ('gb2312', 'gbk', 'gb18030', 'big5', 'shift_jis', 'euc-kr', 'eucjp'): return enc
        if 'gb' in enc or 'big5' in enc: return enc
    except:
        pass
    return 'utf-8'

BINARY_EXTS = {'.zip', '.rar', '.7z', '.gz', '.tar', '.djvu', '.exe', '.bin', '.dat', '.png', '.jpg', '.gif', '.bmp'}
BINARY_EBOOK_EXTS = {'.pdf', '.mobi', '.umd', '.epub', '.doc', '.docx', '.rtf', '.azw3'}
BINARY_HEADER_MAGIC = {b'\x89\x9b\x9a\xde': '.umd'}

def extract_ebook(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in {'.umd'}:
        try:
            from umd_reader import extract_text_from_umd
            return extract_text_from_umd(path)
        except Exception:
            pass
    elif ext in {'.pdf', '.doc', '.docx', '.rtf', '.mobi', '.epub', '.azw3'}:
        try:
            from ebook_reader import extract_binary_ebook
            return extract_binary_ebook(path)
        except Exception:
            pass
    return None

@app.get("/api/files/read")
def read_file(path: str = '', dir_key: str = 'originals', max_size: int = 5_000_000):
    base = Path(ROOT_DIRS.get(dir_key, ROOT_DIRS['originals']))
    target = base / path.lstrip('/')
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    if target.stat().st_size > max_size:
        return {"warning": "File too large", "size": target.stat().st_size, "truncated": True}
    ext = Path(target.name).suffix.lower()
    raw = target.read_bytes()
    if ext in BINARY_EBOOK_EXTS or (len(raw) >= 4 and raw[:4] == b'\x89\x9b\x9a\xde'):
        ebook_text = extract_ebook(str(target))
        if ebook_text:
            return {"file_name": target.name, "size": len(ebook_text), "content": ebook_text, "encoding": ext[1:] or "binary_ebook"}
        raise HTTPException(415, f"Binary ebook format ({ext or 'unknown'}), could not extract text")
    if ext in BINARY_EXTS:
        raise HTTPException(415, f"Binary file format ({ext or 'unknown'}), not readable as text")
    try:
        if len(raw) >= 3 and raw[:3] == b'\xef\xbb\xbf':
            return {"file_name": target.name, "size": len(raw), "content": raw[3:].decode('utf-8'), "encoding": 'utf-8-bom'}
        if len(raw) >= 2 and raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            enc = 'utf-16-le' if raw[:2] == b'\xff\xfe' else 'utf-16-be'
            return {"file_name": target.name, "size": len(raw), "content": raw.decode(enc), "encoding": enc}
        raw8k = raw[:8192]
        best_content = None
        best_enc = None
        for enc in ['utf-8', 'gb18030', 'gbk', 'gb2312', 'big5', 'shift_jis']:
            try:
                best_content = raw.decode(enc)
                best_enc = enc
                break
            except:
                continue
        if best_content is None:
            try:
                import chardet
                result = chardet.detect(raw8k)
                guessed = result.get('encoding', 'utf-8') or 'utf-8'
                best_content = raw.decode(guessed, errors='replace')
                best_enc = guessed
            except:
                best_content = raw.decode('utf-8', errors='replace')
                best_enc = 'utf-8'
        return {"file_name": target.name, "size": len(best_content), "content": best_content, "encoding": best_enc}
    except Exception as e:
        return {"error": f"Read failed: {e}", "path": str(target)}

# ===== Health Check =====

import sys
sys.path.insert(0, '/opt/health-check')
_hc_instance = None
_hc_lock = threading.Lock()

def _get_hc(scan_root=None):
    global _hc_instance
    root = scan_root or "/data/originals"
    if _hc_instance is None or scan_root:
        from health_checker import HealthChecker
        _hc_instance = HealthChecker({"SCAN_ROOT": root, "OUTPUT_DIR": "/data/health-reports"})
    return _hc_instance

@app.get("/api/health-check/sources")
def health_check_sources():
    seen = set()
    paths = []
    try:
        import subprocess, os
        mount_info = {}
        for mp in ["/data/originals", "/data/output"]:
            if os.path.isdir(mp):
                try:
                    p = subprocess.run(["df", mp], capture_output=True, text=True, timeout=5)
                    info = p.stdout.split(chr(10))[1] if len(p.stdout.split(chr(10))) > 1 else ""
                    parts = info.split() if info else []
                    mount_info[mp] = parts[1] if len(parts) > 1 else None
                except:
                    mount_info[mp] = None
        seen.add("/data/originals")
        paths.append({"path": "/data/originals", "name": "默认源 (SMB)", "type": "default"})
        if "/data/output" in mount_info:
            seen.add("/data/output")
            paths.append({"path": "/data/output", "name": "输出目录 (NFS)", "type": "mount"})
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT name, path, source_type FROM doc_sources WHERE enabled=TRUE ORDER BY id")
        for r in cur.fetchall():
            if r[1] not in seen:
                seen.add(r[1])
                paths.append({"path": r[1], "name": r[0], "type": r[2] or "db"})
        cur.close(); conn.close()
    except:
        pass
    return paths


@app.get("/api/health-check/browse")
def health_check_browse(path: str = "/data/originals"):
    import os
    dirs = []
    try:
        if not os.path.isdir(path):
            return {"path": path, "dirs": []}
        with os.scandir(path) as it:
            for e in sorted(it, key=lambda x: x.name):
                if e.is_dir(follow_symlinks=False):
                    dirs.append({"name": e.name, "path": e.path})
    except:
        pass
    return {"path": path, "dirs": dirs}

@app.post("/api/health-check/start")
def health_check_start(scan_root: str = ""):
    hc = _get_hc(scan_root if scan_root else None)
    with _hc_lock:
        if hasattr(hc, '_thread') and hc._thread and hc._thread.is_alive():
            return {"status": "already_running"}
        import threading
        def _run():
            try:
                hc.reset()
                hc.run_scan()
                hc.run_checks()
                hc.export()
                hc.analyze()
            except Exception as e:
                print(f"Health check error: {e}")
        t = threading.Thread(target=_run, daemon=True)
        hc._thread = t
        t.start()
    return {"status": "started"}

@app.post("/api/health-check/stop")
def health_check_stop():
    hc = _get_hc()
    hc.cancel()
    return {"status": "stopped"}

@app.get("/api/health-check/status")
def health_check_status():
    hc = _get_hc()
    running = hasattr(hc, '_thread') and hc._thread and hc._thread.is_alive()
    return {
        "running": running,
        "scanned": len(hc.scanned_files),
        "checked": len(hc.check_results),
        "cancelled": hc.is_cancelled,
        "ai_ready": hc.ai_analysis is not None,
    }

@app.get("/api/health-check/results")
def health_check_results(page: int = 1, size: int = 50, status: str = ''):
    hc = _get_hc()
    results = hc.check_results
    if status:
        results = [r for r in results if r.get('status') == status]
    total = len(results)
    start = (page - 1) * size
    end = start + size
    return {"items": results[start:end], "total": total, "page": page, "size": size}

@app.get("/api/health-check/stats")
def health_check_stats():
    hc = _get_hc()
    results = hc.check_results
    if not results:
        return {"total": 0, "ok": 0, "warning": 0, "error": 0, "categories": {}}
    ok = sum(1 for r in results if r.get('status') == 'ok')
    warning = sum(1 for r in results if r.get('status') == 'warning')
    error = sum(1 for r in results if r.get('status') == 'error')
    cats = {}
    for r in results:
        cat = r.get('category', 'unknown')
        cats[cat] = cats.get(cat, 0) + 1
    return {"total": len(results), "ok": ok, "warning": warning, "error": error, "categories": cats}

@app.get("/api/health-check/results/export")
def health_check_export(fmt: str = 'csv'):
    hc = _get_hc()
    if not hc.check_results:
        raise HTTPException(400, "No results to export")
    out = hc.export()
    path = out.get(fmt) or out.get('csv')
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Export file not found")
    return FileResponse(path, filename=os.path.basename(path))

@app.get("/api/health-check/results/ai-analysis")
def health_check_ai_analysis():
    hc = _get_hc()
    if not hc.ai_analysis:
        raise HTTPException(404, "AI analysis not ready yet")
    return {"analysis": hc.ai_analysis}

# ===== Auth System =====

import hashlib, secrets

def hash_password(pw: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + pw).encode()).hexdigest()
    return salt + ':' + h

def verify_password(pw: str, stored: str) -> bool:
    salt, h = stored.split(':', 1)
    return hashlib.sha256((salt + pw).encode()).hexdigest() == h

@app.post("/api/auth/register")
def register(username: str = '', password: str = '', role: str = 'user'):
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=%s", (username,))
    if cur.fetchone():
        cur.close(); conn.close()
        raise HTTPException(409, "Username already exists")
    pw_hash = hash_password(password)
    cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s) RETURNING id",
                (username, pw_hash, role))
    uid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return {"id": uid, "username": username, "role": role}

@app.get("/api/auth/users")
def list_users():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, username, role, enabled, created_at FROM users ORDER BY id")
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"id": r[0], "username": r[1], "role": r[2], "enabled": r[3], "created_at": str(r[4]) if r[4] else None} for r in rows]

@app.post("/api/auth/login")
def login(username: str = '', password: str = ''):
    if not username or not password:
        raise HTTPException(400, "Username and password required")
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT password_hash, role FROM users WHERE username=%s AND enabled=TRUE", (username,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or not verify_password(password, row[0]):
        raise HTTPException(401, "Invalid credentials")
    token = jose_jwt.encode({"sub": username, "role": row[1], "iat": int(datetime.now().timestamp())}, JWT_SECRET, algorithm=JWT_ALGO)
    log_operation(username, 'login', details={"method": "password"})
    return {"access_token": token, "token_type": "bearer", "username": username, "role": row[1]}

@app.get("/api/auth/me")
def auth_me(request: Request):
    auth = request.headers.get('authorization', '')
    if not auth:
        raise HTTPException(401, "Not authenticated")
    try:
        token = auth.replace('Bearer ', '')
        payload = jose_jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        return {"username": payload.get('sub'), "role": payload.get('role'), "authenticated": True}
    except:
        raise HTTPException(401, "Invalid token")

@app.get("/api/oplog")
def get_oplog(limit: int = 50):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, user_name, action, target_type, target_id, details, created_at FROM operation_log ORDER BY id DESC LIMIT %s", (limit,))
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"id": r[0], "user": r[1], "action": r[2], "target_type": r[3], "target_id": r[4], "details": r[5], "time": str(r[6]) if r[6] else None} for r in rows]

@app.post("/api/organize/undo/{log_id}")
def undo_organize(log_id: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT before_state FROM operation_log WHERE id=%s AND action='organize'", (log_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        cur.close(); conn.close()
        raise HTTPException(404, "No undoable operation found")
    before = row[0]
    if isinstance(before, str): before = json.loads(before)
    for item in before.get('plan', []):
        old_path = item.get('old_path')
        new_path = item.get('new_path')
        if old_path and new_path:
            src = Path(new_path); dst = Path(old_path)
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.move(str(src), str(dst))
                cur.execute("UPDATE documents SET file_path=%s WHERE id=%s", (str(dst), item.get('id')))
    conn.commit(); cur.close(); conn.close()
    log_operation('system', 'undo', target_type='organize', target_id=log_id)
    return {"status": "undone", "log_id": log_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
