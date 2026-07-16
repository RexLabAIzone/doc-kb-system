with open('/tmp/人性的弱点.umd', 'rb') as f:
    raw = f.read()

print(f"Total size: {len(raw)}")
print(f"Magic: {raw[:4].hex()}")

# Look for all sections by finding 0x23 markers
pos = 0
sections = []
last_type = None
while pos < len(raw) - 5:
    if raw[pos] == 0x23:
        stype = raw[pos+1]
        slen = int.from_bytes(raw[pos+2:pos+6], 'little')
        sections.append((pos, stype, slen))
        pos += 6 + slen
    else:
        pos += 1

print(f"\nFound {len(sections)} #-sections:")
for offset, stype, slen in sections[:30]:
    data_snippet = raw[offset+6:offset+6+min(slen, 40)]
    try:
        txt = data_snippet.decode('gbk', errors='replace')
    except:
        txt = repr(data_snippet)
    print(f"  off={offset} type=0x{stype:02x} len={slen} data={repr(txt)}")

# The data between sections might be the actual content
print("\n--- Looking for text content ---")
# Read data between two # markers
for i in range(len(sections)-1):
    start = sections[i][0] + 6 + sections[i][2]
    end = sections[i+1][0]
    if end > start:
        mid_data = raw[start:end]
        if len(mid_data) > 10:
            try:
                txt = mid_data.decode('gbk', errors='replace')
                if any(ord(c) > 0x4E00 for c in txt[:50]):
                    print(f"  gap[{i}]: off={start}-{end} len={len(mid_data)} text={repr(txt[:80])}")
            except:
                pass
