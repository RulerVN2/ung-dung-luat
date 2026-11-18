#!/usr/bin/env python3
"""Đọc văn bản SỬA ĐỔI và đề xuất chỗ cần sửa trong văn bản gốc để người dùng duyệt.

Dùng:
  python3 -I amend_propose.py propose <sua_doi.json> <goc.json> <de_xuat.json> [id_dieu_chua_lenh ...]
      Đọc các lệnh "Sửa đổi, bổ sung / Bãi bỏ / Thay thế cụm từ ..." trong Điều đầu tiên (hoặc các Điều chỉ định)
      của văn bản sửa đổi, tìm vị trí trong văn bản gốc, ghi danh sách đề xuất (mỗi đề xuất có trạng thái
      'tu_dong' hoặc 'xem_tay' kèm lý do).
  python3 -I amend_propose.py report <de_xuat.json> <bao_cao.html>
      Xuất báo cáo HTML để rà soát từng đề xuất (trước / sau).
  python3 -I amend_propose.py apply <goc.json> <de_xuat.json> <ids_duyet.json> <goc_moi.json>
      Áp dụng các đề xuất đã duyệt (danh sách id) vào bản sao của văn bản gốc, ghi lịch sử sửa đổi.

Nguyên tắc: công cụ KHÔNG tự quyết. Chỉ đề xuất khi tìm thấy vị trí chắc chắn; còn lại để 'xem_tay'.
"""
import copy
import html
import json
import re
import sys
import unicodedata

OPEN = '“„"'
CLOSE = '”"'
QUOTE = re.compile('[“„"]([^”"]*)[”"]')
TARGET = re.compile(r'(?:điểm\s+([a-zđ]\d?)\s+)?(?:khoản\s+(\d+)\s+)?(?:(?:tên|tiêu đề)\s+)?Điều\s+(\d+[a-z]?)', re.I)
LETTERS = 'abcdđeghiklmnopqrstuvxy'


def nrm(s):
    """Bỏ dấu, hạ chữ thường, GIỮ NGUYÊN độ dài chuỗi (để ánh xạ vị trí về chữ gốc)."""
    out = []
    for ch in s:
        d = unicodedata.normalize('NFD', ch)[:1].lower()
        out.append('d' if ch in 'đĐ' else (d if d else ch))
    return ''.join(out)


def find_phrase(text, phrase):
    """Tìm cụm từ (không phân biệt dấu/hoa thường/khoảng trắng). Trả về danh sách (đầu, cuối) trong text."""
    words = [w for w in re.split(r'\s+', nrm(phrase).strip()) if w]
    if not words:
        return []
    rx = re.compile(r'\s+'.join(re.escape(w) for w in words))
    return [m.span() for m in rx.finditer(nrm(text))]


# ---- nhận diện lệnh ---------------------------------------------------------------------------------
def quotes_of(text):
    q = [m.group(1).strip() for m in QUOTE.finditer(text)]
    return q


def tail_after_nhu_sau(text):
    m = re.search(r'như sau\s*:?\s*', text)
    if not m:
        return ''
    t = text[m.end():].strip()
    t = t.lstrip(OPEN).strip()
    t = re.sub(r'[”"]\s*[.;]?\s*$', '', t)
    return t


def parse_target(head, ctx):
    ms = list(TARGET.finditer(head))
    t = {'dieu': ctx.get('dieu'), 'khoan': None, 'diem': None}
    if ms:
        m = ms[-1]
        t = {'dieu': m.group(3), 'khoan': m.group(2), 'diem': m.group(1)}
    if re.search(r'Điều này', head):
        t['dieu'] = ctx.get('dieu')
        m = re.search(r'(?:điểm\s+([a-zđ]\d?)\s+)?khoản\s+(\d+)\s+Điều này', head)
        if m:
            t['khoan'], t['diem'] = m.group(2), m.group(1)
        else:
            m = re.search(r'điểm\s+([a-zđ]\d?)\s+Điều này', head)
            if m:
                t['diem'] = m.group(1)
    return t


