import sys, re

with open(sys.argv[1], 'rb') as f:
    raw = f.read()

# Extract all valid UTF-16-LE strings of reasonable length
result = []
i = 0
while i < len(raw) - 20:
    # Try to decode as UTF-16-LE starting at position i
    try:
        decoded = raw[i:i+200].decode('utf-16-le')
        # Check if contains CJK chars
        cjk_count = sum(1 for c in decoded if 0x4E00 <= ord(c) <= 0x9FFF)
        ascii_count = sum(1 for c in decoded if 0x20 <= ord(c) <= 0x7E or ord(c) in (0x0A, 0x0D))
        total_len = len(decoded)
        # If at least 30% CJK chars and total length > 10
        if cjk_count > 5 and total_len > 15 and cjk_count + ascii_count > total_len * 0.5:
            result.append(decoded)
            i += len(decoded.encode('utf-16-le'))
            continue
    except:
        pass
    i += 1

full = '\n'.join(result)
full = full.replace('\u2029', '\n')

print(full)
