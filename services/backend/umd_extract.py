import sys

with open(sys.argv[1], 'rb') as f:
    raw = f.read()

result = []
i = 0
while i < len(raw) - 1:
    cp = raw[i] | (raw[i+1] << 8)
    if 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F:
        run = []
        for j in range(i, len(raw) - 1, 2):
            cp2 = raw[j] | (raw[j+1] << 8)
            if (0x4E00 <= cp2 <= 0x9FFF or 0x3000 <= cp2 <= 0x303F or
                0x0020 <= cp2 <= 0x007E or cp2 in (0x000A, 0x000D) or
                0x0080 <= cp2 <= 0x00FF or 0xFF00 <= cp2 <= 0xFFEF) and cp2 != 0:
                run.append(cp2)
            elif len(run) > 5:
                break
            else:
                run = []
                break
        if len(run) > 10:
            text = ''.join(chr(c) for c in run)
            result.append(text)
            i += len(run) * 2
            continue
    i += 1

full = '\n'.join(result)
print(f"Total chars: {len(full)}")
print(full[:5000])