def classify(text, ctx):
    """Trả về dict mô tả lệnh. loai: thay_cum | them_cum_sau | them_cum_truoc | bo_cum | bai_bo | them_cau_truc |
    sua_cau_truc | sua_ten | xem_tay"""
    head = text.split('như sau')[0] if 'như sau' in text else text
    qs = quotes_of(text)
    d = {'goc': text[:240]}
    if re.match(r'^(Thay thế|Thay)\s+cụm từ', text) and len(qs) >= 2:
        d.update(loai='thay_cum', cu=qs[0], moi=qs[1], dich=parse_target(text.split(qs[1])[-1] if qs[1] in text else text, ctx))
    elif re.match(r'^Bổ sung cụm từ', text) and len(qs) >= 2:
        pos = 'truoc' if re.search(r'vào trước', text) else 'sau'
        d.update(loai='them_cum_' + pos, moi=qs[0], moc=qs[1], dich=parse_target(text.split(qs[1])[-1] if qs[1] in text else text, ctx))
    elif re.match(r'^(Bỏ|Bãi bỏ)\s+cụm từ', text) and qs:
        d.update(loai='bo_cum', cu=qs[0], dich=parse_target(text.split(qs[0])[-1], ctx))
    elif re.match(r'^Bãi bỏ', text):
        d.update(loai='bai_bo', dich=parse_target(head, ctx), nhieu=bool(re.search(r',|\bvà\b', head)))
    elif re.match(r'^Bổ sung\s+(Điều|khoản|điểm)', text):
        body = tail_after_nhu_sau(text)
        d.update(loai='them_cau_truc', dich=parse_target(head.split('vào sau')[-1], ctx), moi=body, head=head)
    elif re.match(r'^Sửa đổi(, bổ sung)?\s+(tên|tiêu đề)\s+Điều', text):
        body = tail_after_nhu_sau(text)
        d.update(loai='sua_ten', dich=parse_target(head, ctx), moi=body)
    elif re.match(r'^Sửa đổi', text) and 'như sau' in text:
        body = tail_after_nhu_sau(text)
        nhieu = bool(re.search(r'(khoản|điểm)\s+\S+\s*(,|và)\s*(khoản|điểm)?\s*\S+\s+Điều|một số nội dung|định nghĩa', head))
        nhieu = nhieu or len(re.findall(r'khoản\s+\d', head)) > 1 or len(re.findall(r'điểm\s+[a-zđ]\b', head)) > 1
        d.update(loai='sua_cau_truc', dich=parse_target(head, ctx), moi=body, nhieu=nhieu, head=head)
    elif re.search(r'tên\s+(Mục|Chương)|\b(Mục|Chương)\s+\d+', text) and re.match(r'^(Thay|Bổ sung|Bỏ|Sửa)', text):
        d.update(loai='xem_tay', ly_do='Lệnh nhắm vào tên Mục/Chương, công cụ chưa xử lý')
    elif re.match(r'^Thay thế\s+Phụ lục', text):
        d.update(loai='xem_tay', ly_do='Thay thế Phụ lục: cần đưa Phụ lục mới vào thủ công')
    else:
        d.update(loai='xem_tay', ly_do='Chưa nhận diện được dạng câu lệnh')
    return d


def units(art):
    """Tách các đơn vị lệnh trong một Điều của văn bản sửa đổi."""
    out = []
    for c in art['clauses']:
        head = c['text']
        m = re.search(r'(?:Điều|khoản)\s+(\d+[a-z]?)\s+như sau', head)
        ctx_d = None
        mm = list(TARGET.finditer(head.split('như sau')[0]))
        if mm:
            ctx_d = mm[-1].group(3)
        ACT = re.compile(r'^(Sửa đổi|Bổ sung|Thay thế|Thay|Bỏ|Bãi bỏ)')
        if c['points'] and ACT.match(head) and 'như sau' in head and not QUOTE.search(head) \
                and all(ACT.match(p['text']) for p in c['points']):
            for p in c['points']:
                out.append(('%s.%s' % (c['no'], p['label']), p['text'], {'dieu': ctx_d}))
        else:
            out.append((c['no'], head + (' ' + ' '.join(p['label'] + ') ' + p['text'] for p in c['points']) if c['points'] else ''), {'dieu': ctx_d}))
    return out


