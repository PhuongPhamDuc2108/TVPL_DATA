# Trích DANH MỤC trong văn bản pháp luật ra Excel

Bộ script tải văn bản **từ Công báo Chính phủ** (bản chính thức, có file .doc/.docx)
rồi bóc các bảng danh mục ra Excel/CSV/JSON.

Vì sao dùng Công báo mà không dùng thuvienphapluat.vn: TVPL chặn crawl (HTTP 403),
giấu trường "Tình trạng hiệu lực" sau đăng nhập, và bảng trên web đã bị dựng lại
bằng HTML nên dễ sai lệch. Công báo cho đúng file Word gốc.

## Chạy

```bash
venv\Scripts\python.exe danh_muc_nghe.py         # TT 11/2020 + TT 19/2023
venv\Scripts\python.exe danh_muc_hoa_chat.py     # NĐ 24/2026/NĐ-CP
venv\Scripts\python.exe trang_danh_muc_nghe.py   # sinh trang HTML tra cứu nghề
```

Lần chạy đầu cần mạng và **Microsoft Word** (dùng COM để đổi `.doc` cũ sang `.docx`;
`.docx` thì không cần). File gốc lưu ở `data/vanban_goc/`, các lần sau chạy lại
dùng luôn bản đã tải.

Phụ thuộc thêm so với trước: `requests`, `python-docx`, `pandas`, `openpyxl`,
`truststore`, `pywin32` — đã ghi trong `requirements.txt`.

> `truststore` là bắt buộc trên máy này: CDN của Chính phủ (`g7.cdnchinhphu.vn`)
> không gửi kèm chứng chỉ trung gian nên `certifi` dựng chuỗi thất bại. `truststore`
> đẩy việc xác thực sang kho chứng chỉ Windows (tự tải chứng chỉ trung gian theo
> AIA). Không tắt `verify`.

## File

| File | Vai trò |
|---|---|
| `danh_muc_common.py` | tải Công báo, `.doc` → `.docx`, tải HTML (curl_cffi, có cache), duyệt đoạn/bảng đúng thứ tự, ghi Excel |
| `danh_muc_nghe.py` | danh mục nghề nặng nhọc, độc hại, nguy hiểm |
| `danh_muc_hoa_chat.py` | 4 phụ lục hóa chất của NĐ 24/2026 |
| `danh_muc_nganh_nghe.py` | ngành, nghề đầu tư kinh doanh có điều kiện (198 và 142) |
| `danh_muc_phe_lieu.py` | phế liệu: được phép NK, và tạm ngừng tạm nhập tái xuất |
| `danh_muc_bi_mat_nha_nuoc.py` | họ 31 quyết định danh mục bí mật nhà nước |
| `trang_danh_muc_nghe.py` | sinh `public/danh_muc_nghe.html` (tra cứu offline, tìm không dấu) |

**Hai đường lấy nguồn.** Danh mục nghề và hóa chất lấy file Word gốc từ Công báo.
Ba danh mục còn lại **không có đường đó**: Công báo tìm kiếm hỏng (`/tim-kiem`
trả về cùng một danh sách bất kể từ khóa), `thuvienphapluat.vn/van-ban/` trả 403,
`luatvietnam.vn/tim-van-ban` trả 403, vbpl.vn là SPA. Nên chúng bóc từ trang đăng
toàn văn, qua `tai_html()` dùng curl_cffi giả lập Chrome và cache HTML vào
`data/html_goc/`.

## 1. Nghề, công việc nặng nhọc, độc hại, nguy hiểm

Nguồn:

* **TT 11/2020/TT-BLĐTBXH** – 12/11/2020, hiệu lực **01/3/2021** – danh mục gốc,
  bãi bỏ 8 quyết định/thông tư cũ (1995, 1996, 1999, 2000, 2003, 2012, 2016).
* **TT 19/2023/TT-BLĐTBXH** – 29/12/2023, hiệu lực **15/02/2024** – bổ sung.
* **TT 28/2025/TT-BNV** – 31/12/2025, hiệu lực **01/3/2026** – danh mục **riêng
  cho Quân đội**, bãi bỏ QĐ 1085/LĐTBXH-QĐ (1996). Công báo chưa đăng nên lấy bản
  web; cả danh mục nằm trong MỘT bảng HTML, tiêu đề lĩnh vực và dòng "ĐIỀU KIỆN
  LAO ĐỘNG LOẠI …" nằm lọt trong bảng đó.

Kết quả: `data/danh_muc_nghe_nndhnh.xlsx` (+ `.csv`, `.json`)

* **2.429 nghề, công việc / 62 lĩnh vực** — TT 11/2020: 1.840 / 42; TT 19/2023:
  52 / 3; TT 28/2025: **537 / 17** (khớp đúng con số công bố).
* Theo điều kiện lao động: **loại IV 1.576** (nặng nhọc, độc hại, nguy hiểm),
  **loại V 698** + **loại VI 155** (đặc biệt nặng nhọc, độc hại, nguy hiểm).
* Sheet `Danh mục nghề` (từng nghề) và `Tổng hợp theo lĩnh vực`.

Những chỗ bản gốc dễ làm hỏng việc bóc tách, đã xử lý:

