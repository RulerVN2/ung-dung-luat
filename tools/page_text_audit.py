#!/usr/bin/env python3
"""Thống kê từng PDF: bao nhiêu trang có lớp chữ, bao nhiêu trang là ảnh (cần OCR).

Dùng: python3 -I page_text_audit.py <thư_mục_chứa_pdf>
"""
import os
import subprocess
import sys

MIN_CHARS = 80  # dưới ngưỡng này coi như trang không có chữ


def pages_text(path):
    out = subprocess.run(['pdftotext', path, '-'], capture_output=True).stdout.decode('utf-8', 'replace')
    pages = out.split('\f')
    if pages and pages[-1] == '':
        pages.pop()
    return [len(''.join(p.split())) for p in pages]


def main():
    folder = sys.argv[1]
    total_text = total_img = 0
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith('.pdf'):
            continue
        counts = pages_text(os.path.join(folder, name))
        img = [i + 1 for i, c in enumerate(counts) if c < MIN_CHARS]
        total_text += len(counts) - len(img)
        total_img += len(img)
        if not img:
            kind = 'toàn bộ có chữ'
        elif len(img) == len(counts):
            kind = 'toàn bộ là ảnh'
        else:
            head = ', '.join(map(str, img[:8])) + (' ...' if len(img) > 8 else '')
            kind = 'HỖN HỢP, trang ảnh: ' + head
        print('%3d trang | %3d ảnh | %s | %s' % (len(counts), len(img), kind, name[:48]))
    print('TỔNG: %d trang có chữ, %d trang ảnh cần OCR' % (total_text, total_img))


if __name__ == '__main__':
    main()
