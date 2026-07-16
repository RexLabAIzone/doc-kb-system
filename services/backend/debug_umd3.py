with open('/tmp/人性的弱点.umd', 'rb') as f:
    raw = f.read()

print(f"Total size: {len(raw)}")

pos = 4
found_any = False
while pos < len(raw) - 5:
    marker = raw[pos]
    if marker == 0x23:
        category = raw[pos+1]
        unknown = raw[pos+2]
        length = raw[pos+3]
        content = raw[pos+4:pos+length]
        # Print first 50 blocks
        if found_any < 30:
            print(f"FUNC: pos={pos} cat=0x{category:02x} unk={unknown} len={length} content={repr(content[:16])}")
        found_any += 1
        pos += length
    elif marker == 0x24:
        rv = struct.unpack('<I', raw[pos+1:pos+5]) if len(raw) >= pos+9 else 0
        dblen = struct.unpack('<I', raw[pos+5:pos+9]) if len(raw) >= pos+9 else 0
        if found_any < 30:
            print(f"DATA: pos={pos} rv={rv} len={dblen}")
        found_any += 1
        if dblen:
            pos += dblen
        else:
            pos += 1
    else:
        if found_any < 10:
            print(f"SKIP: pos={pos} byte=0x{marker:02x}")
        pos += 1

print(f"\nTotal blocks: {found_any}")
print(f"Final pos: {pos} / {len(raw)}")