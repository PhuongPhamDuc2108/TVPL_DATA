# -*- coding: utf-8 -*-
"""
Phân loại CHỦ ĐỀ pháp lý cho bộ dữ liệu hỏi - đáp (vd plo_hoidap_dataset.json),
thay cho việc để lĩnh vực là tên chuyên mục ("Tôi muốn hỏi"/"Chat với chuyên gia").

Tín hiệu phân loại (offline, không cần AI):
  - Văn bản được trích dẫn (van_ban_dan_chieu / trich_dan): mạnh nhất
    (vd dẫn "Luật Đất đai" -> Đất đai, "Nghị định 168/2024" -> Giao thông).
  - Từ khóa trong TIÊU ĐỀ (trọng số cao) và CÂU HỎI (trọng số vừa).

Ghi:
  - Chuyển linh_vuc gốc (tên chuyên mục) sang trường "chuyen_muc" (giữ lại nguồn).
  - Đặt linh_vuc = CHỦ ĐỀ phân loại được (hoặc "Khác" nếu không đủ tín hiệu).
  Chạy lại nhiều lần an toàn (giữ chuyen_muc đã có).

Dùng:
  python phan_loai_chu_de.py                         # xem phân bố (dry-run), KHÔNG ghi
  python phan_loai_chu_de.py --apply                 # ghi đè plo_hoidap_dataset.json
  python phan_loai_chu_de.py --in X.json --out Y.json --apply
"""