* Bản Công báo TT 11/2020 bị **cắt làm 2 số** (301+302 và 303+304).
* Hai tiêu đề lĩnh vực **`XXXVII. GIÁO DỤC - ĐÀO TẠO`** và
  **`XXXXI. TÀI NGUYÊN MÔI TRƯỜNG`** nằm *lọt vào trong bảng* của lĩnh vực trước
  chứ không phải đoạn văn riêng — nếu chỉ đọc đoạn văn sẽ gán nhầm ~30 nghề.
* Số La Mã lĩnh vực trong bản gốc **không chuẩn** ở cuối danh mục
  (`XXXX`, `XXXXI`, `XXXXII` thay vì `XL`, `XLI`, `XLII`) — script giữ nguyên
  cách đánh của văn bản để trích dẫn cho khớp.
* Cột `stt` được đánh lại từ 1 ở **mỗi lĩnh vực và mỗi loại điều kiện lao động**,
  đúng như bản gốc — nên `stt` không phải khóa duy nhất, dùng cột `id`.

Riêng TT 28/2025 (Quân đội) dùng chữ HOA cho dòng phân nhóm ("ĐIỀU KIỆN LAO ĐỘNG
LOẠI VI") nên `RE_LOAI` phải khớp không phân biệt hoa thường.

## 2. Hóa chất — Nghị định 24/2026/NĐ-CP

Nguồn: **NĐ 24/2026/NĐ-CP** ngày 17/01/2026, hiệu lực ngay **17/01/2026**, quy định
các danh mục hóa chất thuộc phạm vi điều chỉnh của **Luật Hóa chất 69/2025/QH15**.

Kết quả: `data/danh_muc_hoa_chat_ND24_2026.xlsx` (+ `.csv`) — **1.376 dòng**:

| Sheet | Nội dung | Số dòng |
|---|---|---|
| `PL I` | Hóa chất cơ bản thuộc lĩnh vực công nghiệp hóa chất trọng điểm | 39 |
| `PL II - SXKD có điều kiện` | Hóa chất sản xuất, kinh doanh có điều kiện | 786 |
| `PL III - Nhóm 1` | Kiểm soát đặc biệt, nhóm 1 | 166 |
| `PL III - Nhóm 2` | Kiểm soát đặc biệt, nhóm 2 | 87 |
| `PL IV - Bảng A` | Phải có Kế hoạch phòng ngừa, ứng phó sự cố — theo từng chất + ngưỡng khối lượng | 277 |
| `PL IV - Bảng B` | Nt — theo nhóm nguy hại | 21 |
| `Tất cả` | gộp cả 6 bảng | 1.376 |

Cột: `stt`, `nguon_stt`, `ten_khoa_hoc` (IUPAC/tiếng Anh), `ten_chat` (tiếng Việt),
`ma_cas`, `ma_cas_tach`, `cas_bat_thuong`, `cong_thuc_hoa_hoc`, `nhom_hoa_chat`,
`nguong_khoi_luong_tan`, `nhom_lon`, `nhom`, `phu_luc`, `muc`, `ten_danh_muc`.

Lưu ý về dữ liệu:

* **`stt` ở Phụ lục I, II, III là do script đánh lại** (`nguon_stt = "tự đánh"`,
  1.078/1.376 dòng): bản gốc dùng danh sách tự động của Word nên ô STT rỗng khi đọc
  bằng python-docx. Đánh lại bắt đầu từ 1 ở mỗi nhóm. Phụ lục IV có STT thật trong
  văn bản (`nguon_stt = "văn bản"`).
* `ma_cas` giữ **nguyên văn**; `ma_cas_tach` là các mã CAS hợp lệ tách ra, ngăn bởi
  `; `. Có 60 dòng không có mã CAS (bản gốc ghi `---`, thường là nhóm hợp chất như
  "Diisocyanate (TDI, MDI, HDI…)"), và **17 dòng chứa nhiều mã CAS** trong một ô.
* `cas_bat_thuong = x`: mã sai định dạng **trong chính bản gốc**. Hiện có đúng 1 dòng:
  Phụ lục IV, `Formaldehit (Nồng độ ≥ 90%)` ghi `50-00-00` (CAS thật là `50-00-0`).
* `nhom_lon` / `nhom`: Phụ lục III chia hai cấp — `A. Các tiền chất công nghiệp`,
  `B. Hóa chất thuộc Công ước CWC` (`2A`, `2A*`, `2B`, `3A`, `3B`, `Hóa chất khác`),
  `C. Hóa chất thuộc các công ước quốc tế`. Số chất trong các nhóm CWC khớp đúng
  Bảng 2 và Bảng 3 của Công ước (2A: 2, 2A\*: 1, 2B: 23; 3A: 4, 3B: 13).
* Bảng "Hóa chất Bảng 3" **đổi tiêu đề cột giữa chừng** sang
  `Tên hóa chất theo tiếng Anh | Tên hóa chất theo tiếng Việt`; script nhận diện
  lại tiêu đề nên không mất cột tên tiếng Việt.
* Ngưỡng khối lượng giữ nguyên định dạng văn bản (`5.000`, `150.000 (net)`) —
  đơn vị là **kg** theo quy định của Phụ lục IV.

Quy tắc **không nằm trong bảng** mà nằm ở phần lời của phụ lục, cần đọc thêm khi
áp dụng: hỗn hợp chứa ít nhất một thành phần thuộc Phụ lục II với hàm lượng
**> 5% khối lượng** thì bị quản như chất tinh khiết; với Phụ lục III là **> 1%**
(nhóm 1) và **> 5%** (tiền chất công nghiệp nhóm 2).

## Kiểm chứng

Cả hai script **đối chiếu số hàng**: mỗi bảng phải giải thích được hết số hàng của
nó (hàng tiêu đề cột + hàng tiêu đề nhóm + hàng dữ liệu). Lệch một hàng là script
dừng với `AssertionError` chứ không âm thầm bỏ sót.

## 3. Ngành, nghề đầu tư kinh doanh có điều kiện

`data/danh_muc_nganh_nghe_kdcdk.xlsx` — phải giữ **cả hai bản** vì đang trong đợt
thay đổi liên tiếp:

| Mốc | Văn bản | Số ngành nghề |
|---|---|---|
| đến 30/6/2026 | Phụ lục IV Luật Đầu tư 61/2020/QH14, đã hợp nhất các luật sửa đổi | **230** (gốc 2020 là 227) |
| 01/3/2026 | Luật Đầu tư 143/2025/QH15 hiệu lực — **trừ Điều 7 + Phụ lục IV** | vẫn 227 |
| 01/7/2026 | Phụ lục IV Luật 143/2025/QH15 hiệu lực | **198** |
| 01/7/2026 → 28/02/2027 | **NQ 66.17/2026/NQ-CP** (15/5/2026) cắt 56 ngành | **142** ← đang áp dụng |
| 01/3/2027 | Luật Đầu tư sửa đổi 2026 tiếp tục cắt giảm | (chưa trích) |

5 sheet: `230 - Luật ĐT 2020 (cũ)`, `198 - Luật 143.2025`, `142 - NQ 66.17.2026`,
`Đã cắt giảm` (56), `Đổi tên` (15). Bản 230 giữ lại làm **bẫy luật cũ** cho bộ
test — AI học dữ liệu cũ sẽ trả lời theo bản này.

**Đối chiếu tự động, kiểm chứng được:** khớp tên nguyên văn được 127/142 ngành.
Còn 71 ngành lệch ở bản 198 và 15 ngành lệch ở bản 142 — script ghép gần đúng
(`difflib`, ngưỡng 0,55) và tìm ra 15 cặp *đổi tên*, còn lại **đúng 56 ngành bị
cắt**, khớp chính xác con số Nghị quyết công bố. Nếu chạy lại mà không ra 56,
script in cảnh báo.

Ngành bị cắt gồm những thứ rất hay gặp trong câu hỏi của dân: dịch vụ kế toán,
cầm đồ, xoa bóp, dịch vụ bảo vệ, logistics, kinh doanh khoáng sản, đại lý và môi
giới bảo hiểm, vận tải biển… AI học từ dữ liệu cũ gần như chắc chắn trả lời sai
nhóm này.

## 4. Phế liệu — hai danh mục KHÁC NHAU

`data/danh_muc_phe_lieu.xlsx` (+ `.csv`), 271 dòng:

| Sheet | Văn bản | Dòng |
|---|---|---|
| Được phép NK - QĐ 13.2023 | QĐ 13/2023/QĐ-TTg (22/5/2023, hiệu lực 01/6/2023, thay QĐ 28/2020) | 24 / 5 nhóm |
| Tạm ngừng - PL I phế liệu | TT 41/2026/TT-BCT (22/7/2026, **hiệu lực 05/9/2026 → 31/12/2029**) | 34 |
| Tạm ngừng - PL II đã sử dụng | nt | 213 |

Đừng lẫn hai danh mục: một cái cho phép **nhập khẩu làm nguyên liệu sản xuất**,
cái kia **cấm kinh doanh tạm nhập, tái xuất, chuyển khẩu**. Cũng đừng lẫn số hiệu:
**TT 41/2026/TT-BXD** (vật liệu xây dựng) và **TT 41/2026/TT-BTC** (thuế tài sản
mã hóa) là văn bản hoàn toàn khác.

Lưu ý dữ liệu:

* Bản Công báo của QĐ 13/2023 là **PDF scan, không có lớp text** (5 trang, 153 ký
  tự) — muốn dùng file gốc thì phải OCR. Bảng ở đây bóc từ trang toàn văn.
* Mã HS trong QĐ 13/2023 bị tách làm 3 cột (`7204` `10` `00`), script nối lại
  thành `72041000`.
* Bản gốc QĐ 13/2023 có **lỗi đánh máy**: dòng thứ 2 của nhóm 1 ghi số thứ tự
  `12` thay vì `1.2`. Giữ nguyên, không tự sửa; khóa tra cứu nên dùng `ma_hs`.
* TT 41/2026 áp dụng quy tắc *"liệt kê mã 2, 4 hoặc 6 số thì mọi mã 8 số thuộc
  nhóm đó đều áp dụng"* — quy tắc nằm ở phần lời, **không** nằm trong bảng.

## 5. Bí mật nhà nước — họ 31 quyết định

`data/danh_muc_bi_mat_nha_nuoc.xlsx`. Nền pháp lý mới: **Luật Bảo vệ bí mật nhà
nước số 117/2025/QH15** (thông qua 10/12/2025, **hiệu lực 01/3/2026**, thay Luật
2018, gom còn 13 lĩnh vực) — nên cả họ đang được ban hành lại trong 2025–2026.

* Sheet `Văn bản`: **31 quyết định** đang hiệu lực và công khai — đầy đủ.
* Sheet `Khoản`: **67 khoản/điểm** bóc từ 4 quyết định tìm được trang toàn văn
  (19, 562, 774, 970/QĐ-TTg). Thêm link vào `TOAN_VAN` trong script là bóc thêm.

**Giới hạn cứng, không phải thiếu sót tra cứu:** ba lĩnh vực **quốc phòng, an
ninh quốc gia – TTATXH, cơ yếu** có quyết định riêng nhưng **bản thân quyết định
không đăng công khai**. Không có nguồn nào crawl được.

Cấu trúc bản gốc là **văn xuôi, không có bảng**: mỗi độ mật là một Điều
(`Điều 1. Bí mật nhà nước độ Tối mật gồm:`), bên dưới là khoản `1.`, `2.`… và
điểm `a)`, `b)`. Cách trình bày **không đồng nhất giữa các quyết định** — bộ tách
xử lý cả ba biến thể: tiêu đề độ mật nằm cùng dòng với "Điều N"; tách rời thành
`Điều 1` / `.` / `Bí mật nhà nước độ…`; và số khoản đứng riêng một dòng. Tiêu đề
độ mật chỉ được nhận khi đứng ngay sau "Điều N", nếu không sẽ nuốt phải đoạn tóm
tắt do trang web tự viết ở đầu bài.

## 6. Toàn bộ nguồn web đang dùng

12 URL, khai báo ngay đầu mỗi script. Đổi nguồn thì sửa ở đó.

| Danh mục | Văn bản | URL |
|---|---|---|
| Nghề NNĐHNH | TT 11/2020/TT-BLĐTBXH | `congbao.chinhphu.vn/van-ban/thong-tu-so-11-2020-tt-bldtbxh-33183.htm` |
| Nghề NNĐHNH | TT 19/2023/TT-BLĐTBXH | `congbao.chinhphu.vn/van-ban/thong-tu-so-19-2023-tt-bldtbxh-41242/48815.htm` |
| Hóa chất | NĐ 24/2026/NĐ-CP | `congbao.chinhphu.vn/van-ban/nghi-dinh-so-24-2026-nd-cp-468796.htm` |
| Ngành nghề | Phụ lục IV Luật 143/2025/QH15 (198) | `thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/chinh-sach-moi/101784/danh-muc-198-nganh-nghe-dau-tu-kinh-doanh-co-dieu-kien-tu-01-7-2026` |
| Ngành nghề | Phụ lục NQ 66.17/2026/NQ-CP (142) | `luatvietnam.vn/linh-vuc-khac/danh-sach-cac-nganh-nghe-kinh-doanh-co-dieu-kien-moi-nhat-tu-01-7-2026-883-109489-article.html` |
| Phế liệu | QĐ 13/2023/QĐ-TTg | `luatvietnam.vn/xuat-nhap-khau/quyet-dinh-13-2023-qd-ttg-phe-lieu-duoc-phep-nhap-khau-lam-nguyen-lieu-san-xuat-253214-d1.html` |
| Phế liệu | TT 41/2026/TT-BCT | `luatvietnam.vn/xuat-nhap-khau/thong-tu-41-2026-tt-bct-danh-muc-phe-lieu-va-hang-hoa-tam-ngung-kinh-doanh-441401-d1.html` |
| BMNN | chỉ mục 31 quyết định | `thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/tu-van-phap-luat/30388/tong-hop-danh-muc-bi-mat-nha-nuoc-trong-cac-linh-vuc` |
| BMNN | QĐ 19/QĐ-TTg (văn hóa, thông tin) | `luatvietnam.vn/van-hoa/quyet-dinh-19-qd-ttg-2026-ban-hanh-danh-muc-bi-mat-nha-nuoc-linh-vuc-van-hoa-thong-tin-423322-d1.html` |
| BMNN | QĐ 562/QĐ-TTg (tài nguyên, môi trường) | `luatvietnam.vn/an-ninh-quoc-gia/quyet-dinh-562-qd-ttg-2025-danh-muc-bi-mat-nha-nuoc-linh-vuc-tai-nguyen-va-moi-truong-393233-d1.html` |
| BMNN | QĐ 774/QĐ-TTg (thanh tra, KNTC) | `luatvietnam.vn/tiet-kiem/quyet-dinh-774-qd-ttg-danh-muc-bi-mat-nha-nuoc-linh-vuc-thanh-tra-khieu-nai-184396-d1.html` |
| BMNN | QĐ 970/QĐ-TTg (Tòa án nhân dân) | `luatvietnam.vn/tu-phap/quyet-dinh-970-qd-ttg-2020-danh-muc-bi-mat-nha-nuoc-thuoc-toa-an-186181-d1.html` |

Ba URL Công báo là **trang giới thiệu**, không phải link file. Script đọc trang
đó, dò link `download/stream?…` trỏ về `g7.cdnchinhphu.vn` rồi mới tải `.doc`/
`.docx`. Link tải có token, **thay đổi theo phiên** nên không hardcode được — đó
là lý do phải cào lại trang mỗi lần thay vì lưu link file.

File gốc lưu ở `data/vanban_goc/` (Word từ Công báo) và `data/html_goc/` (HTML đã
cache). Chạy lại không tải lại; muốn tải mới thì xóa file cache hoặc truyền
`tai_lai=True`.

## 7. Nạp vào PostgreSQL (DB `questions`) — 2 bảng, phân cấp bằng mảng

```
danh_muc              2 dòng — tên, mô tả, văn bản (text[]), NHÃN từng tầng
     └──< danh_muc_chi_tiet   3.268 dòng — phân cấp ở cột `duong_dan text[]`
```

Kết quả: `nghe_nndhnh` **1.892** mục (2 thông tư / 45 lĩnh vực), `hoa_chat`
**1.376** mục (1 nghị định / 4 phụ lục).

> **Phạm vi bảng nghề:** chỉ nạp **TT 11/2020 + TT 19/2023**.
> `TT 28/2025/TT-BNV` (danh mục riêng cho Quân đội, 537 nghề / 17 lĩnh vực) vẫn
> có đủ trong `data/danh_muc_nghe_nndhnh.xlsx` nhưng **không nạp vào DB**: nó
> đánh số La Mã lĩnh vực từ `I` lại, trùng với hai thông tư kia, gộp chung một
> danh mục là gây nhầm khi tra cứu. Muốn nạp lại thì thêm tên nó vào
> `DANH_MUC['nghe_nndhnh']['van_ban']` của `nap_danh_muc_v3.py` — `doc_nghe()`
> lọc theo đúng danh sách đó, không phải sửa chỗ nào khác.

* DDL: **`schema_danh_muc_v3.sql`** (2 bảng, 9 chỉ mục, 7 view)
* Nạp: **`nap_danh_muc_v3.py`**, 3 chế độ giống `nap_postgres.py`

```bash
venv\Scripts\python.exe nap_danh_muc_v3.py --dry-run
```
```bash
venv\Scripts\python.exe nap_danh_muc_v3.py --load --schema-file schema_danh_muc_v3.sql
```

DSN mặc định `postgresql://questions:questions@172.16.10.71:5433/questions` —
**cổng 5433** (bên trong container server chạy ở 5432). Ghi đè bằng
`DATABASE_URL` hoặc `--dsn`.

### Vì sao phân cấp là mảng chứ không phải 3 cột

Đọc bản gốc thì hai văn bản có **số tầng khác nhau**:

| | Số tầng | Đường dẫn thật |
|---|---|---|
| nghề | 2 | `{XV. Y TẾ VÀ DƯỢC, Loại V}` |
| hóa chất PL I | 1 | `{Phụ lục I}` |
| hóa chất PL II, PL IV bảng A | 2 | `{Phụ lục II, 1. Chất sản xuất…}` |
| hóa chất PL IV bảng B | 3 | `{Phụ lục IV, 2. Bảng B, II. Nguy hại vật chất}` |
| hóa chất PL III | 4 | `{Phụ lục III, 1.1. Nhóm 1, A. CÁC TIỀN CHẤT…, Nhóm 1 (IVB)…}` |

Ba cột cố định vì thế **vừa thiếu vừa thừa**: bản v2 phải nối hai tầng vào một
chuỗi (`'Phụ lục III - 1.1. Nhóm 1'`) và để `nhom_con` NULL suốt 2.429 dòng nghề.
Phân bố số tầng sau khi nạp: hóa chất 39 / 1.063 / 21 / 253 dòng ở 1–4 tầng,
nghề toàn bộ 2.429 dòng đúng 2 tầng.

### Bảng `danh_muc` — 2 dòng

`ma`, `ten`, `ten_ngan`, `linh_vuc`, `co_quan`, `can_cu`, `van_ban text[]`,
`mo_ta`, `dung_de_lam_gi`, `pham_vi`, `luu_y`, `so_muc`.

**Nhãn** khai nghĩa các cột dùng chung ở bảng chi tiết, vì cùng một tầng mang
nghĩa khác nhau — tầng 2 của nghề là mức độ nặng nhọc, tầng 2 của hóa chất là
mục trong phụ lục:

| | `nghe_nndhnh` | `hoa_chat` |
|---|---|---|
| `nhan_cap` | `{Lĩnh vực, Điều kiện lao động}` | `{Phụ lục, Mục, Nhóm, Nhóm con}` |
| `nhan_ten` | Tên nghề, công việc | Tên chất |
| `nhan_ten_khac` | — | Tên khoa học (danh pháp IUPAC) |
| `nhan_ma` | — | Mã số CAS |
| `nhan_mo_ta` | Đặc điểm điều kiện lao động | — |

`nhan_cap[i]` ứng với `duong_dan[i]`. Nhờ vậy trang `/danh-muc` tự đặt đúng tiêu
đề cột: chọn nghề thì cột hiện *Lĩnh vực* / *Điều kiện lao động*, chọn hóa chất
thì hiện *Phụ lục* / *Mục* / *Nhóm* / *Nhóm con*.

### Bảng `danh_muc_chi_tiet` — 12 cột

`danh_muc_id` (FK), `van_ban`, `van_ban_id` (FK), `duong_dan text[]`, `stt`,
`ten`, `ten_khac`, `ma_cas`, `cong_thuc_hoa_hoc`, `nguong_khoi_luong_kg`,
`mo_ta`, `content_hash`.

#### `loai_muc` — cột TÍNH TẠI CHỖ ở view, không lưu trong bảng

Vì bản gốc trộn 4 kiểu dòng vào cùng một bảng

| `loai_muc` | Số dòng | Là gì |
|---|---|---|
| `muc` | 3.240 | mục thật của danh mục — một nghề, một chất |
| `nhom` | 21 | một NHÓM chứ không phải cá thể: Phụ lục IV **Bảng B** liệt kê nhóm nguy hại (`Độc cấp tính cấp 1`), tiêu đề cột gốc là *Nhóm hóa chất* |
| `tiep_noi` | 4 | nửa sau của một mục bị xuống dòng: `và các muối proton hóa tương ứng` |
| `ghi_chu` | 3 | lời dẫn, không phải mục: `Ví dụ`, `Ngoại trừ: Fonofos:` |

Cả 4 kiểu **đều lưu nguyên**, vì chúng là hàng riêng thật trong văn bản (Word
còn đánh số cho chúng). Cột này chỉ nói ra dòng nào là mục, để:

* **đếm đúng** — `danh_muc.so_muc` chỉ đếm `loai_muc='muc'` (1.348 hóa chất),
  `so_dong` đếm tất cả (1.376). Trước đây một số đếm duy nhất nói quá số chất.
  Script nạp lấy `so_muc` **qua view**, vì luật phân loại chỉ có ở đó.
* **gắn nhãn đúng** — 21 dòng Bảng B từng bị gắn tiêu đề *"Tên chất"*.

Cột này **không lưu trong bảng** — nó suy được 100% từ dữ liệu sẵn có, nên luật
nằm **duy nhất** ở `CASE` trong view `v_danh_muc_chi_tiet`. Bảng giữ 12 cột, và
không có hai bản luật để lệch nhau. `app.py` vì thế đọc từ view chứ không từ
bảng. Đổi luật thì sửa file schema rồi chạy lại `CREATE OR REPLACE VIEW` —
không cần nạp lại dữ liệu.

Cách nhận ra, **đều lấy từ dấu hiệu trong văn bản, không đoán**:

* `nhom` — dấu hiệu **cấu trúc**: Bảng B có cột `Nhóm hóa chất` thay cho cột
  `Tên chất`, nên `duong_dan[2] LIKE '%Bảng B%'` và không có CAS lẫn công thức.
* `tiep_noi` — tên tiếng Việt mở đầu `và `, tên tiếng Anh mở đầu `and `. Đã
  kiểm ngược: **0** chất có mã CAS hoặc công thức mà tên mở đầu như vậy.
  KHÔNG dùng luật *"tên bắt đầu bằng chữ thường"* — có 34 dòng như thế nhưng
  phần lớn là chất thật, chữ thường là tiếp đầu ngữ hóa học (`n-Butanol`,
  `o-Anisidin`, `m-Flo toluen`).
* `ghi_chu` — mở đầu `Ví dụ` / `Ngoại trừ`.

Bảng cha có thêm `nhan_ten_nhom` (`'Nhóm hóa chất'`) — nhãn dùng cho dòng
`loai_muc='nhom'`. Cần cột riêng vì trong **cùng một văn bản** chủ thể của bảng
đổi: Phụ lục IV Bảng A liệt kê từng chất, Bảng B liệt kê nhóm nguy hại. View
`v_danh_muc_chi_tiet` và API tự chọn nhãn theo `loai_muc`, nên giao diện đổi
tiêu đề cột theo dữ liệu đang xem.

#### `van_ban` + `van_ban_id` — hai cột đi cặp

`van_ban` là tên đọc được (`'TT 11/2020/TT-BLĐTBXH'`), `van_ban_id` là **khóa
ngoại sang bảng `van_ban` đã có sẵn trong DB questions** (2.612 dòng, kèm
`link`). Bộ câu hỏi test nối vào bảng đó qua `cau_hoi_van_ban` (10.427 dòng),
nên chỉ nhờ cột id này mới join được "câu hỏi test" với "danh mục dùng để chấm
nó" — mà đó là lý do bộ danh mục nằm trong DB này:

```sql
SELECT ch.cau_hoi_id, ch.tieu_de, v.so_hieu, dm.ma,
       count(*) AS so_muc_doi_chieu
FROM cau_hoi ch
JOIN cau_hoi_van_ban cv   ON cv.cau_hoi_id = ch.cau_hoi_id
JOIN van_ban v            ON v.van_ban_id  = cv.van_ban_id
JOIN danh_muc_chi_tiet ct ON ct.van_ban_id = v.van_ban_id
JOIN danh_muc dm          ON dm.danh_muc_id = ct.danh_muc_id
GROUP BY 1, 2, 3, 4 ORDER BY 3, 1;
-- 8 câu hỏi: 5 câu TT 11/2020 (1.840 mục), 3 câu NĐ 24/2026 (1.376 mục)
```

Tra id theo `khoa` (cột UNIQUE), **không** theo `so_hieu` — `so_hieu` NULL ở
732/2.612 dòng và không có ràng buộc duy nhất:

    'TT 11/2020/TT-BLĐTBXH'  ->  khoa 'sh:11/2020/tt-blđtbxh'  ->  id 1916

`tra_id_van_ban()` trong loader **dừng hẳn** nếu có tên không tra ra, chứ không
để `NULL` âm thầm: để NULL thì bảng vẫn nạp xong, thống kê vẫn đúng, chỉ có việc
join sang câu hỏi test là lặng lẽ mất dòng.

Bảng `danh_muc` cố ý **không** có `van_ban_id bigint[]` — Postgres không kiểm
được khóa ngoại trên từng phần tử mảng. Thay bằng view `v_danh_muc_van_ban`.

**Không còn `thuoc_tinh jsonb`.** Cột đó từng gói 5 khóa, nhưng soi lại thì chỉ
2 khóa là dữ liệu thật của văn bản (`cong_thuc_hoa_hoc` 1.342 dòng /
`nguong_khoi_luong_kg` 296 dòng), còn `nhom_hoa_chat` lặp y nguyên `ten` ở
21/21 dòng, `nguon_stt` chỉ có 2 giá trị và suy được từ phụ lục, còn
`cas_sai_chu_so_kiem_tra` tính lại 100% từ `ma_cas` bằng `cas_hop_le()`. Vậy
hai khóa thật lên **cột thật** để grid hiện `C6H6` trần thay vì khối JSON, ba
khóa còn lại bỏ. Muốn xem lại 4 mã CAS lệch chữ số kiểm tra thì chạy
`nap_danh_muc_v3.py --dry-run`.

`nguong_khoi_luong_kg` **giữ đơn vị trong tên cột** — bản gốc để đơn vị ở tiêu
đề cột Phụ lục IV, giữ nguyên văn giá trị (`'5.000'`, dấu chấm kiểu Việt).

`ma_cas` là `text`, nhiều mã ngăn bởi `'; '` (17 chất). Tra chính xác thì dùng
`'71-43-2' = ANY(string_to_array(ma_cas, '; '))`, đừng `LIKE` kẻo `43-2` khớp
vào giữa mã khác.

Ký hiệu "ô này không có giá trị" của bản gốc (`-`, `--`, `---`) bỏ về `NULL` ở
**cả** `ma_cas` **và** `cong_thuc_hoa_hoc` — hằng `KHONG_CO` dùng chung. Trước
đây `ma_cas` bỏ (55 dòng) còn `cong_thuc_hoa_hoc` giữ nguyên văn (32 dòng):
cùng một ký hiệu, cùng một nghị định, hai cách xử lý. Đây là dấu **trình bày**,
không phải dữ liệu — khác hẳn việc sửa mã CAS, việc đó không bao giờ làm.

### Truy vấn

```sql
-- lọc theo tầng 1
SELECT ten FROM danh_muc_chi_tiet WHERE duong_dan[1] = 'Phụ lục III';

-- nghề đặc biệt nặng nhọc, bất kể nằm ở tầng nào
SELECT ten, duong_dan FROM danh_muc_chi_tiet
WHERE duong_dan && ARRAY['Loại V','Loại VI'];

-- đường dẫn đọc bằng mắt
SELECT array_to_string(duong_dan, ' › ') AS vi_tri, ten FROM danh_muc_chi_tiet;

-- từng tầng kèm đúng nhãn của nó
SELECT * FROM v_danh_muc_tang WHERE ten = 'Lái máy bay.';

-- tra CAS
SELECT ten, ten_khac FROM danh_muc_chi_tiet WHERE '71-43-2' = ANY(ma);
```

### Bảy view

**Tra cứu**

* `v_danh_muc_chi_tiet` — join sẵn, có `vi_tri`, `phan_loai_nghe` tính tại chỗ,
  và `ten_van_ban` / `link_van_ban` lấy qua `van_ban_id`.
* `v_danh_muc_tang` — trải từng tầng đường dẫn kèm đúng nhãn của tầng đó.
* `v_danh_muc_van_ban` — mỗi danh mục gồm những văn bản nào, kèm `link`,
  `so_muc` / `so_dong`, và **số câu hỏi test đang trỏ vào cùng văn bản đó**.
  Đây là chỗ hai bộ dữ liệu gặp nhau.
* `v_danh_muc_dem` — đếm theo `loai_muc`, để không nhầm số dòng với số mục.

**Tự kiểm — cả ba phải luôn trả 0 dòng**, script nạp chạy sau mỗi `--load`

* `v_danh_muc_sai_van_ban` — tên văn bản không có trong `danh_muc.van_ban`.
* `v_danh_muc_thieu_nhan` — đường dẫn sâu hơn số nhãn đã khai ở bảng cha.
* `v_danh_muc_thieu_van_ban_id` — có tên văn bản nhưng chưa tra ra
  `van_ban_id` (bảng `van_ban` thiếu văn bản, hoặc tên lệch so với `khoa`).

### Xuất cấu trúc bảng ra Excel

`xuat_cau_truc_db.py` đọc thẳng `information_schema` / `pg_indexes` /
`pg_constraint` nên **luôn khớp DB thật**, không chép tay từ file schema.

```bash
venv\Scripts\python.exe xuat_cau_truc_db.py
```

Không tham số thì ra `data/cau_truc_danh_muc_2_bang.xlsx` gồm **cả hai bảng**,
10 sheet: *Tổng quan* · *Cột - danh_muc* · *Cột - danh_muc_chi_tiet* ·
*Quan hệ* (đọc từ chính khóa ngoại) · *Ràng buộc* · *Chỉ mục* ·
*Cột chỉ có ở view* · *Ý nghĩa cột theo danh mục* · *Hiện trạng dữ liệu* ·
*View liên quan*.

Truyền tên bảng thì xuất riêng từng bảng:
`xuat_cau_truc_db.py danh_muc` → `data/cau_truc_danh_muc.xlsx`.

Sheet *Cột* có `so_dong_co_du_lieu` + `ty_le` để thấy ngay cột nào danh mục nào
không dùng (nghề bỏ trống 4/12 cột nghiệp vụ). Sheet *Cột chỉ có ở view* liệt kê
những cột **không nằm trong bảng** mà tính tại chỗ (`loai_muc`, `nhan_ten`,
`vi_tri`, `phan_loai_nghe`, `link_van_ban`…) để khỏi tưởng là thiếu.

Chú thích cột chia **theo từng bảng** trong hằng `MO_TA_COT` — `ten` và
`van_ban` có ở cả hai bảng nhưng mang nghĩa khác nhau, gộp một dict phẳng thì
khóa trùng và bảng này lấy chú thích của bảng kia.

### File cũ đã bỏ

`schema_danh_muc.sql` + `nap_danh_muc_postgres.py` nạp vào **một bảng phẳng**
gồm cả 6 danh mục — bảng đó đã bị `DROP`. Giữ lại **chỉ vì** trong đó còn phần
đọc Excel của ngành nghề / phế liệu / bí mật nhà nước, chưa đưa sang cấu trúc
mới. Thêm chúng vào v3 chỉ cần một mục trong hằng `DANH_MUC` và một hàm đọc dựng
`duong_dan`, không phải đổi bảng.

Bản v2 (2 bảng, 3 cột phân cấp cố định) **đã xóa** — nó là bước trung gian, cấu
trúc bị v3 thay hẳn nên không còn giá trị tham khảo.

## 4. Giao diện tra cứu trên web

Trang `/danh-muc` trong chính `app.py` (không thêm server riêng):

```bash
venv\Scripts\python.exe app.py
```

Mở `http://127.0.0.1:8002/danh-muc` (hoặc cổng đặt ở `PORT`).

| Đường dẫn | Việc |
|---|---|
| `GET /danh-muc` | trang `public/danh_muc.html` |
| `GET /api/danh-muc/bo-loc` | mã danh mục / văn bản / phần mục kèm số lượng |
| `GET /api/danh-muc` | các mục, lọc `ma_danh_muc`, `so_hieu`, `phan_muc`, `cas`, `q`, `limit` |

Lọc theo **mã danh mục** (`nghe_nndhnh` / `hoa_chat_nd24`) chạy bằng SQL ở server;
hai select văn bản và phần mục tự thu hẹp theo danh mục đang chọn. Ô tìm kiếm lọc
phía trình duyệt và **bỏ dấu tiếng Việt** — gõ `lai may bay` vẫn ra *Lái máy bay*;
gõ thẳng mã CAS `71-43-2` cũng ra. Cột tự ẩn khi cả tập kết quả đều rỗng (chọn
danh mục nghề thì mất cột *Tên khoa học* / *Mã CAS*, chọn hoá chất thì mất cột
*Đặc điểm*). Bấm vào một hàng để xem đầy đủ bản ghi, kể cả những cột đang ẩn.
Bảng vẽ 200 dòng mỗi lượt để không dựng 3.268 hàng cùng lúc.

Bố cục toàn màn hình: **trang không cuộn, chỉ hộp bảng cuộn**, nên thanh lọc và
dòng tiêu đề cột luôn nhìn thấy. Đừng đổi lại thành trang cuộn + `thead` sticky:
lúc đó thanh lọc và `thead` nằm ở hai vùng cuộn khác nhau, cuộn trang là dòng tiêu
đề bị đẩy lệch và chui xuống dưới thanh lọc. Màn hẹp (< 760px) thì trả về cuộn
trang bình thường, hộp bảng cao tối đa 70vh.

Nếu chưa nạp dữ liệu, trang báo lỗi kèm đúng lệnh cần chạy thay vì trắng trang.

> Ghi chú: DB **chưa cài extension `unaccent`** (mới chỉ có `pg_trgm`), nên tìm
> không dấu làm ở phía trình duyệt. Muốn chuyển hẳn sang tìm không dấu bằng SQL
> thì cần `CREATE EXTENSION unaccent` trên DB.
