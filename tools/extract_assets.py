#!/usr/bin/env python3
"""Regenerate ssgold/assets from an original Sound Studio Gold installation.

Usage: python tools/extract_assets.py /path/to/gold   (folder holding Gold.exe, Goldlib.dll, BWCC.DLL)

Writes:
  bitmaps/<NAME>.png      every BITMAP resource, named from the NAMETABLE
  bwcc/<id>.png           Borland custom-control bitmaps from BWCC.DLL (buttons, checks, radios)
  icons/<NAME>.png        every icon (IC_*)
  cursors/<NAME>.cur/.xbm every cursor (CUR_*): Windows .cur, X11 .xbm + mask
  resources.json          menu, accelerators, dialogs, string table
  tables.json             display tables read from Goldlib.dll's data segment
  help.json               help topics decoded from Goldhelp.hlp
  patches/, drums/        the .PLS patch lists and .DRM drum kits
"""
import io
import json
import os
import shutil
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ne import NE, parse_menu, parse_dialog, parse_strings, parse_accel  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ssgold', 'assets')


def dib_to_image(d):
    hs = struct.unpack_from('<I', d, 0)[0]
    if hs == 40:
        _w, h, _pl, bpp, _comp, _, _, _, clr, _ = struct.unpack_from('<iiHHIIiiII', d, 4)
        ncol = clr or (1 << bpp if bpp <= 8 else 0)
        off = 14 + 40 + ncol * 4
    else:
        bpp = struct.unpack_from('<H', d, 10)[0]
        ncol = 1 << bpp if bpp <= 8 else 0
        off = 14 + 12 + ncol * 3
    bmp = b'BM' + struct.pack('<IHHI', 14 + len(d), 0, 0, off) + d
    im = Image.open(io.BytesIO(bmp))
    im.load()
    return im.convert('RGB')


def nametable(n):
    d = n.find(15)[0]['data']
    pos = 0
    names = {}
    while pos < len(d):
        sz, typ, rid = struct.unpack_from('<HHH', d, pos)
        if sz == 0:
            break
        names.setdefault(typ, {})[rid & 0x7FFF] = d[pos + 7:pos + sz].split(b'\0')[0].decode()
        pos += sz
    return names