# ---- tìm vị trí trong văn bản gốc -----------------------------------------------------------------------
def find_article(base, no):
    for a in base['articles']:
        if a['no'] == no:
            return a
    return None


def scope_fields(a, khoan, diem):
    """Danh sách trường chữ (nhãn, đối tượng, khóa) trong phạm vi Điều/khoản/điểm. Trả về (fields, ghi_chu)."""
    f, note = [], ''
    if khoan is None and diem is None:
        f.append(('Tên Điều', a, 'title'))
        if a['intro']:
            f.append(('Phần mở đầu', a, 'intro'))
        for c in a['clauses']:
            f.append(('Khoản %s' % c['no'], c, 'text'))
            for p in c['points']:
                f.append(('Khoản %s, điểm %s' % (c['no'], p['label']), p, 'text'))
        return f, note
    cl = [c for c in a['clauses'] if c['no'] == khoan] if khoan else a['clauses']
    if khoan and not cl:
        note = 'Không tách được Khoản %s trong văn bản gốc, tìm trong cả Điều' % khoan
        return scope_fields(a, None, None)[0], note
    for c in cl:
        if diem is None:
            f.append(('Khoản %s' % c['no'], c, 'text'))
        for p in c['points']:
            if diem is None or p['label'] == diem:
                f.append(('Khoản %s, điểm %s' % (c['no'], p['label']), p, 'text'))
    return f, note


def apply_phrase(op, base):
    a = find_article(base, op['dich']['dieu']) if op['dich'].get('dieu') else None
    if a is None:
        return None, 'Không có Điều %s trong văn bản gốc' % op['dich'].get('dieu')
    fields, note = scope_fields(a, op['dich'].get('khoan'), op['dich'].get('diem'))
    key = op.get('cu') or op.get('moc')
    changes = []
    for label, obj, k in fields:
        txt = obj[k]
        spans = find_phrase(txt, key)
        if not spans:
            continue
        new, last = [], 0
        for s, e in spans:
            new.append(txt[last:s])
            if op['loai'] == 'thay_cum':
                new.append(op['moi'])
            elif op['loai'] == 'bo_cum':
                pass
            elif op['loai'] == 'them_cum_sau':
                new.append(txt[s:e] + ' ' + op['moi'])
            else:
                new.append(op['moi'] + ' ' + txt[s:e])
            last = e
        new.append(txt[last:])
        changes.append({'vi_tri': label, 'truoc': txt, 'sau': ''.join(new).replace('  ', ' '), 'so_cho': len(spans)})
    if not changes:
        return None, 'Không tìm thấy cụm từ “%s” trong phạm vi chỉ định (có thể do OCR đọc sai)' % key
    return {'thay_doi': changes, 'ghi_chu': note}, None


def flat(a):
    parts = [a['title']] + ([a['intro']] if a['intro'] else [])
    for c in a['clauses']:
        parts.append('%s. %s' % (c['no'], c['text']))
        parts += ['%s) %s' % (p['label'], p['text']) for p in c['points']]
    return ' '.join(parts)


def split_title(head, old_title='', co_khoan=False):
    """Tách 'Tên Điều' khỏi phần nội dung dính liền phía sau (đoạn trích bị nối thành một dòng)."""
    head = head.strip()
    if old_title:
        ws = [w for w in re.split(r'\s+', nrm(old_title).strip()) if w]
        m = re.match(r'^\s*' + r'\s+'.join(re.escape(w) for w in ws), nrm(head)) if ws else None
        if m:
            # tên Điều không đổi (chỉ khác dấu do OCR): giữ tên cũ trong văn bản gốc
            return old_title.strip(), head[m.end():].strip()
    if co_khoan:  # có khoản 1. ngay sau tên: toàn bộ đoạn trước khoản là tên Điều
        return head, ''
    words = head.split()
    for i in range(3, len(words)):
        if words[i][:1].isupper() and words[i - 1][:1].islower() and not re.search(r'[,;:]$', words[i - 1]):
            return ' '.join(words[:i]), ' '.join(words[i:])
    return head, ''


