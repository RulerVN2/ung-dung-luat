#!/usr/bin/env python3
"""Tách cấu trúc văn bản pháp luật Việt Nam: Chương / Mục / Điều / Khoản / Điểm (bản 2).

Dùng: python3 -I parse_structure.py <input.txt> <output.json>

Khác bản 1:
- Chịu lỗi OCR: "l." / "I." / "Ï." đọc là "1."; "Điêu", "Điểu" vẫn nhận là Điều; "d)" thay "đ)".
- Dùng dãy số để xác nhận: Khoản chỉ được nhận khi đúng số kế tiếp, Điểm đúng chữ kế tiếp.
- Nội dung trong ngoặc kép “…” (trích dẫn nội dung sửa đổi) không bị tách thành Điều/Khoản giả,
  mà được giữ nguyên trong văn bản của Khoản đang đứng.
- Mọi chỗ nghi ngờ được ghi vào danh sách cảnh báo để người dùng rà soát.
"""
import json
import re
import sys

CHUONG = re.compile(r'^Chương\s+([IVXLCDMl1|Ï]+)\s*$')
MUC = re.compile(r'^Mục\s+(\d+|[lI|Ï]+)\s*$')
DIEU = re.compile(r'^Đi\S{0,3}\s+([0-9lIÏ|]{1,3}[a-z]?)\s*[.,]\s+(.+)$')
KHOAN = re.compile(r'^([0-9lIÏ|!]{1,3})\s*[.,]\s+(.*)$')
DIEM = re.compile(r'^([a-zđ])\)\s+(.*)$')
NOISE_LEAD = re.compile(r'^[.·•,;:~=>_|\s]+(?=[0-9A-Za-zÀ-ỹ“"])')
PAGE_NO = re.compile(r'^[-–—\s]*\d{1,3}[-–—\s]*$')
OPEN_Q = '“„«"'
CLOSE_Q = '”»"'
MAX_QUOTE_LINES = 60
LETTERS = 'abcdđeghiklmnopqrstuvxy'
DIGIT_FIX = str.maketrans({'l': '1', 'I': '1', 'Ï': '1', '|': '1', '!': '1', 'O': '0'})


def to_int(s):
    t = s.translate(DIGIT_FIX)
    return int(t) if t.isdigit() else None


def is_upper_title(line):
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def parse(lines):
    chapters, articles, warnings = [], [], []
    cur_chapter = cur_section = None
    art = clause = point = None
    pending = None
    title_open = False
    in_q = False  # đang ở trong đoạn trích dẫn nội dung sửa đổi
    q_lines = 0

    def append(text):
        if point is not None:
            point['text'] += ' ' + text
        elif clause is not None:
            clause['text'] += ' ' + text
        elif art is not None:
            art['intro'] = (art['intro'] + ' ' + text).strip()

    for raw in lines:
        line = NOISE_LEAD.sub('', raw.strip())  # bỏ ký tự rác OCR đầu dòng (.., ~, =, >)
        if not line or PAGE_NO.match(line):
            continue

        if in_q:
            hm = DIEU.match(line)
            nxt_no = (to_int(re.sub(r'[a-z]$', '', hm.group(1))) if hm else None)
            last_no = int(re.match(r'\d+', articles[-1]['no']).group()) if articles else 0
            if hm and nxt_no == last_no + 1:
                in_q = False  # cấu trúc thật tiếp tục: coi như trích dẫn đã kết thúc
            else:
                q_lines += 1
                if any(c in line for c in CLOSE_Q) or q_lines > MAX_QUOTE_LINES:
                    in_q = False
                if art is not None:
                    append(line)
                continue
        elif line[0] in OPEN_Q:
            if not any(c in line[1:] for c in CLOSE_Q):
                in_q = True
                q_lines = 0
            if art is not None:
                append(line)
            continue

        m = CHUONG.match(line)
        if m:
            cur_chapter = {'no': m.group(1), 'title': '', 'sections': []}
            chapters.append(cur_chapter)
            cur_section = None
            pending = ('chapter', cur_chapter)
            art = clause = point = None
            title_open = False
            continue
        m = MUC.match(line)
        if m and cur_chapter is not None:
            cur_section = {'no': m.group(1), 'title': ''}
            cur_chapter['sections'].append(cur_section)
            pending = ('section', cur_section)
            art = clause = point = None
            title_open = False
            continue
        if pending is not None:
            if is_upper_title(line):
                pending[1]['title'] = (pending[1]['title'] + ' ' + line).strip()
                continue
            pending = None

        m = DIEU.match(line)
        if m and to_int(re.sub(r'[a-z]$', '', m.group(1))) is not None:
            no = m.group(1).translate(DIGIT_FIX)
            art = {
                'no': no, 'title': m.group(2).strip(), 'intro': '', 'clauses': [],
                'chapter': cur_chapter['no'] if cur_chapter else None,
                'section': cur_section['no'] if cur_section else None,
            }
            articles.append(art)
            clause = point = None
            title_open = True
            continue
        if art is None:
            continue
        if title_open:
            if line[0].islower() and not DIEM.match(line):
                art['title'] += ' ' + line
                continue
            title_open = False

        m = KHOAN.match(line)
        if m:
            n = to_int(m.group(1))
            expected = len(art['clauses']) + 1
            if n is not None and n >= expected and n - expected <= 3:
                if n > expected:
                    warnings.append('Điều %s: thiếu Khoản %d đến %d (OCR có thể đã bỏ sót)' % (art['no'], expected, n - 1))
                clause = {'no': str(n), 'text': m.group(2).strip(), 'points': []}
                art['clauses'].append(clause)
                point = None
                continue
        m = DIEM.match(line)
        if m and clause is not None:
            ch = m.group(1)
            nxt = LETTERS[len(clause['points'])] if len(clause['points']) < len(LETTERS) else None
            if ch == nxt or (nxt == 'đ' and ch == 'd'):
                point = {'label': nxt, 'text': m.group(2).strip()}
                clause['points'].append(point)
                continue
        append(line)

    return chapters, articles, warnings


def check(articles, warnings):
    prev = 0
    seen = set()
    for a in articles:
        n = int(re.match(r'\d+', a['no']).group())
        if a['no'] in seen:
            warnings.append('Điều %s xuất hiện hai lần' % a['no'])
        seen.add(a['no'])
        if n != prev and n != prev + 1 and n > prev:
            warnings.append('Dãy Điều nhảy từ %d sang %s' % (prev, a['no']))
        prev = max(prev, n)
        if not a['clauses'] and len(a['intro']) < 40:
            warnings.append('Điều %s gần như trống (nội dung có thể bị mất)' % a['no'])
    return warnings


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding='utf-8') as f:
        lines = f.read().splitlines()
    chapters, articles, warnings = parse(lines)
    warnings = check(articles, warnings)
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump({'chapters': chapters, 'articles': articles, 'warnings': warnings}, f, ensure_ascii=False, indent=1)
    n_clauses = sum(len(a['clauses']) for a in articles)
    n_points = sum(len(c['points']) for a in articles for c in a['clauses'])
    print('Chương: %d | Điều: %d | Khoản: %d | Điểm: %d | Cảnh báo: %d' % (
        len(chapters), len(articles), n_clauses, n_points, len(warnings)))
    for w in warnings[:6]:
        print(' -', w)


if __name__ == '__main__':
    main()