def icon_image(d):
    """Win16 ICON resource (BITMAPINFOHEADER with XOR+AND masks, height doubled) -> RGBA."""
    w, h2, _pl, bpp = struct.unpack_from('<iiHH', d, 4)
    h = h2 // 2
    ncol = 1 << bpp
    pal = [(d[40 + 4 * i + 2], d[40 + 4 * i + 1], d[40 + 4 * i]) for i in range(ncol)]
    p = 40 + 4 * ncol
    xs = ((w * bpp + 31) // 32) * 4
    ms = ((w + 31) // 32) * 4
    xor = d[p:p + xs * h]
    andm = d[p + xs * h:p + xs * h + ms * h]
    im = Image.new('RGBA', (w, h))
    px = im.load()
    for y in range(h):
        row = xor[(h - 1 - y) * xs:]
        mrow = andm[(h - 1 - y) * ms:]
        for x in range(w):
            bit = x * bpp
            v = (row[bit // 8] >> (8 - bpp - bit % 8)) & (ncol - 1)
            transparent = (mrow[x // 8] >> (7 - x % 8)) & 1
            px[x, y] = pal[v] + ((0,) if transparent else (255,))
    return im


def write_cursor(d, base):
    """Win16 CURSOR resource (hotspot + 1bpp DIB with AND mask) -> .cur and .xbm/.xbm mask."""
    hx, hy = struct.unpack_from('<HH', d, 0)
    dib = d[4:]
    w, h2 = struct.unpack_from('<ii', dib, 4)
    h = h2 // 2
    p = 40 + 8
    stride = ((w + 31) // 32) * 4
    xor = dib[p:p + stride * h]
    andm = dib[p + stride * h:p + 2 * stride * h]
    # .cur file
    cur = struct.pack('<HHH', 0, 2, 1) + struct.pack('<BBBBHHII', w, h, 0, 0, hx, hy, len(dib), 22) + dib
    open(base + '.cur', 'wb').write(cur)
    # X11 bitmap pair: source = black pixels, mask = opaque pixels
    src, msk = [], []
    for y in range(h):
        r_x = xor[(h - 1 - y) * stride:]
        r_a = andm[(h - 1 - y) * stride:]
        for bx in range(w // 8):
            xb, ab = r_x[bx], r_a[bx]
            s = m = 0
            for i in range(8):
                xv = (xb >> (7 - i)) & 1
                av = (ab >> (7 - i)) & 1
                opaque = not av
                black = opaque and not xv
                if opaque or xv:
                    m |= 1 << i
                if black or (av and xv):
                    s |= 1 << i
            src.append(s)
            msk.append(m)
    name = os.path.basename(base).replace('-', '_')
    for suffix, data in (('', src), ('_mask', msk)):
        txt = '#define %s%s_width %d\n#define %s%s_height %d\n' % (name, suffix, w, name, suffix, h)
        if not suffix:
            txt += '#define %s_x_hot %d\n#define %s_y_hot %d\n' % (name, hx, name, hy)
        txt += 'static unsigned char %s%s_bits[] = {\n' % (name, suffix)
        txt += ',\n'.join(', '.join('0x%02x' % b for b in data[i:i + 12]) for i in range(0, len(data), 12))
        txt += '};\n'
        open(base + suffix + '.xbm', 'w').write(txt)
    return hx, hy


def dll_tables(path):
    n = NE(path)
    ds, _ = n.segment_data(struct.unpack_from('<H', n.data, n.ne + 0xE)[0])

    def strs(off, count):
        out = []
        for _ in range(count):
            e = ds.index(b'\0', off)
            out.append(ds[off:e].decode('latin1'))
            off = e + 1
        return out
    return {
        'timesig_num': list(ds[0x30af:0x30dc]),
        'timesig_den': list(ds[0x30dc:0x3109]),
        'key_names': strs(0x5f05, 12),
        'styles': strs(0x5e91, 16),
        'chord_types': strs(0x5f65, 12),
        'chord_suffixes': [''] + strs(0x12fb, 23),
        'chord_roots': strs(0x136c, 12),
        'controller_names': strs(0x4f54, 0),
        'gold_version': strs(0x5c8d, 1)[0],
        'xg_sysex': _xg_sysex(ds, strs),
    }


def _xg_sysex(ds, strs):
    """Event window 'Insert Type' sysex templates: names at 0x6128, 10-byte records at 0x5788."""
    names = strs(0x6128, 45)
    out = []
    for i, nm in enumerate(names):
        rec = ds[0x5788 + 10 * i:0x5788 + 10 * (i + 1)]
        body = rec[:rec.index(0xF7) + 1]
        out.append([nm, body.hex()])
    return out


def small_icon(im):
    """16x16 caption icon: from each 2x2 block keep the darkest opaque pixel so thin lines survive."""
    im = im.convert('RGBA')
    out = Image.new('RGBA', (im.width // 2, im.height // 2))
    for y in range(out.height):
        for x in range(out.width):
            block = [im.getpixel((2 * x + dx, 2 * y + dy)) for dy in (0, 1) for dx in (0, 1)]
            opaque = [p for p in block if p[3]]
            if len(opaque) < 2:
                out.putpixel((x, y), (0, 0, 0, 0))
                continue
            out.putpixel((x, y), min(opaque, key=lambda p: p[0] * 3 + p[1] * 6 + p[2]))
    return out


def main(src):
    exe = os.path.join(src, 'Gold.exe')
    n = NE(exe)
    names = nametable(n)
    for sub in ('bitmaps', 'icons', 'cursors', 'patches', 'drums'):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    for r in n.find('BITMAP'):
        dib_to_image(r['data']).save(os.path.join(OUT, 'bitmaps', names[2][r['id']] + '.png'))
    icons = {}
    for r in n.find('GROUP_ICON'):
        icon_id = struct.unpack_from('<H', r['data'], 6 + 12)[0]
        nm = names[14][r['id']]
        im = icon_image(n.get('ICON', icon_id))
        im.save(os.path.join(OUT, 'icons', nm + '.png'))
        small_icon(im).save(os.path.join(OUT, 'icons', nm + '_SM.png'))
        icons[nm] = r['id']
    cursors = {}
    for r in n.find('GROUP_CURSOR'):
        cid = struct.unpack_from('<H', r['data'], 6 + 12)[0]
        nm = names[12][r['id']]
        cursors[nm] = write_cursor(n.get('CURSOR', cid), os.path.join(OUT, 'cursors', nm))
    strings = {}
    for r in n.find('STRING'):
        strings.update(parse_strings(r['id'], r['data']))
    dialogs = {}
    for r in n.find('DIALOG'):
        dialogs[names[5][r['id']]] = parse_dialog(r['data'])
    res = {
        'menu': parse_menu(n.get('MENU', 1)),
        'accelerators': parse_accel(n.get('ACCELERATOR', 1)),
        'dialogs': dialogs,
        'strings': {str(k): v for k, v in sorted(strings.items())},
        'cursors': cursors,
    }
    json.dump(res, open(os.path.join(OUT, 'resources.json'), 'w'), indent=1)
    json.dump(dll_tables(os.path.join(src, 'Goldlib.dll')), open(os.path.join(OUT, 'tables.json'), 'w'), indent=1)
    bwcc = os.path.join(src, 'BWCC.DLL')
    if os.path.exists(bwcc):
        os.makedirs(os.path.join(OUT, 'bwcc'), exist_ok=True)
        for r in NE(bwcc).find('BITMAP'):
            dib_to_image(r['data']).save(os.path.join(OUT, 'bwcc', '%d.png' % r['id']))
    for f in os.listdir(src):
        ext = f.lower().rsplit('.', 1)[-1]
        if ext == 'pls':
            shutil.copy(os.path.join(src, f), os.path.join(OUT, 'patches', f.upper()))
        elif ext == 'drm':
            shutil.copy(os.path.join(src, f), os.path.join(OUT, 'drums', f.upper()))
    hlp = next((os.path.join(src, f) for f in os.listdir(src) if f.lower() == 'goldhelp.hlp'), None)
    if hlp:
        from winhelp import HLP
        topics = {}
        for title, paras in HLP(hlp).topics():
            if title and title not in topics:
                topics[title] = paras
        json.dump(topics, open(os.path.join(OUT, 'help.json'), 'w'), indent=0)
    print('assets written to', OUT)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