def split_inline(text, old_title=''):
    """Tách đoạn trích 'Điều N. Tên ... 1. ... a) ...' (đã bị nối thành một dòng) thành Điều/Khoản/Điểm, theo dãy số."""
    text = text.strip()
    m = re.match(r'^Điều\s+(\d+[a-z]?)\s*[.,]\s*', text)
    if not m:  # rác OCR đứng trước chữ "Điều N."
        m2 = re.search(r'Điều\s+(\d+[a-z]?)\s*[.,]\s*', text[:40])
        if m2:
            text = text[m2.start():]
            m = re.match(r'^Điều\s+(\d+[a-z]?)\s*[.,]\s*', text)
    no = m.group(1) if m else None
    rest = text[m.end():] if m else text
    # tiêu đề: đến trước khoản "1." hoặc hết
    clauses, title, intro = [], rest, ''
    pos, n = [], 1
    for mm in re.finditer(r'(?:(?<=\s)|^)[„“"]?\s*(\d{1,2}|[lIÏ|])\s*[.,]\s+(?=\S)', rest):
        g = mm.group(1)
        if (int(g) if g.isdigit() else 1) == n:
            pos.append((mm.start(), mm.end(), n))
            n += 1
    if pos:
        title = rest[:pos[0][0]].strip()
        for i, (s, e, k) in enumerate(pos):
            body = rest[e:(pos[i + 1][0] if i + 1 < len(pos) else len(rest))].strip()
            clauses.append(_clause(k, body))
    title, intro = split_title(title, old_title, bool(clauses))
    return {'no': no, 'title': title.strip(), 'intro': intro, 'clauses': clauses}


def _clause(k, body):
    pts, i = [], 0
    marks = []
    for mm in re.finditer(r'(?:(?<=\s)|^)([a-zđ])\)\s+', body):
        exp = LETTERS[len(marks)] if len(marks) < len(LETTERS) else None
        if mm.group(1) == exp or (exp == 'đ' and mm.group(1) == 'd'):
            marks.append((mm.start(), mm.end(), exp))
    if not marks:
        return {'no': str(k), 'text': body, 'points': []}
    text = body[:marks[0][0]].strip()
    for j, (s, e, lb) in enumerate(marks):
        pts.append({'label': lb, 'text': body[e:(marks[j + 1][0] if j + 1 < len(marks) else len(body))].strip()})
    return {'no': str(k), 'text': text, 'points': pts}


