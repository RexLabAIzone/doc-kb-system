import psycopg2, json, os, httpx
from datetime import datetime
from elasticsearch import Elasticsearch

DB_URL = os.getenv('DB_URL', 'postgresql://docadmin:changeit@postgres:5432/docdb')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://ollama:11434')

def get_db():
    return psycopg2.connect(DB_URL)

def create_tables():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id SERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entity_relations (
            id SERIAL PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id INT NOT NULL REFERENCES entities(id),
            target_type TEXT NOT NULL,
            target_id INT NOT NULL REFERENCES entities(id),
            relation_type TEXT NOT NULL,
            weight FLOAT DEFAULT 1.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entity_relations_source ON entity_relations(source_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entity_relations_target ON entity_relations(target_id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_type_name ON entities(entity_type, name)")
    conn.commit(); cur.close(); conn.close()

def get_or_create_entity(cur, entity_type, name, metadata=None):
    cur.execute("SELECT id FROM entities WHERE entity_type=%s AND name=%s", (entity_type, name))
    row = cur.fetchone()
    if row:
        eid = row[0]
        if metadata:
            cur.execute("UPDATE entities SET metadata = metadata || %s WHERE id=%s", (json.dumps(metadata), eid))
        return eid
    cur.execute("INSERT INTO entities (entity_type, name, metadata) VALUES (%s, %s, %s) RETURNING id",
                (entity_type, name, json.dumps(metadata or {})))
    return cur.fetchone()[0]

def add_relation(cur, source_type, source_id, target_type, target_id, relation_type, weight=1.0):
    cur.execute("""
        INSERT INTO entity_relations (source_type, source_id, target_type, target_id, relation_type, weight)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (source_type, source_id, target_type, target_id, relation_type, weight))

def extract_entities_from_text(text, title=""):
    if not text or len(text.strip()) < 100:
        return {}
    chunk = text[:8000]
    try:
        httpx.post(OLLAMA_URL + "/api/generate",
                   json={"model": "qwen2.5:7b", "prompt": "hello", "stream": False, "options": {"num_predict": 1}},
                   timeout=120)
    except:
        pass
    prompt = """从以下文本中提取实体，只返回JSON格式（不要任何其他文字）：
{{
  "people": ["人名列表"],
  "places": ["地名列表"],
  "concepts": ["概念/主题词列表"],
  "series": ["系列名称"]
}}

文本：
{}""".format(chunk)
    try:
        resp = httpx.post(OLLAMA_URL + "/api/generate",
                          json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False, "options": {"num_predict": 512}},
                          timeout=180)
        data = resp.json()
        raw = data.get("response", "")
        raw = raw.strip()
        if raw.startswith("```json"): raw = raw[7:]
        if raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        print("  Ollama entity extraction error: {}".format(e))
        return {}

def process_document(doc_id, content_text, key_points=None, file_name=""):
    conn = get_db(); cur = conn.cursor()
    try:
        category = (key_points or {}).get("category", "")
        author = (key_points or {}).get("author", "")

        doc_entity_id = get_or_create_entity(cur, "document", file_name, {"doc_id": doc_id})
        if author:
            author_id = get_or_create_entity(cur, "author", author)
            add_relation(cur, "document", doc_entity_id, "author", author_id, "written_by", 1.0)
        if category:
            cat_id = get_or_create_entity(cur, "category", category)
            add_relation(cur, "document", doc_entity_id, "category", cat_id, "categorized_as", 1.0)

        entities = extract_entities_from_text(content_text, file_name)
        for etype, names in entities.items():
            if not names:
                continue
            map_type = {"people": "person", "places": "place", "concepts": "concept", "series": "series"}
            mapped = map_type.get(etype, etype)
            for name in names[:10]:
                name = name.strip()
                if not name or len(name) > 100:
                    continue
                eid = get_or_create_entity(cur, mapped, name)
                add_relation(cur, "document", doc_entity_id, mapped, eid, "mentions", 0.5)

        conn.commit()
    except Exception as e:
        print("  process_document error id={}: {}".format(doc_id, e))
        conn.rollback()
    finally:
        cur.close(); conn.close()

def process_all_classified(limit=500):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.content_text, d.file_name,
               c.category, c.key_points
        FROM documents d
        LEFT JOIN doc_categories c ON c.doc_id = d.id
        WHERE d.content_text IS NOT NULL AND length(d.content_text) > 100
        ORDER BY d.id LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    for i, (doc_id, text, fname, category, kp) in enumerate(rows):
        print("Processing {} ({}/{})".format(doc_id, i+1, len(rows)))
        kp_dict = kp if isinstance(kp, dict) else {}
        if category:
            kp_dict["category"] = category
        process_document(doc_id, text, kp_dict, fname or "")
    print("Done. Processed {} docs".format(len(rows)))

def build_similarity_relations():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.file_name FROM documents d
        WHERE EXISTS (SELECT 1 FROM doc_embeddings e WHERE e.doc_id = d.id)
        ORDER BY d.id
    """)
    doc_ids = [(r[0], r[1]) for r in cur.fetchall()]
    count = 0
    for doc_id, fname in doc_ids:
        try:
            cur.execute("SELECT embedding::text FROM doc_embeddings WHERE doc_id=%s", (doc_id,))
            row = cur.fetchone()
            if not row:
                continue
            vec_text = row[0]
            cur.execute("""
                SELECT e.doc_id, d.file_name,
                       1 - (e.embedding <=> %s::vector) AS score
                FROM doc_embeddings e
                JOIN documents d ON d.id = e.doc_id
                WHERE e.doc_id != %s
                ORDER BY e.embedding <=> %s::vector
                LIMIT 5
            """, (vec_text, doc_id, vec_text))
            similar = cur.fetchall()
            src_eid = get_or_create_entity(cur, "document", fname, {"doc_id": doc_id})
            for sim_id, sim_name, score in similar:
                if score and score > 0.5:
                    tgt_eid = get_or_create_entity(cur, "document", sim_name, {"doc_id": sim_id})
                    add_relation(cur, "document", src_eid, "document", tgt_eid, "similar", float(score))
            conn.commit()
            count += 1
        except Exception as e:
            conn.rollback()
            print("  similarity for {} error: {}".format(doc_id, e))
    cur.close(); conn.close()
    print("Built similarity relations for {} docs".format(count))

def get_graph_data(entity_types=None, limit=1000):
    conn = get_db(); cur = conn.cursor()
    where = ""
    params = [limit]
    if entity_types:
        placeholders = ",".join("%s" for _ in entity_types)
        where = "AND e.entity_type IN ({})".format(placeholders)
        params = entity_types + [limit]
    cur.execute("""
        SELECT e.id, e.entity_type, e.name, e.metadata
        FROM entities e WHERE 1=1 {} ORDER BY e.id LIMIT %s
    """.format(where), params)
    nodes = [{"id": r[0], "type": r[1], "name": r[2], "metadata": r[3]} for r in cur.fetchall()]
    node_ids = [n["id"] for n in nodes]
    if not node_ids:
        cur.close(); conn.close()
        return {"nodes": [], "links": []}
    placeholders = ",".join("%s" for _ in node_ids)
    cur.execute("""
        SELECT source_id, target_id, relation_type, weight
        FROM entity_relations
        WHERE source_id IN ({}) AND target_id IN ({})
        LIMIT %s
    """.format(placeholders, placeholders), node_ids + node_ids + [limit * 5])
    links = [{"source": r[0], "target": r[1], "type": r[2], "weight": r[3]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"nodes": nodes, "links": links}

def search_entities(query, entity_type=None, limit=50):
    conn = get_db(); cur = conn.cursor()
    if entity_type:
        cur.execute("SELECT id, entity_type, name, metadata FROM entities WHERE entity_type=%s AND name ILIKE %s LIMIT %s",
                    (entity_type, '%' + query + '%', limit))
    else:
        cur.execute("SELECT id, entity_type, name, metadata FROM entities WHERE name ILIKE %s LIMIT %s",
                    ('%' + query + '%', limit))
    rows = [{"id": r[0], "type": r[1], "name": r[2], "metadata": r[3]} for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows
