#!/usr/bin/env python3
"""Sửa lỗi dấu thanh/dấu mũ do OCR dựa vào ngữ cảnh (cặp từ) học từ văn bản có lớp chữ sạch.

Cách làm: với mỗi âm tiết OCR, lấy các âm tiết trong kho có cùng chữ gốc (bỏ hết dấu), chọn âm tiết
khiến cặp từ với từ trước và từ sau phổ biến nhất. Chỉ đổi khi vượt ngưỡng tin cậy; không đổi số, mã hiệu,
từ viết tắt. Đây là bước hỗ trợ: các chỗ đã sửa được ghi lại để người dùng rà soát.

Dùng:
  python3 -I tone_fix.py build <kho.json> <file.pages.json> [...]   (chỉ dùng trang có lớp chữ)
  python3 -I tone_fix.py fix <kho.json> <vào.txt> <ra.txt> [nhật_ký.json]
"""
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict

WORD = re.compile(r'[^\W\d_]+', re.UNICODE)
THRESH = 5.0  # ngưỡng chênh lệch điểm (log) để chịu đổi khi từ OCR có trong kho
THRESH_UNSEEN = 1.0  # ngưỡng thấp hơn khi từ OCR chưa từng xuất hiện trong kho (khả năng cao là lỗi)


def base(w):
    s = unicodedata.normalize('NFD', w.lower().replace('đ', 'd'))
    return ''.join(c for c in s if not unicodedata.combining(c))


def tokens(text):
    return [m.group().lower() for m in WORD.finditer(text)]


def build(page_files, exclude=None):
    uni, bi = Counter(), Counter()
    exclude = exclude or {}
    for path in page_files:
        pages = json.load(open(path, encoding='utf-8'))
        skip = exclude.get(path, set())
        for pg in pages:
            if pg['source'] != 'text' or pg['page'] in skip:
                continue
            for line in pg['text'].splitlines():
                t = tokens(line)
                uni.update(t)
                bi.update(zip(t, t[1:]))
    variants = defaultdict(list)
    for w, c in uni.items():
        variants[base(w)].append((w, c))
    return {'uni': dict(uni), 'bi': {a + ' ' + b: c for (a, b), c in bi.items() if c >= 1}, 'total': sum(uni.values())}


def score(lex, prev, w, nxt):
    uni, bi = lex['uni'], lex['bi']
    cw = uni.get(w, 0)
    s = 0.3 * math.log(cw + 1)
    if prev:
        s += math.log((bi.get(prev + ' ' + w, 0) + 0.05) / (uni.get(prev, 0) + 1))
    if nxt:
        s += math.log((bi.get(w + ' ' + nxt, 0) + 0.05) / (cw + 1))
    return s


def make_index(lex):
    idx = defaultdict(list)
    for w in lex['uni']:
        idx[base(w)].append(w)
    return idx


def fix_text(text, lex, idx=None, log=None):
    idx = idx or make_index(lex)
    out, pos = [], 0
    for line in text.split('\n'):
        ms = list(WORD.finditer(line))
        words = [m.group().lower() for m in ms]
        res, last = [], 0
        for i, m in enumerate(ms):
            orig = m.group()
            low = words[i]
            res.append(line[last:m.start()])
            last = m.end()
            new = orig
            if len(low) >= 2 and not any(c.isdigit() for c in line[max(0, m.start() - 1):m.end() + 1]):
                cands = idx.get(base(low), [])
                if len(cands) > 1 or (cands and cands[0] != low):
                    prev = words[i - 1] if i > 0 else None
                    nxt = words[i + 1] if i + 1 < len(words) else None
                    s0 = score(lex, prev, low, nxt)
                    best, sb = low, s0
                    for c in cands:
                        sc = score(lex, prev, c, nxt)
                        if sc > sb:
                            best, sb = c, sc
                    if best != low and sb - s0 >= (THRESH if lex['uni'].get(low, 0) else THRESH_UNSEEN):
                        if orig.isupper() and len(orig) > 1:
                            new = best.upper()
                        elif orig[0].isupper():
                            new = best[0].upper() + best[1:]
                        else:
                            new = best
                        if log is not None:
                            log.append({'từ_ocr': orig, 'sửa_thành': new, 'ngữ_cảnh': ' '.join(words[max(0, i - 2):i + 3])})
            res.append(new)
        res.append(line[last:])
        out.append(''.join(res))
    return '\n'.join(out)


def main():
    cmd = sys.argv[1]
    if cmd == 'build':
        lex = build(sys.argv[3:])
        json.dump(lex, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False)
        print('Kho: %d âm tiết khác nhau, %d cặp từ, %d từ' % (len(lex['uni']), len(lex['bi']), lex['total']))
    elif cmd == 'fixdoc':
        lex = json.load(open(sys.argv[2], encoding='utf-8'))
        idx = make_index(lex)
        pages = json.load(open(sys.argv[3], encoding='utf-8'))
        log, parts = [], []
        for pg in pages:
            if pg['source'] == 'ocr':
                before = len(log)
                parts.append(fix_text(pg['text'], lex, idx, log))
                for e in log[before:]:
                    e['trang'] = pg['page']
            else:
                parts.append(pg['text'])
        open(sys.argv[4], 'w', encoding='utf-8').write('\n'.join(parts))
        json.dump(log, open(sys.argv[5], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('%s: đã sửa %d từ' % (sys.argv[3].split('/')[-1], len(log)))
    elif cmd == 'fix':
        lex = json.load(open(sys.argv[2], encoding='utf-8'))
        text = open(sys.argv[3], encoding='utf-8').read()
        log = []
        fixed = fix_text(text, lex, log=log)
        open(sys.argv[4], 'w', encoding='utf-8').write(fixed)
        if len(sys.argv) > 5:
            json.dump(log, open(sys.argv[5], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('Đã sửa %d từ' % len(log))


if __name__ == '__main__':
    main()
