import struct
import zlib

def extract_text_from_umd(path: str) -> str:
    with open(path, 'rb') as f:
        raw = f.read()

    if len(raw) < 4 or raw[:4] != b'\x89\x9b\x9a\xde':
        raise ValueError("Not a valid UMD file")

    pos = 4
    text_parts = []

    while pos < len(raw) - 9:
        if raw[pos] == 0x24:  # data block
            rv = struct.unpack('<I', raw[pos+1:pos+5])[0]
            blen = struct.unpack('<I', raw[pos+5:pos+9])[0]
            if blen < 12 or blen > len(raw) - pos:
                pos += 1
                continue
            content = raw[pos+9:pos+blen]
            try:
                decompressed = zlib.decompress(content)
                try:
                    text = decompressed.decode('utf-16-le', errors='replace')
                    if sum(1 for c in text if 0x4E00 <= ord(c) <= 0x9FFF) > 10:
                        text_parts.append(text.replace('\u2029', '\n'))
                except:
                    pass
            except:
                pass
            pos += blen
        else:
            pos += 1

    result = ''.join(text_parts)

    # Remove null chars and fix common issues
    result = result.replace('\x00', '')

    return result


if __name__ == '__main__':
    import sys
    text = extract_text_from_umd(sys.argv[1])
    print("Extracted {} chars".format(len(text)))
    print(text[:3000])
