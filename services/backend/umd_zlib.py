import sys, zlib

with open(sys.argv[1], 'rb') as f:
    raw = f.read()

pos = 0
count = 0
while pos < len(raw) - 20:
    if raw[pos] == 0x78 and raw[pos+1] in (0x01, 0x5E, 0x9C, 0xDA):
        for length in range(20, min(100000, len(raw) - pos)):
            try:
                decompressed = zlib.decompress(raw[pos:pos+length])
                try:
                    text = decompressed.decode('utf-16-le', errors='replace')
                    cjk = sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF)
                    if cjk > 10:
                        count += 1
                        info = "pos={}, {} compressed -> {} decompressed, {} CJK chars"
                        print(info.format(pos, length, len(decompressed), cjk))
                        if count <= 3:
                            print("  text[:200]: " + repr(text[:200]))
                        break
                except:
                    pass
            except:
                continue
        if count > 5:
            break
    pos += 1

print("Found {} zlib streams with CJK content".format(count))
