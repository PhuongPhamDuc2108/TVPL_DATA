# Lọc câu hỏi theo TÌNH TRẠNG HIỆU LỰC của văn bản

Trả lời câu hỏi: *"làm sao biết luật trong câu hỏi đã bị sửa đổi/hết hiệu lực để loại,
chỉ giữ luật còn hiệu lực?"*

## Cách làm (pipeline `loc_hieu_luc.py`)
1. Từ mỗi câu hỏi, rút **văn bản** được viện dẫn (trường `reference`, dùng lại bộ
   trích dẫn của `main.py`).
2. **Chuẩn hoá** (canonical): gộp biến thể hoa/thường, "năm", khoảng trắng, viết tắt
   (BHXH→Bảo hiểm xã hội...), số hiệu thiếu/thừa hậu tố ("43/2014" ≈ "43/2014/NĐ-CP").
3. Tra **bảng trạng thái** `HIEU_LUC` (kiểm chứng từ vbpl.vn / thuvienphapluat.vn,
   tra 11/08/2026). Nguyên tắc miền: *văn bản hướng dẫn của một luật đã bị thay thế
   thì cũng hết hiệu lực* (VD mọi NĐ/TT hướng dẫn Luật Đất đai 2013).
4. Với tên-trơn không năm ("Luật Đất đai"), suy trạng thái theo **ngày câu hỏi**
   (VD hỏi sau 01/8/2024 ⇒ Luật Đất đai 2024 = còn; trước đó ⇒ 2013 = hết).

## Trạng thái
| Mã | Nghĩa | Xử lý |
|---|---|---|
| `con` | Còn hiệu lực | **GIỮ** |
| `con_sd` | Còn hiệu lực, đã sửa đổi/bổ sung (vẫn áp dụng) | **GIỮ** |
| `het` | Hết hiệu lực / bị thay thế | **LOẠI** |
| `het_phan` | Hết hiệu lực một phần | Giữ, soát điều được trích |

## Kết quả (3651 câu)
| Nhóm | Số câu | File |
|---|---|---|
| ✅ CÒN hiệu lực (dùng test) | **1112** | `cau_hoi_con_hieu_luc.json` |
| ❌ HẾT hiệu lực (loại) | **989** | `cau_hoi_het_hieu_luc.json` |
| ❓ CHƯA xác định (văn bản hiếm, cần tra) | **1550** | `cau_hoi_chua_xac_dinh.json` |

- `docs_chua_xac_dinh.txt` — danh sách văn bản chưa có trong bảng (kèm số lần gặp),
  sắp theo tần suất → thêm dần vào bảng để tăng độ phủ.
- `hieu_luc_map.json` — bảng trạng thái đã dùng (xuất ra để tiện tra/mở rộng).

## Mở rộng độ phủ
Với văn bản trong `docs_chua_xac_dinh.txt`, tra trường **"Tình trạng hiệu lực"** trên
`thuvienphapluat.vn` hoặc `vbpl.vn` (Cơ sở dữ liệu quốc gia), rồi thêm 1 dòng vào dict
`HIEU_LUC` trong `loc_hieu_luc.py` và chạy lại:
```
"Nghị định 96/2016/NĐ-CP": (CON, "điều kiện ANTT ngành nghề kinh doanh"),
```
Chạy: `venv/Scripts/python.exe loc_hieu_luc.py`

## Lưu ý
- Bộ "CÒN" ưu tiên độ CHÍNH XÁC: chỉ gồm văn bản đã xác nhận còn hiệu lực → an toàn
  để làm ground-truth test.
- Bộ "CHƯA xác định" KHÔNG phải đều hết hiệu lực — phần lớn là văn bản đuôi hiếm gặp
  (nhiều cái vẫn còn hiệu lực). Mở rộng bảng để thu hồi các câu này.
