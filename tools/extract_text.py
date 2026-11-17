#!/usr/bin/env python3
"""Lấy chữ từng trang của một PDF: dùng lớp chữ nếu có, nếu không thì OCR (tiếng Việt).

Dùng: python3 -I extract_text.py <file.pdf> <thư_mục_ra> <tên_ngắn> [thư_mục_mô_hình_tessdata]
Ra: <tên_ngắn>.pages.json  (từng trang: số trang, nguồn 'text'|'ocr', nội dung)
    <tên_ngắn>.txt         (nội dung nối lại, để đưa vào bộ tách cấu trúc)
"""
import json
import os
import subprocess
import sys
import tempfile
from multiprocessing import Pool

MIN_CHARS = 80
CROP_RIGHT = 120  # px ở 300 dpi: cắt lề phải để bỏ hình mờ của trang nguồn


def page_count(pdf):
    out = subprocess.run(['pdfinfo', pdf], capture_output=True).stdout.decode('utf-8', 'replace')
    for line in out.splitlines():
        if line.startswith('Pages:'):
            return int(line.split()[1])
    raise SystemExit('Không đọc được số trang')


def text_layer(pdf, p):
    r = subprocess.run(['pdftotext', '-f', str(p), '-l', str(p), pdf, '-'], capture_output=True)
    return r.stdout.decode('utf-8', 'replace')


def ocr_page(args):
    pdf, p, tessdir = args
    txt = text_layer(pdf, p)
    if len(''.join(txt.split())) >= MIN_CHARS:
        return {'page': p, 'source': 'text', 'text': txt}
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, 'pg')
        subprocess.run(['pdftoppm', '-f', str(p), '-l', str(p), '-r', '300', '-gray', '-png', '-singlefile', pdf, base],
                       check=True, capture_output=True)
        png = base + '.png'
        crop = base + '_c.png'
        subprocess.run(['convert', png, '-gravity', 'East', '-chop', '%dx0' % CROP_RIGHT, crop],
                       check=True, capture_output=True)
        cmd = ['tesseract', crop, base, '-l', 'vie', '--psm', '6']
        if tessdir:
            cmd[3:3] = ['--tessdata-dir', tessdir]
        subprocess.run(cmd, capture_output=True)
        out = base + '.txt'
        text = open(out, encoding='utf-8').read() if os.path.exists(out) else ''
    return {'page': p, 'source': 'ocr', 'text': text}


def main():
    pdf, outdir, name = sys.argv[1], sys.argv[2], sys.argv[3]
    tessdir = sys.argv[4] if len(sys.argv) > 4 else None
    os.makedirs(outdir, exist_ok=True)
    n = page_count(pdf)
    with Pool(max(1, (os.cpu_count() or 2))) as pool:
        pages = pool.map(ocr_page, [(pdf, p, tessdir) for p in range(1, n + 1)])
    with open(os.path.join(outdir, name + '.pages.json'), 'w', encoding='utf-8') as f:
        json.dump(pages, f, ensure_ascii=False)
    with open(os.path.join(outdir, name + '.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(pg['text'] for pg in pages))
    n_ocr = sum(1 for pg in pages if pg['source'] == 'ocr')
    print('%s: %d trang, trong đó %d trang OCR' % (name, n, n_ocr))


if __name__ == '__main__':
    main()
