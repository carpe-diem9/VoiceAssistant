"""生成简易占位 PNG 图标（无需 Pillow，纯 stdlib）"""
import struct
import zlib
import os

os.makedirs('public/icons', exist_ok=True)


def make_png(size: int, color=(64, 120, 255, 255)) -> bytes:
    """生成纯色 PNG 字节流"""
    r, g, b, a = color
    # 每行: filter byte (0) + size 个 RGBA 像素
    row = bytes([0]) + bytes([r, g, b, a]) * size
    raw = row * size
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack('>I', len(data))
            + tag
            + data
            + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
        )

    signature = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)  # RGBA
    return signature + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')


for s in (16, 48, 128):
    with open(f'public/icons/icon{s}.png', 'wb') as f:
        f.write(make_png(s))
    print(f'icon{s}.png ok')
