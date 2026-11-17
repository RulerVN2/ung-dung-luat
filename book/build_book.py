#!/usr/bin/env python3
"""Dựng "sách điện tử" thành MỘT file HTML chạy offline từ các văn bản đã tách cấu trúc.

Dùng:
    python3 -I build_book.py <meta.json> <ra.html>

meta.json mô tả các văn bản đưa vào sách (xem meta.example.json). Đường dẫn trong meta.json
được tính từ thư mục chứa meta.json. File HTML đầu ra không gọi mạng và chặn mọi kết nối bằng CSP.
"""
import json
import os
import re
import sys
import unicodedata
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
from parse_structure import DIEU, to_int  # noqa: E402  (dùng chung bộ nhận diện tiêu đề Điều)


def nfc(x):
    """Chuẩn hóa mọi chuỗi về NFC để tìm kiếm không dấu hoạt động chính xác."""
    if isinstance(x, str):
        return unicodedata.normalize('NFC', x)
    if isinstance(x, list):
        return [nfc(i) for i in x]
    if isinstance(x, dict):
        return {k: nfc(v) for k, v in x.items()}
    return x


def article_pages(articles, pages):
    """Ước lượng trang bắt đầu của từng Điều rồi đánh dấu Điều nào có trang lấy từ OCR."""
    start = [None] * len(articles)
    j = 0
    for pg in pages:
        for line in pg['text'].splitlines():
            line = line.strip()
            if j >= len(articles):
                break
            m = DIEU.match(line)
            if m and m.group(1).translate(str.maketrans({'l': '1', 'I': '1', 'Ï': '1', '|': '1'})) == articles[j]['no']:
                start[j] = pg['page']
                j += 1
    last_page = pages[-1]['page'] if pages else 0
    src = {pg['page']: pg['source'] for pg in pages}
    flags = []
    for i, a in enumerate(articles):
        s = start[i]
        if s is None:
            flags.append(False)
            continue
        e = last_page
        for k in range(i + 1, len(articles)):
            if start[k] is not None:
                e = start[k]
                break
        flags.append(any(src.get(p) == 'ocr' for p in range(s, e + 1)))
    # trang bắt đầu của Điều cuối cùng được dò thấy: Phụ lục nằm sau đó
    first = next((s for s in reversed(start) if s is not None), None)
    tail_ocr = bool(first) and any(src.get(p) == 'ocr' for p in range(first, last_page + 1))
    return flags, tail_ocr


def build_doc(entry, base_dir):
    structure = json.load(open(os.path.join(base_dir, entry['structure']), encoding='utf-8'))
    pages = []
    if entry.get('pages'):
        pages = json.load(open(os.path.join(base_dir, entry['pages']), encoding='utf-8'))
    articles = structure['articles']
    flags, tail_ocr = article_pages(articles, pages) if pages else ([False] * len(articles), False)
    seen = {}
    out = []
    for a, ocr in zip(articles, flags):
        n = seen.get(a['no'], 0)
        seen[a['no']] = n + 1
        key = '%s/dieu-%s%s' % (entry['id'], a['no'], '' if n == 0 else '-b%d' % n)
        out.append({
            'key': key, 'no': a['no'], 'title': a['title'], 'intro': a['intro'],
            'clauses': a['clauses'], 'chapter': a['chapter'], 'section': a['section'], 'ocr': ocr,
            'lich_su': a.get('lich_su', []),
        })
    for i, ap in enumerate(structure.get('appendices', []), 1):
        out.append({
            'key': '%s/pl-%d' % (entry['id'], i), 'no': 'PL%d' % i, 'label': ap['label'], 'title': ap['title'],
            'intro': '', 'clauses': [{'no': '', 'text': t, 'points': []} for t in ap['paragraphs']],
            'chapter': 'PL', 'section': None, 'ocr': tail_ocr, 'appendix': True,
        })
    doc = {k: entry.get(k) for k in ('id', 'title', 'so_hieu', 'loai', 'ban_hanh', 'hieu_luc', 'co_quan',
                                      'tinh_trang', 'ghi_chu_hieu_luc')}
    doc['lien_quan'] = entry.get('lien_quan', [])
    doc['chapters'] = structure['chapters']
    doc['articles'] = out
    return doc


def main():
    meta_path, out_path = sys.argv[1], sys.argv[2]
    base_dir = os.path.dirname(os.path.abspath(meta_path))
    meta = json.load(open(meta_path, encoding='utf-8'))
    docs = [build_doc(e, base_dir) for e in meta['van_ban']]
    data = nfc({'docs': docs, 'cap_nhat_den': meta.get('cap_nhat_den') or date.today().strftime('%d/%m/%Y')})
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    blob = blob.replace('</', '<\\/').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    tpl = open(os.path.join(HERE, 'template.html'), encoding='utf-8').read()
    html = tpl.replace('__DATA__', blob)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    n_art = sum(len(d['articles']) for d in docs)
    n_ocr = sum(1 for d in docs for a in d['articles'] if a['ocr'])
    print('Đã dựng %s: %d văn bản, %d Điều (%d Điều có nội dung OCR), %.1f KB' % (
        out_path, len(docs), n_art, n_ocr, len(html.encode('utf-8')) / 1024))


if __name__ == '__main__':
    main()