import argparse
import json
import re
import sys
import unicodedata

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def strip_dia(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def norm(s):
    return re.sub(r"\s+", " ", strip_dia((s or "").lower())).strip()


# Thứ tự = ĐỘ ƯU TIÊN khi hoà điểm (chủ đề đứng trước thắng). Chủ đề rộng
# ("Dân sự - Hợp đồng") để cuối để nhường các chủ đề cụ thể hơn.
# kw: từ khóa (đã bỏ dấu, chữ thường). doc: chuỗi con trong TÊN văn bản (đã bỏ dấu).
TOPICS = [
    ("Giao thông", {
        "kw": ["giao thong", "nong do con", "bang lai", "giay phep lai xe", "bien so",
               "vuot den", "den do", "den xanh", "tin hieu den", "mu bao hiem", "phat nguoi",
               "csgt", "canh sat giao thong", "toc do", "lan duong", "vach ke duong",
               "tai nan giao thong", "dang kiem", "xe cong nghe", "lai xe", "vuot en",
               "xe may", "o to", "giay to xe", "qua tai", "say xin lai xe"],
        "doc": ["giao thong duong bo", "trat tu, an toan giao thong", "168/2024"],
    }),
    ("Đất đai - Nhà ở", {
        "kw": ["dat dai", "so do", "so hong", "thua dat", "quy hoach", "tho cu",
               "chuyen muc dich", "giay chung nhan quyen su dung dat", "thu hoi dat",
               "giai phong mat bang", "xay nha", "nha o", "chung cu", "thue tro",
               "thue nha", "phong tro", "can ho", "dat nen", "bat dong san",
               "lan chiem", "ranh gioi", "tach thua", "dat nong nghiep", "cap so"],
        "doc": ["dat dai", "nha o", "kinh doanh bat dong san", "123/2024"],
    }),
    ("Hôn nhân - Gia đình", {
        "kw": ["ly hon", "ket hon", "hon nhan", "cap duong", "quyen nuoi con",
               "tai san chung", "tai san rieng", "ngoai tinh", "vo chong",
               "tao hon", "dang ky ket hon", "con chung", "bao luc gia dinh"],
        "doc": ["hon nhan va gia dinh"],
    }),
    ("Thừa kế", {
        "kw": ["thua ke", "di chuc", "di san", "hang thua ke", "khai nhan di san",
               "chia di san", "nguoi thua ke", "de lai tai san"],
        "doc": [],
    }),
    ("Lao động - BHXH", {
        "kw": ["hop dong lao dong", "sa thai", "nghi viec", "thai san", "bao hiem xa hoi",
               "bhxh", "tro cap that nghiep", "nguoi lao dong", "so bao hiem", "nghi phep",
               "tai nan lao dong", "tien luong", "luong toi thieu", "thu viec",
               "cham dut hop dong lao dong", "thoi gio lam viec", "cong doan",
               "luong huu", "om dau", "tro cap", "nghi huu", "che do thai san"],
        "doc": ["bo luat lao dong", "bao hiem xa hoi", "viec lam", "cong doan",
                "an toan, ve sinh lao dong"],
    }),
    ("Hình sự", {
        "kw": ["trom", "cuop", "lua dao", "danh nhau", "co y gay thuong tich", "ma tuy",
               "truy cuu trach nhiem hinh su", "bat coc", "giet nguoi", "vu khi",
               "bom min", "danh bac", "tang tru", "hiep dam", "chiem doat tai san",
               "tham o", "pham toi", "phat tu", "khoi to", "bi cao", "bi can",
               "trach nhiem hinh su", "xam hai", "co bac", "buon lau"],
        "doc": ["hinh su", "to tung hinh su"],
    }),
    ("Doanh nghiệp - Đầu tư", {
        "kw": ["doanh nghiep", "cong ty co phan", "thanh lap cong ty", "giay phep kinh doanh",
               "ho kinh doanh", "dau tu", "co dong", "von dieu le", "giai the",
               "pha san", "ma so doanh nghiep", "kinh doanh", "oda", "du an"],
        "doc": ["doanh nghiep", "dau tu", "quan ly va dau tu von nha nuoc", "chung khoan"],
    }),
    ("Thuế - Tài chính", {
        # tránh bare "thue" vì bỏ dấu trùng với "thuê" (thuê nhà/trọ).
        "kw": ["nop thue", "tien thue", "khai thue", "dong thue", "chiu thue", "thue thu nhap",
               "thue gtgt", "thue tndn", "thue tncn", "hoa don", "ma so thue", "quyet toan thue",
               "tncn", "tndn", "gtgt", "mien thue tndn", "hoan thue", "phi truoc ba", "mien giam thue"],
        "doc": ["thue thu nhap", "quan ly thue", "thue gia tri gia tang"],
    }),
    ("Hành chính - Cư trú", {
        "kw": ["cccd", "can cuoc cong dan", "can cuoc", "ho khau", "tam tru", "thuong tru",
               "nhap khau", "ho tich", "khai sinh", "dinh danh", "so ho khau",
               "dang ky cu tru", "xuat canh", "nhap canh", "ho chieu", "muon cccd",
               "muon can cuoc", "so dinh danh"],
        "doc": ["cu tru", "can cuoc", "xuat canh, nhap canh", "ho tich"],
    }),
    ("Tiêu dùng", {
        "kw": ["mua hang online", "giao hang", "hoan tien", "bao hanh", "hang gia",
               "hang kem chat luong", "don hang", "tra hang", "san pham loi", "dat mua"],
        "doc": ["bao ve quyen loi nguoi tieu dung"],
    }),
    ("CNTT - Mạng - Dữ liệu", {
        "kw": ["facebook", "mang xa hoi", "livestream", "thong tin ca nhan", "du lieu ca nhan",
               "camera", "tai khoan ngan hang", "boi nho", "noi xau", "tin nhan", "zalo",
               "an ninh mang", "lo thong tin", "deepfake", "mao danh", "review san pham",
               "dang bai", "an danh"],
        "doc": ["an ninh mang", "giao dich dien tu", "vien thong", "du lieu ca nhan",
                "cong nghe thong tin", "cong nghe so"],
    }),
    ("Y tế", {
        # bỏ "thuoc" (trùng "thuộc"), "chuyen vien" (trùng "chuyên viên"),
        # doc "duoc" -> "luat duoc" (tránh trùng "được").
        "kw": ["kham benh", "chua benh", "benh vien", "bao hiem y te", "bhyt",
               "co so kham chua benh", "hanh nghe kham", "chuyen vien y", "kham chua benh",
               "uong thuoc", "don thuoc", "mua thuoc"],
        "doc": ["kham benh, chua benh", "bao hiem y te", "luat duoc"],
    }),
    ("Giáo dục", {
        "kw": ["hoc sinh", "sinh vien", "truong hoc", "hoc phi", "bang cap", "du hoc",
               "tot nghiep", "tuyen sinh", "giao vien", "hoc bong", "van bang"],
        "doc": ["giao duc"],
    }),
    ("Môi trường - Xây dựng", {
        "kw": ["giay phep xay dung", "xay dung khong phep", "o nhiem", "tieng on",
               "moi truong", "rac thai", "xa thai", "khao sat dia hinh", "khong gian ngam"],
        "doc": ["bao ve moi truong", "xay dung"],
    }),
    ("Dân sự - Hợp đồng", {   # rộng -> để cuối
        "kw": ["hop dong", "dat coc", "vay tien", "cho vay", "tra no", "doi no", "vay no",
               "boi thuong", "mua ban", "giao dich dan su", "den bu", "cam co", "the chap",
               "vi pham hop dong", "don phuong cham dut", "phat vi pham", "giao ket", "uy quyen"],
        "doc": [],
    }),
]

# Biên dịch regex từ khóa (khớp theo ranh giới, tránh "no" lọt vào "nong").
def _mk(kw):
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])")

