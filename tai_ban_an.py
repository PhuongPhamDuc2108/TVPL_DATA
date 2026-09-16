# -*- coding: utf-8 -*-
"""
CACH B: Tai ban an hanh chinh ve KHIEU NAI / KHOI KIEN (that, cong khai) tu
congbobanan.toaan.gov.vn + anle.toaan.gov.vn — link PDF TRUC TIEP, khong can login.
Moi ban an chua nguyen "phan trinh bay cua nguoi khoi kien" = noi dung don that cua dan.

Script: tai PDF -> luu; tach phan trinh bay cua nguoi khoi kien -> *_noidungdon.txt.
Yeu cau: PyMuPDF (fitz) — da co san.
"""
import os
import re
import ssl
import urllib.request
import fitz

OUT_DIR = r"D:\TVPL_data\data_khieunai\ban_an"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# ten_file -> URL PDF truc tiep (da xac minh loai tai duoc)
FILES = {
    "anle_06_2023_HC-GDT_thu_hoi_dat.pdf":       "https://anle.toaan.gov.vn/webcenter/ShowProperty?nodeId=%2FUCMServer%2FTAND319255",
    "anle_24_2020_HC-GDT_dat_dai.pdf":           "https://anle.toaan.gov.vn/webcenter/ShowProperty?nodeId=/UCMServer/TAND199003",
    "cbba_717_2025_HC-PT_nguyenvanH.pdf":        "https://congbobanan.toaan.gov.vn/5ta1821464t1cvn/65_Nguyen_Van_H__UBND_TP_B.pdf",
    "cbba_487_2020_HC-PT.pdf":                   "https://congbobanan.toaan.gov.vn/5ta699931t1cvn/mahoa.pdf",
    "cbba_345_2025_HC-ST_buithiT.pdf":           "https://congbobanan.toaan.gov.vn/5ta2050795t1cvn/Bu%CC%80i_Thi%CC%A3_T3.pdf",
    "cbba_42_2025_HC-ST_binhthuan.pdf":          "https://congbobanan.toaan.gov.vn/5ta1780006t1cvn/Ban_an_so_tham.pdf",
    "cbba_130_2023_HC-ST_phamthi.pdf":           "https://congbobanan.toaan.gov.vn/5ta1456597t1cvn/ban_an_pham_thi_aubnd_tp_pt.pdf",
    "cbba_250_2025_HC-PT_nguyenvanN.pdf":        "https://congbobanan.toaan.gov.vn/5ta1740790t1cvn/40_Nguyen_Van_N__UBND_huyen_D.pdf",
    "cbba_longan_thao_phung.pdf":                "https://congbobanan.toaan.gov.vn/5ta504010t1cvn/THAO___PHUNG.pdf",
}

START = re.compile(r'(người khởi kiện|người khiếu nại)[^\n]{0,40}(trình bày|khởi kiện|khiếu nại)', re.I)
END = ["Người bị kiện", "người bị kiện", "NHẬN ĐỊNH", "Tại phiên tòa", "Đại diện Viện kiểm sát",
       "XÉT THẤY", "QUYẾT ĐỊNH:"]


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=90, context=CTX).read()


def extract_don(full):
    m = START.search(full)
    if not m:
        # fallback: tu "khởi kiện" dau tien
        i = full.find("khởi kiện")
        if i < 0:
            return None
        s = max(0, i - 60)
    else:
        s = m.start()
    ends = [full.find(k, s + 50) for k in END if full.find(k, s + 50) > 0]
    e = min(ends) if ends else s + 5000
    return full[s:e].strip()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ok = 0
    for name, url in FILES.items():
        out = os.path.join(OUT_DIR, name)
        try:
            data = fetch(url)
            if data[:5] != b"%PDF-":
                print(f"SKIP {name} (khong phai PDF)"); continue
            with open(out, "wb") as f:
                f.write(data)
            doc = fitz.open(out); full = "".join(p.get_text() for p in doc); pages = doc.page_count; doc.close()
            don = extract_don(full)
            if don:
                with open(out.replace(".pdf", "_noidungdon.txt"), "w", encoding="utf-8") as f:
                    f.write(don)
            print(f"OK   {name:<40} {len(data):>8,}b  {pages}tr  don={'co' if don else 'khong'} ({len(don) if don else 0} ky tu)")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}  ({e})")
    print(f"\n==> Tai {ok}/{len(FILES)} ban an vao {OUT_DIR}")
    print("    Moi ban an co them file *_noidungdon.txt = phan trinh bay cua nguoi khoi kien (noi dung don).")


if __name__ == "__main__":
    main()
