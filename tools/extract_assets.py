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


def style_tables(exe_path, dll_path):
    """The 16 accompaniment styles.

    Gold.exe passes Goldlib 20 far pointers into its own data segment (GOLDLIB.RECEIVE_SP, called
    from Gold.exe segment 2); the first argument is a table of 16 far pointers, one per style.
    A style record (offsets from its pointer P):
      P+0x00 far ptr  rhythm table: one byte per note, low 6 bits = duration index, 0x40 = tied
      P+0x04 far ptr  pitch table: 12 blocks (one per chord type, C root) of 'block size' notes
      P+0x08 8 far ptrs drum patterns: [steps, step duration index, one bitmask byte per step]
      P+0x28 time signature index, P+0x29 tempo
      P+0x2A 6 bytes: first note of Acc1..Acc4, Bass in the tables, then the block size
      P+0x31/38/3F/46/4D/54: 7 bytes each (unused, Acc1..Acc4, Bass, Drums) for program,
                             velocity code (velocity = code * 8 + 7), volume, pan, reverb, chorus
    Goldlib's data segment holds the Instant Chord Track progressions (17-byte rows of
    (root << 4 | chord type) bytes ended by 0xFF at 0x1A80), beats per chord (0x1A70) and the
    engine's constant tables.  All offsets are for Gold v4.00 / Goldlib v1.19.
    """
    exe = NE(exe_path)
    seg2, _ = exe.segment_data(2)
    assert seg2[0x0F:0x11] == b'\x1e\x68'      # push ds; push <table>  (first RECEIVE_SP argument)
    table = struct.unpack_from('<H', seg2, 0x11)[0]
    dseg = struct.unpack_from('<H', exe.data, exe.ne + 0xE)[0]
    d, rel = exe.segment_data(dseg)
    ptr = {off: t2 for st, fl, off, t1, t2 in rel if t1 == dseg and st == 3}
    lib = NE(dll_path)
    ds, _ = lib.segment_data(struct.unpack_from('<H', lib.data, lib.ne + 0xE)[0])
    names = dll_tables(dll_path)['styles']
    styles = []
    for i in range(16):
        P = ptr[table + 4 * i]
        parts = list(d[P + 0x2A:P + 0x30])
        bs = parts[5]
        rp, pp = ptr[P], ptr[P + 4]
        drums = []
        for k in range(8):
            q = ptr[P + 8 + 4 * k]
            drums.append({'steps': d[q], 'step': d[q + 1], 'hits': list(d[q + 2:q + 2 + d[q]])})
        prog = []
        for b in ds[0x1A80 + 17 * i:0x1A80 + 17 * (i + 1)]:
            if b == 0xFF:
                break
            prog.append([b >> 4, b & 15])
        styles.append({
            'name': names[i], 'timesig': d[P + 0x28], 'tempo': d[P + 0x29], 'parts': parts,
            'rhythm': list(d[rp:rp + bs]), 'pitches': [list(d[pp + bs * c:pp + bs * (c + 1)]) for c in range(12)],
            'drums': drums,
            'program': list(d[P + 0x32:P + 0x38]), 'velocity': list(d[P + 0x39:P + 0x3F]),
            'volume': list(d[P + 0x40:P + 0x46]), 'pan': list(d[P + 0x47:P + 0x4D]),
            'reverb': list(d[P + 0x4E:P + 0x54]), 'chorus': list(d[P + 0x55:P + 0x5B]),
            'progression': prog, 'beats': ds[0x1A70 + i],
        })
    engine = {
        'durations': list(struct.unpack_from('<18h', ds, 0x45CC)),
        'drum_notes': list(ds[0x45F0:0x4600]),
        'drum_velocity': list(ds[0x4600:0x4608]),
        'root_offset': list(struct.unpack('12b', ds[0x4610:0x461C])),
        'acc_channel': struct.unpack_from('<h', ds, 0x298C)[0],
        'drum_channel': struct.unpack_from('<h', ds, 0x2966)[0],
        'ict_bars': struct.unpack_from('<h', ds, 0x1A6E)[0], 'ict_max_bars': 200,
    }
    return {'engine': engine, 'styles': styles}


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
    json.dump(style_tables(exe, os.path.join(src, 'Goldlib.dll')), open(os.path.join(OUT, 'styles.json'), 'w'))
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
        from winhelp import HLP, rich_topics
        h = HLP(hlp)
        topics = {}
        used = set()
        for t in rich_topics(h):
            if not t['title'] or t['title'] in topics:
                continue
            paras = []
            for para in t['paras']:
                runs = []
                for txt, st in para:
                    st = {k: v for k, v in st.items() if v and not (k == 'color' and v in ('#000000', '#010100'))}
                    if 'bm' in st:
                        used.add(st['bm'])
                    if txt is not None:
                        txt = txt.encode('latin1').decode('cp1252', 'replace')
                    if runs and txt is not None and runs[-1][0] is not None and runs[-1][1] == st:
                        runs[-1][0] += txt
                    else:
                        runs.append([txt, st])
                paras.append(runs)
            topics[t['title']] = paras
        json.dump(topics, open(os.path.join(OUT, 'help.json'), 'w'), separators=(',', ':'))
        os.makedirs(os.path.join(OUT, 'help'), exist_ok=True)
        for n in sorted(used):
            imgs = h.images('|bm%d' % n) if '|bm%d' % n in h.files else []
            if imgs:
                imgs[0].save(os.path.join(OUT, 'help', 'bm%d.png' % n))
    print('assets written to', OUT)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
