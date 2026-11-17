# Sổ tay Luật Điện lực

Bộ công cụ biến các văn bản pháp luật về điện lực (PDF, kể cả bản scan) thành **một file HTML duy nhất**
để tra cứu offline: mục lục theo Chương/Điều, tìm kiếm toàn văn không phân biệt dấu, đánh dấu và ghi chú
cá nhân, hiển thị tình trạng hiệu lực.

Repo này **chỉ chứa mã nguồn**. Không đưa PDF hay văn bản đã tách lên đây (xem `.gitignore`).

## Cách hoạt động

```
PDF  ->  chữ từng trang  ->  sửa lỗi dấu  ->  tách Chương/Điều/Khoản  ->  file HTML
        (lớp chữ hoặc OCR)   (tone_fix)       (parse_structure)          (build_book)
```

| Thư mục | Nội dung |
|---|---|
| `tools/page_text_audit.py` | Thống kê từng PDF: trang nào có chữ, trang nào là ảnh |
| `tools/extract_text.py` | Lấy chữ từng trang; trang ảnh thì OCR tiếng Việt (có cắt lề phải để bỏ hình mờ) |
| `tools/tone_fix.py` | Sửa lỗi dấu thanh do OCR dựa vào ngữ cảnh, học từ văn bản có chữ sạch |
| `tools/parse_structure.py` | Tách Chương, Mục, Điều, Khoản, Điểm và liệt kê chỗ nghi ngờ để rà soát |
| `tools/eval_tone.py` | Đo độ chính xác của bộ sửa dấu trên trang có đáp án chuẩn |
| `book/template.html` | Giao diện sách (HTML, CSS, JS thuần, không thư viện ngoài) |
| `book/build_book.py` | Ghép dữ liệu vào giao diện, ra một file HTML |
| `book/meta.example.json` | Mẫu khai báo văn bản: số hiệu, ngày ban hành, tình trạng hiệu lực, văn bản liên quan |

## Cần cài

- Python 3.10 trở lên
- `poppler-utils` (lệnh `pdftotext`, `pdftoppm`, `pdfinfo`)
- `tesseract-ocr` và mô hình tiếng Việt `vie`. Nên dùng mô hình chính xác hơn: tải
  `vie.traineddata` từ kho `tesseract-ocr/tessdata_best` rồi trỏ `--tessdata-dir` tới thư mục chứa nó
- ImageMagick (lệnh `convert`)

## Các bước

Tất cả lệnh chạy bằng `python3 -I` (chế độ cô lập, không nạp mã lạ từ thư mục đang đứng).

```bash
# 1. Xem PDF nào có chữ, PDF nào cần OCR
python3 -I tools/page_text_audit.py <thư_mục_pdf>

# 2. Lấy chữ từng trang (mỗi văn bản một lần). Ra: <tên>.pages.json và <tên>.txt
python3 -I tools/extract_text.py <file.pdf> <thư_mục_ra> <tên_ngắn> <thư_mục_tessdata>

# 3. Dựng kho từ từ các văn bản có chữ sạch, rồi sửa dấu cho văn bản OCR
python3 -I tools/tone_fix.py build kho.json <sạch1>.pages.json <sạch2>.pages.json
python3 -I tools/tone_fix.py fixdoc kho.json <tên>.pages.json <tên>.final.txt <tên>.fixlog.json

# 4. Tách cấu trúc. Ra: <tên>.json kèm danh sách cảnh báo cần rà soát
python3 -I tools/parse_structure.py <tên>.final.txt <tên>.json

# 5. Dựng sách: sao chép book/meta.example.json, sửa đường dẫn và thông tin, rồi
python3 -I book/build_book.py meta.json so-tay.html
```

File `so-tay.html` mở bằng Chrome hoặc Edge, không cần mạng, không cần cài gì. Gửi file này cho đồng nghiệp.

## Lưu ý quan trọng

- **Tình trạng hiệu lực do người dùng xác nhận** trong `meta.json` (`tinh_trang`). Công cụ không tự suy đoán.
- **Văn bản scan có lỗi chữ.** Trên trang kiểm thử, OCR sai khoảng 8-10% số từ, bộ sửa dấu giảm còn khoảng
  2,5%. Điều nào có nội dung từ OCR được đánh dấu cảnh báo trong sách. Cần rà soát các Điều quan trọng
  với bản gốc trước khi trích dẫn.
- **Ghi chú và đánh dấu** lưu trong trình duyệt của từng máy (không nằm trong file chung). Có nút xuất/nhập.
- **An toàn:** file HTML đầu ra không gọi mạng (khai báo `Content-Security-Policy` chặn mọi kết nối) và không
  dùng thư viện bên ngoài.
- Sách là tài liệu hỗ trợ tra cứu, **không thay thế bản chính thức** của văn bản.

## Chưa làm

- Đọc câu "sửa đổi, bổ sung khoản X Điều Y như sau" từ văn bản sửa đổi và áp vào văn bản gốc, giữ lịch sử.
- Công cụ nhập văn bản có giao diện (hiện chạy bằng dòng lệnh).


## Cập nhật khi có văn bản sửa đổi (bản thử)

```
python3 -I tools/amend_propose.py propose <sua_doi>.json <goc>.json <de_xuat>.json 1
python3 -I tools/amend_propose.py report  <de_xuat>.json <bao_cao>.html
python3 -I tools/amend_propose.py apply   <goc>.json <de_xuat>.json <ids_duyet>.json <goc_moi>.json
```
Công cụ chỉ đề xuất, không tự quyết. Lệnh nào không chắc vị trí thì ghi `xem_tay` kèm lý do. Chạy thử Nghị định 243/2026 → Nghị định 57/2025: 53 lệnh, 35 đề xuất được, 18 cần xem tay.
