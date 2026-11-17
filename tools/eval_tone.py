#!/usr/bin/env python3
"""Kiểm thử bộ sửa dấu: OCR lại các trang có lớp chữ (đáp án chuẩn), so sánh trước và sau khi sửa.

Dùng: python3 -I eval_tone.py <luat.pdf> <thư_mục_out> <tessdata> <trang_đầu> <trang_cuối> [degrade]
Kho từ được dựng KHÔNG gồm các trang kiểm thử.
"""
import difflib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tone_fix  # noqa: E402


def ocr(pdf, p, tessdir, degrade):
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, 'pg')
        subprocess.run(['pdftoppm', '-f', str(p), '-l', str(p), '-r', '300', '-gray', '-png', '-singlefile', pdf, base], check=True)
        src = base + '.png'
        out = base + '_c.png'
        cmd = ['convert', src, '-gravity', 'East', '-chop', '120x0']
        if degrade:  # mô phỏng bản scan: mờ nhẹ, nhiễu, nén JPEG
            cmd += ['-blur', '0x0.9', '-attenuate', '0.35', '+noise', 'Gaussian', '-quality', '55']
            out = base + '_c.jpg'
        subprocess.run(cmd + [out], check=True)
        subprocess.run(['tesseract', out, base, '--tessdata-dir', tessdir, '-l', 'vie', '--psm', '6'], capture_output=True)
        return open(base + '.txt', encoding='utf-8').read()


def words(text):
    return [m.group() for m in tone_fix.WORD.finditer(text)]


def wer(gt, hyp):
    sm = difflib.SequenceMatcher(None, gt, hyp, autojunk=False)
    same = sum(b.size for b in sm.get_matching_blocks())
    return 1 - same / max(1, len(gt)), len(gt) - same


def main():
    pdf, outdir, tessdir, a, b = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
    degrade = len(sys.argv) > 6
    pages_json = os.path.join(outdir, 'doc09.pages.json')
    excl = {pages_json: set(range(a, b + 1))}
    files = [os.path.join(outdir, 'doc%s.pages.json' % n) for n in ('07', '13', '08', '09')]
    if os.environ.get('TF_THRESH'):
        tone_fix.THRESH = float(os.environ['TF_THRESH'])
    if os.environ.get('TF_UNSEEN'):
        tone_fix.THRESH_UNSEEN = float(os.environ['TF_UNSEEN'])
    lex = tone_fix.build(files, exclude=excl)
    idx = tone_fix.make_index(lex)
    gt_pages = {pg['page']: pg['text'] for pg in json.load(open(pages_json, encoding='utf-8'))}
    tot_gt = tot_err0 = tot_err1 = 0
    changes_good = changes_bad = 0
    for p in range(a, b + 1):
        gt = words(gt_pages[p])
        cache = os.path.join(outdir, 'eval_raw_%d_%s.txt' % (p, 'd' if degrade else 'c'))
        if os.path.exists(cache):
            raw = open(cache, encoding='utf-8').read()
        else:
            raw = ocr(pdf, p, tessdir, degrade)
            open(cache, 'w', encoding='utf-8').write(raw)
        log = []
        fixed = tone_fix.fix_text(raw, lex, idx, log)
        _, e0 = wer(gt, words(raw))
        _, e1 = wer(gt, words(fixed))
        tot_gt += len(gt)
        tot_err0 += e0
        tot_err1 += e1
    print('Trang %d-%d (%s): %d từ chuẩn | lỗi trước sửa: %d (%.1f%%) | sau sửa: %d (%.1f%%)' % (
        a, b, 'giả lập scan' if degrade else 'ảnh sạch', tot_gt, tot_err0, 100 * tot_err0 / tot_gt, tot_err1, 100 * tot_err1 / tot_gt))


if __name__ == '__main__':
    main()