def build_op(i, text, ctx, base, so_hieu):
    d = classify(text, ctx)
    d['id'] = i
    d['trang_thai'], d['ly_do'] = 'xem_tay', d.get('ly_do', '')
    loai = d['loai']
    if loai in ('thay_cum', 'them_cum_sau', 'them_cum_truoc', 'bo_cum'):
        res, err = apply_phrase(d, base)
        if res:
            d['de_xuat'] = res
            d['trang_thai'] = 'tu_dong'
            if any(c['so_cho'] > 1 for c in res['thay_doi']):
                d['ly_do'] = 'Cụm từ xuất hiện nhiều chỗ; nếu văn bản sửa đổi không nói "tất cả" thì chỉ nên sửa chỗ được chỉ định'
        else:
            d['ly_do'] = err
    elif loai == 'bai_bo':
        t = d['dich']
        a = find_article(base, t['dieu']) if t.get('dieu') else None
        if a is None:
            d['ly_do'] = 'Không có Điều %s trong văn bản gốc' % t.get('dieu')
        elif d.get('nhieu'):
            d['ly_do'] = 'Bãi bỏ nhiều vị trí trong một câu, cần xem tay'
        else:
            d['de_xuat'] = {'bai_bo': t, 'truoc': flat(a) if not t.get('khoan') else '', 'ghi_chu': ''}
            d['trang_thai'] = 'tu_dong'
    elif loai in ('sua_cau_truc', 'sua_ten', 'them_cau_truc'):
        t = d['dich']
        a = find_article(base, t['dieu']) if t.get('dieu') else None
        body = d.get('moi', '')
        if loai == 'them_cau_truc':
            if not body:
                d['ly_do'] = 'Không thấy nội dung trích dẫn của phần bổ sung'
            else:
                d['de_xuat'] = {'chen': t, 'noi_dung': body, 'vi_tri_chen': d.get('head', '')}
                d['trang_thai'] = 'tu_dong' if re.match(r'^Bổ sung\s+Điều', text) else 'xem_tay'
                if d['trang_thai'] == 'xem_tay':
                    d['ly_do'] = 'Bổ sung Khoản/Điểm: cần chọn đúng chỗ chèn'
        elif a is None:
            d['ly_do'] = 'Không có Điều %s trong văn bản gốc' % t.get('dieu')
        elif not body:
            d['ly_do'] = 'Không thấy nội dung trích dẫn (OCR có thể làm mất dấu ngoặc kép)'
        elif d.get('nhieu'):
            d['ly_do'] = 'Một lệnh sửa nhiều vị trí, cần xem tay'
        elif loai == 'sua_ten':
            d['de_xuat'] = {'sua_ten': t, 'truoc': a['title'], 'sau': re.sub(r'^Điều\s+\d+[a-z]?\s*[.,]\s*', '', body)}
            d['trang_thai'] = 'tu_dong'
        elif t.get('khoan') is None and t.get('diem') is None:
            d['de_xuat'] = {'thay_dieu': t, 'truoc': flat(a), 'sau': body, 'cau_truc_moi': split_inline(body, a['title'])}
            d['trang_thai'] = 'tu_dong'
        else:
            fields, note = scope_fields(a, t.get('khoan'), t.get('diem'))
            if len(fields) == 1 and not note:
                d['de_xuat'] = {'thay_muc': t, 'vi_tri': fields[0][0], 'truoc': fields[0][1][fields[0][2]], 'sau': body}
                d['trang_thai'] = 'tu_dong'
            else:
                d['ly_do'] = note or 'Không xác định được đúng một vị trí cần thay trong văn bản gốc'
                d['de_xuat'] = {'truoc': ' / '.join(f[1][f[2]][:120] for f in fields[:3]), 'sau': body}
    if d['trang_thai'] == 'xem_tay' and not d['ly_do']:
        d['ly_do'] = 'Cần xem tay'
    return d


