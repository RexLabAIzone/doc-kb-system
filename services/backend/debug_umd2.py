with open('/tmp/人性的弱点.umd', 'rb') as f:
    raw = f.read()

print(f"Total size: {len(raw)}")
print(f"Magic: {raw[:4].hex()}")

print("\nRaw hex first 200 bytes:")
for i in range(0, 200, 16):
    hex_str = ' '.join(f'{b:02x}' for b in raw[i:i+16])
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in raw[i:i+16])
    print(f"  {i:04x}: {hex_str:<48s} {ascii_str}")

print("\nAnalyzing all #-sections:")
pos = 0
count = 0
while pos < len(raw) and count < 30:
    if raw[pos] == 0x23:
        stype = raw[pos+1]
        len2 = int.from_bytes(raw[pos+2:pos+4], 'little')
        len2be = int.from_bytes(raw[pos+2:pos+4], 'big')
        len4 = int.from_bytes(raw[pos+2:pos+6], 'little')
        print(f"pos={pos} type=0x{stype:02x} len2LE={len2} len2BE={len2be} len4LE={len4} next={raw[pos+6:pos+10].hex()}")
        # Try with len4 as section length
        if len4 > 0 and len4 < len(raw) - pos:
            data = raw[pos+6:pos+6+len4]
            try:
                txt = data.decode('gbk', errors='replace')
                if any(0x4E00 <= ord(c) <= 0x9FFF for c in txt[:10]):
                    print(f"  -> GBK: {repr(txt[:60])}")
            except:
                pass
            try:
                txt = data.decode('utf-8', errors='replace')
                if any(0x4E00 <= ord(c) <= 0x9FFF for c in txt[:10]):
                    print(f"  -> UTF8: {repr(txt[:60])}")
            except:
                pass
        count += 1
        pos += 6 + len4
    else:
        pos += 1