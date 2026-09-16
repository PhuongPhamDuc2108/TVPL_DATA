# Báo cáo kiểm chứng hiệu lực (web) — 11/08/2026

Đã tra web (vbpl.vn, thuvienphapluat.vn, luatvietnam.vn, chinhphu.vn) toàn bộ ~49 văn bản
đang được xếp "còn hiệu lực". Phát hiện **12 văn bản phân loại SAI** (đang "còn" nhưng thực
tế đã HẾT hiệu lực) — phần lớn bị thay thế đúng **01/7/2026** (sau mốc dữ liệu cũ).

## Đã sửa: CÒN → HẾT
| Văn bản | Thay bằng | Hiệu lực |
|---|---|---|
| **Thông tư 111/2013/TT-BTC** (thuế TNCN) | TT 87/2026/TT-BTC | 01/7/2026 |
| **Luật Thuế thu nhập cá nhân 2007** | Luật TNCN 2025 (109/2025/QH15) | 01/7/2026 |
| **Luật Xây dựng 2014** | Luật Xây dựng 2025 | 01/7/2026 |
| **Luật Thi hành án dân sự 2008** | Luật THADS 2025 (106/2025/QH15) | 01/7/2026 |
| **Luật Thi hành án hình sự 2019** | Luật THAHS 2025 (127/2025/QH15) | 01/7/2026 |
| **Luật Thi hành tạm giữ, tạm giam 2015** | Luật 128/2025/QH15 | 01/7/2026 |
| **Nghị định 123/2020/NĐ-CP** (hóa đơn) | NĐ 254/2026/NĐ-CP | 01/7/2026 |
| **Nghị định 62/2015/NĐ-CP** (THADS) | NĐ 152/2026/NĐ-CP | 01/7/2026 |
| **Nghị định 10/2020/NĐ-CP** (vận tải) | NĐ 158/2024/NĐ-CP | 01/1/2025 |
| **Nghị định 01/2021/NĐ-CP** (đăng ký DN) | NĐ 168/2025/NĐ-CP | 01/7/2025 |
| **Nghị định 28/2015/NĐ-CP** (BH thất nghiệp) | NĐ 374/2025/NĐ-CP | 01/1/2026 |
| **Nghị định 146/2018/NĐ-CP** (BHYT) | NĐ 188/2025 bãi bỏ hầu hết | 15/8/2025 |

## Đã sửa: nhãn chính xác hơn (vẫn GIỮ trong bộ "còn")
- **Nghị định 144/2021/NĐ-CP**: phần PCCC bị NĐ 106/2025 thay; phần an ninh trật tự / bạo lực
  gia đình vẫn còn → đánh dấu "còn (đã sửa đổi)".
- **Luật Thương mại 2005**: một số điều bị Luật Quản lý ngoại thương 2017 bãi bỏ → "còn (đã sửa đổi)".

## Đã xác nhận CÒN hiệu lực (khớp bảng, không đổi)
Bộ luật Dân sự 2015, Bộ luật Hình sự 2015 (sửa đổi 2025), BLLĐ 2019, BLTTDS/BLTTHS 2015 (sửa đổi
2025), Luật HN&GĐ 2014, Luật DN 2020, Luật Cư trú 2020, Hiến pháp 2013 (sửa đổi NQ 203/2025);
Luật SHTT 2005, Luật XLVPHC 2012, Luật Dược 2016, Luật Hộ tịch 2014, Luật Quốc tịch 2008, Luật
BHYT 2008, Luật Giáo dục 2019, Luật Trọng tài TM 2010, Luật ATTP 2010, Luật Khiếu nại 2011, Luật
Tố cáo 2018, Luật TTHC 2015, Luật Lý lịch tư pháp 2009, Luật NLĐ đi làm việc nước ngoài 2020;
NĐ 123/2015, 23/2015, 98/2020, 126/2020, 52/2013, 12/2022, 39/2007, 145/2020, 82/2020, 15/2020,
16/2022, 10/2022.

## Ngoài ra: sửa lỗi logic
Văn bản ghi năm cũ tường minh ("Bộ luật Dân sự 1995", "Bộ luật Hình sự 2009") trước đây bị nhận
nhầm là "còn" → đã thêm bảng **VALID_YEARS** (năm hợp lệ mỗi dòng luật): năm cũ hơn bản hiện hành
tự động → HẾT.

## Kết quả sau kiểm chứng
- CÒN hiệu lực: **1020 câu** (trước khi sửa: 1108) → `cau_hoi_con_hieu_luc_FINAL.json`
- HẾT hiệu lực: 1081 câu
- Chưa xác định (văn bản đuôi hiếm): 1550 câu
