import psycopg2, os
conn = psycopg2.connect(os.environ['DB_URL'])
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM documents")
total = cur.fetchone()[0]
print("Total documents: {}".format(total))

cur.execute("SELECT COUNT(*) FROM documents WHERE content_text IS NOT NULL AND content_text != ''")
with_text = cur.fetchone()[0]
print("With content_text: {}".format(with_text))

cur.execute("""
  SELECT file_ext, COUNT(*) FROM documents 
  WHERE content_text IS NOT NULL AND content_text != '' 
  GROUP BY file_ext ORDER BY COUNT(*) DESC
""")
print("\nBy extension (with content):")
for ext, cnt in cur.fetchall():
    print("  {}: {}".format(ext or '(none)', cnt))

cur.execute("""
  SELECT file_ext, COUNT(*) FROM documents 
  WHERE content_text IS NOT NULL AND content_text != '' 
  AND file_ext IN ('.pdf', '.mobi', '.epub', '.umd', '.azw3')
  GROUP BY file_ext
""")
print("\nBinary ebook formats with content (likely garbled):")
for ext, cnt in cur.fetchall():
    print("  {}: {}".format(ext, cnt))

# Find garbled .txt content (binary data or replacement chars)
cur.execute("""
  SELECT id, file_name, file_ext, LEFT(content_text, 120) FROM documents 
  WHERE content_text IS NOT NULL AND content_text != '' 
  AND file_ext IN ('.pdf', '.mobi', '.epub', '.umd')
  LIMIT 10
""")
print("\nSample garbage content from binary formats:")
for row in cur.fetchall():
    print("  id={} {}: {}".format(row[0], row[1], repr(row[3][:60])))

# Count txt files with replacement chars or binary-looking content
cur.execute("""
  SELECT COUNT(*) FROM documents 
  WHERE content_text IS NOT NULL AND content_text != ''
  AND file_ext = '.txt'
  AND (content_text ~ '\\x{fffd}' OR content_text ~ '\\x{0000}')
""")
garbled_txt = cur.fetchone()[0]
print("\n.txt with replacement chars or null bytes: {}".format(garbled_txt))

# Check for .txt files that start with binary markers
cur.execute("""
  SELECT COUNT(*) FROM documents 
  WHERE content_text IS NOT NULL AND content_text != ''
  AND file_ext = '.txt'
  AND (LEFT(content_text, 1) = '\\x00' OR content_text LIKE 'PK\\x03\\x04%' OR content_text LIKE '%PDF-%')
""")
binary_txt = cur.fetchone()[0]
print(".txt with binary content: {}".format(binary_txt))

conn.close()