for _name, _t in TOPICS:
    _t["kw_re"] = [_mk(k) for k in _t["kw"]]

W_DOC, W_TITLE, W_QUES = 4, 3, 1


def classify(rec):
    title = norm(rec.get("tieu_de"))
    ques = norm(rec.get("cau_hoi"))
    docnames = " ; ".join([norm(v.get("ten", "")) for v in rec.get("van_ban_dan_chieu", [])]
                          + [norm(c.get("van_ban", "")) for c in rec.get("trich_dan", [])])

    best, best_score = "Khác", 0
    for name, t in TOPICS:
        s = 0
        if any(sub in docnames for sub in t["doc"]):
            s += W_DOC
        s += W_TITLE * sum(1 for r in t["kw_re"] if r.search(title))
        s += W_QUES * sum(1 for r in t["kw_re"] if r.search(ques))
        if s > best_score:
            best, best_score = name, s
    return best


def main():
    ap = argparse.ArgumentParser(description="Phân loại chủ đề pháp lý cho dataset hỏi - đáp.")
    ap.add_argument("--in", dest="inp", default="plo_hoidap_dataset.json", help="File đầu vào")
    ap.add_argument("--out", dest="out", default=None, help="File đầu ra (mặc định = ghi đè --in khi --apply)")
    ap.add_argument("--apply", action="store_true", help="Ghi kết quả ra file (mặc định chỉ xem phân bố)")
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        data = json.load(f)

    from collections import Counter, defaultdict
    dist = Counter()
    samples = defaultdict(list)
    for r in data:
        topic = classify(r)
        dist[topic] += 1
        if len(samples[topic]) < 3:
            samples[topic].append(r.get("tieu_de", "")[:60])
        r["_topic"] = topic  # tạm

    total = len(data)
    print(f"Tổng: {total} câu | phân bố chủ đề:\n")
    for topic, n in dist.most_common():
        print(f"  {n:5d}  {topic:26s} ({n*100//total:2d}%)")
        for s in samples[topic]:
            print(f"           · {s}")
    print()

    if not args.apply:
        print("→ Đây là DRY-RUN (chưa ghi). Thêm --apply để ghi vào file.")
        return

    for r in data:
        topic = r.pop("_topic")
        if "chuyen_muc" not in r:
            r["chuyen_muc"] = r.get("linh_vuc", "")
        r["linh_vuc"] = topic

    out = args.out or args.inp
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, out)
    print(f"✓ Đã ghi {total} câu (linh_vuc = chủ đề, chuyen_muc = chuyên mục gốc) -> {out}")


if __name__ == "__main__":
    main()
