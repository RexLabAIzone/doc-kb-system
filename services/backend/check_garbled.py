import psycopg2, os
conn = psycopg2.connect(os.environ['DB_URL'])
cur = conn.cursor()
ff = chr(65533)
cur.execute("""
  SELECT COUNT(*) FROM documents
  WHERE content_text IS NOT NULL AND content_text != ''
  AND (content_text LIKE '%%' || %s || '%%' OR content_text LIKE '%%PDF-%%' OR content_text LIKE '%%PK%%' OR content_text LIKE '%%BOOKMOBI%%')
""", (ff,))
print('Garbled count:', cur.fetchone()[0])
cur.execute("""
  SELECT id, file_name, LEFT(content_text, 80) FROM documents
  WHERE content_text IS NOT NULL AND content_text != ''
  AND (content_text LIKE '%%' || %s || '%%' OR content_text LIKE '%%PDF-%%' OR content_text LIKE '%%PK%%' OR content_text LIKE '%%BOOKMOBI%%')
  LIMIT 5
""", (ff,))
for r in cur.fetchall():
    print('id={} {}: {}'.format(r[0], r[1], repr(r[2])))
cur.close(); conn.close()