def cmd_propose(src, base_path, out, only, ten=''):
    sua = json.load(open(src, encoding='utf-8'))
    base = json.load(open(base_path, encoding='utf-8'))
    ops = []
    for art in sua['articles']:
        if only and art['no'] not in only:
            continue
        if not re.match(r'^Sửa đổi|^Bổ sung|^Bãi bỏ', art['title']):
            continue
        for uid, text, ctx in units(art):
            ops.append(build_op('Đ%s.%s' % (art['no'], uid), text, ctx, base, ''))
    json.dump({'nguon': src, 'goc': base_path, 'ten_sua_doi': ten, 'de_xuat': ops}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tu = sum(1 for o in ops if o['trang_thai'] == 'tu_dong')
    print('Tổng số lệnh: %d | đề xuất được (tu_dong): %d | cần xem tay: %d' % (len(ops), tu, len(ops) - tu))


# ---- báo cáo ----------------------------------------------------------------------------------------
def esc(s):
    return html.escape(s or '')


def cmd_report(path, out):
    data = json.load(open(path, encoding='utf-8'))
    rows = []
    for o in data['de_xuat']:
        dp = o.get('de_xuat') or {}
        body = ''
        if 'thay_doi' in dp:
            for c in dp['thay_doi']:
                body += '<div class=c><b>%s</b><div class=b>%s</div><div class=a>%s</div></div>' % (esc(c['vi_tri']), esc(c['truoc']), esc(c['sau']))
        elif 'truoc' in dp or 'sau' in dp:
            body += '<div class=c><div class=b>%s</div><div class=a>%s</div></div>' % (esc(dp.get('truoc')), esc(dp.get('sau')))
        elif 'noi_dung' in dp:
            body += '<div class=c><b>Bổ sung mới</b><div class=a>%s</div></div>' % esc(dp['noi_dung'])
        elif 'bai_bo' in dp:
            body += '<div class=c><b>Bãi bỏ</b> %s</div>' % esc(json.dumps(dp['bai_bo'], ensure_ascii=False))
        t = o.get('dich') or {}
        tgt = ' · '.join(x for x in ['Điều %s' % t['dieu'] if t.get('dieu') else '', 'khoản %s' % t['khoan'] if t.get('khoan') else '', 'điểm %s' % t['diem'] if t.get('diem') else ''] if x)
        cls = 'ok' if o['trang_thai'] == 'tu_dong' else 'no'
        chk = ('<label class=k><input type=checkbox data-id="%s"> Duyệt</label>' % esc(o['id'])) if o['trang_thai'] == 'tu_dong' else ''
        rows.append('<section class=%s>' % cls + chk + '<h3>%s <small>%s · %s</small></h3><p class=g>%s</p>%s%s</section>' % (
            esc(o['id']), esc(o['loai']), esc(tgt), esc(o['goc']), body,
            ('<p class=w>%s</p>' % esc(o['ly_do'])) if o['ly_do'] else ''))
    doc = ('<!doctype html><meta charset=utf-8><title>Đề xuất cập nhật sửa đổi</title><style>'
           'body{font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin:20px auto;padding:0 16px;color:#222}'
           'section{border:1px solid #d8d3c4;border-radius:8px;padding:10px 14px;margin:10px 0}section.no{background:#fff7e0}'
           'h3{margin:0 0 4px;font-size:15px}small{color:#777;font-weight:400}.g{color:#555;margin:2px 0 6px}.w{color:#9a5b00;margin:6px 0 0}'
           '.c{margin:6px 0}.b{background:#fde8e8;padding:6px;border-radius:5px;margin:3px 0;white-space:pre-wrap}'
           '.a{background:#e6f4ea;padding:6px;border-radius:5px;white-space:pre-wrap}'
           '.k{float:right;font-weight:600;cursor:pointer}#bar{position:sticky;top:0;background:#fff;border-bottom:1px solid #d8d3c4;padding:8px 0;z-index:2}'
           'button{font:inherit;padding:6px 12px;border:1px solid #888;border-radius:6px;background:#f3f1e8;cursor:pointer}</style>'
           '<h1>Đề xuất cập nhật theo văn bản sửa đổi</h1><p>Đỏ: nội dung hiện có. Xanh: nội dung đề xuất. '
           'Khung vàng: cần xem tay. Chỉ tick "Duyệt" sau khi bạn đối chiếu bản gốc.</p>'
           '<div id=bar><span id=n>Đã duyệt: 0</span> &nbsp; <button id=all>Tick tất cả đề xuất</button> '
           '<button id=none>Bỏ tick hết</button> <button id=exp>Xuất danh sách đã duyệt (.json)</button></div>' + ''.join(rows) +
           '<script>(function(){var K="duyet:"+document.title+location.pathname;var cs=[].slice.call(document.querySelectorAll("input[data-id]"));'
           'var saved={};try{saved=JSON.parse(localStorage.getItem(K)||"{}")}catch(e){}'
           'function upd(){var o={};cs.forEach(function(c){if(c.checked)o[c.dataset.id]=1});try{localStorage.setItem(K,JSON.stringify(o))}catch(e){}'
           'document.getElementById("n").textContent="Đã duyệt: "+Object.keys(o).length+"/"+cs.length}'
           'cs.forEach(function(c){c.checked=!!saved[c.dataset.id];c.addEventListener("change",upd)});upd();'
           'document.getElementById("all").onclick=function(){cs.forEach(function(c){c.checked=true});upd()};'
           'document.getElementById("none").onclick=function(){cs.forEach(function(c){c.checked=false});upd()};'
           'document.getElementById("exp").onclick=function(){var ids=cs.filter(function(c){return c.checked}).map(function(c){return c.dataset.id});'
           'var a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(ids)],{type:"application/json"}));'
           'a.download="duyet.json";a.click()}})()</script>')
    open(out, 'w', encoding='utf-8').write(doc)
    print('Đã ghi', out)


# ---- áp dụng ----------------------------------------------------------------------------------------
def add_mark(obj, key, mark):
    """Gắn dấu 'được sửa đổi' vào đúng đoạn chữ để sổ tay tô vàng và hiện nội dung khi đưa chuột vào."""
    obj.setdefault(key, []).append(mark)


def head_of(text, n=300):
    h = text.split('như sau')[0].strip().rstrip(':') if 'như sau' in text else text
    return (h[:n] + '…') if len(h) > n else h


def cmd_apply(base_path, prop_path, ids_path, out):
    base = json.load(open(base_path, encoding='utf-8'))
    prop = json.load(open(prop_path, encoding='utf-8'))
    ids = set(json.load(open(ids_path, encoding='utf-8')))
    new = copy.deepcopy(base)
    done = 0
    for o in prop['de_xuat']:
        if o['id'] not in ids or o['trang_thai'] != 'tu_dong':
            continue
        dp = o['de_xuat']
        art = None
        if 'thay_doi' in dp:
            a = find_article(new, o['dich']['dieu'])
            fields, _ = scope_fields(a, o['dich'].get('khoan'), o['dich'].get('diem'))
            for c in dp['thay_doi']:
                for label, obj, k in fields:
                    if obj[k] == c['truoc']:
                        obj[k] = c['sau']
                        if o['loai'] == 'thay_cum':
                            mt, cum = 'Thay cụm từ “%s” bằng “%s”' % (o['cu'], o['moi']), o['moi']
                        elif o['loai'] == 'bo_cum':
                            mt, cum = 'Bỏ cụm từ “%s”' % o['cu'], None
                        else:
                            mt = 'Bổ sung cụm từ “%s” vào %s cụm từ “%s”' % (o['moi'], 'trước' if o['loai'] == 'them_cum_truoc' else 'sau', o['moc'])
                            cum = o['moi']
                        add_mark(obj, 'sd' if k == 'text' else 'sd_' + k, {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': mt, 'cum': cum})
            art = a
        elif 'thay_dieu' in dp:
            a = find_article(new, dp['thay_dieu']['dieu'])
            n = dp['cau_truc_moi']
            a['title'], a['intro'], a['clauses'] = n['title'], n['intro'], n['clauses']
            add_mark(a, 'sd_all', {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': head_of(o['goc']) + ' (toàn bộ Điều được thay bằng nội dung mới)', 'cum': None})
            art = a
        elif 'sua_ten' in dp:
            a = find_article(new, dp['sua_ten']['dieu'])
            a['title'] = dp['sau']
            add_mark(a, 'sd_title', {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': head_of(o['goc']), 'cum': None})
            art = a
        elif 'thay_muc' in dp:
            a = find_article(new, dp['thay_muc']['dieu'])
            fields, _ = scope_fields(a, dp['thay_muc'].get('khoan'), dp['thay_muc'].get('diem'))
            newtxt = dp['sau']
            tgt = fields[0][1]
            if 'label' in tgt:  # nhãn a), b)... đã có sẵn ở khung Điểm
                newtxt = re.sub(r'^\s*[a-zđ]\d?\)\s*', '', newtxt)
            elif 'no' in tgt:
                newtxt = re.sub(r'^\s*\d+\s*[.,]\s+', '', newtxt)
            tgt[fields[0][2]] = newtxt
            add_mark(fields[0][1], 'sd', {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': head_of(o['goc']), 'cum': None})
            art = a
        elif 'thay_khoan' in dp:
            t = dp['thay_khoan']
            a = find_article(new, t['dieu'])
            mo_ta = head_of(o['goc'])
            for nc in copy.deepcopy(t['cau_truc']):
                i = [j for j, c in enumerate(a['clauses']) if c['no'] == nc['no']][0]
                m = {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': mo_ta, 'cum': None}
                add_mark(nc, 'sd', m)
                for p_ in nc['points']:
                    add_mark(p_, 'sd', dict(m))
                a['clauses'][i] = nc
            art = a
        elif 'thay_diem' in dp:
            t = dp['thay_diem']
            a = find_article(new, t['dieu'])
            cl = [c for c in a['clauses'] if c['no'] == t['khoan']][0]
            pt_ = [p_ for p_ in cl['points'] if p_['label'] == t['diem']][0]
            pt_['text'] = dp['sau']
            add_mark(pt_, 'sd', {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': head_of(o['goc']), 'cum': None})
            art = a
        elif 'bai_bo' in dp:
            t = dp['bai_bo']
            a = find_article(new, t['dieu'])
            if t.get('khoan'):
                gone = [c for c in a['clauses'] if c['no'] == t['khoan']]
                a['clauses'] = [c for c in a['clauses'] if c['no'] != t['khoan']]
                add_mark(a, 'sd_bo', {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': 'Bãi bỏ khoản %s' % t['khoan'],
                                       'khoan': t['khoan'], 'truoc': gone[0]['text'] if gone else ''})
                art = a
            else:
                new['articles'] = [x for x in new['articles'] if x is not a]
        elif 'noi_dung' in dp and dp['chen'].get('dieu') and not dp['chen'].get('khoan'):
            n = split_inline(dp['noi_dung'])
            n.update(chapter=None, section=None)
            add_mark(n, 'sd_all', {'ten': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'mo_ta': head_of(o['goc']), 'cum': None})
            idx = max([i for i, x in enumerate(new['articles']) if x['no'] != n['no']] or [0])
            after = re.search(r'vào sau Điều\s+(\d+[a-z]?)', dp.get('vi_tri_chen', ''))
            if after:
                idx = [i for i, x in enumerate(new['articles']) if x['no'] == after.group(1)][0]
                n['chapter'], n['section'] = new['articles'][idx]['chapter'], new['articles'][idx]['section']
            new['articles'].insert(idx + 1, n)
            art = n
        if art is not None:
            entry = {'van_ban': prop.get('ten_sua_doi', ''), 'lenh': o['id'], 'goc': o['goc'][:160]}
            old = find_article(base, art['no'])
            if old is not None and not art.get('lich_su'):  # bản cũ: chỉ giữ một lần, trước lần sửa đầu tiên
                entry['ban_cu'] = {'title': old['title'], 'intro': old['intro'], 'clauses': copy.deepcopy(old['clauses'])}
            art.setdefault('lich_su', []).append(entry)
        done += 1
    json.dump(new, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('Đã áp dụng %d/%d đề xuất đã duyệt' % (done, len(ids)))


def main():
    a = sys.argv[1:]
    if len(a) >= 4 and a[0] == 'propose':
        ten = next((x[4:] for x in a[4:] if x.startswith('ten=')), '')
        cmd_propose(a[1], a[2], a[3], set(x for x in a[4:] if not x.startswith('ten=')), ten)
    elif len(a) == 3 and a[0] == 'report':
        cmd_report(a[1], a[2])
    elif len(a) == 5 and a[0] == 'apply':
        cmd_apply(a[1], a[2], a[3], a[4])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
