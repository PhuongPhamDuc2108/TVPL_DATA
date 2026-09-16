# -*- coding: utf-8 -*-
"""
Tai hang loat DON THU / VAN BAN GIAI QUYET KHIEU NAI THAT (co noi dung, khong phai mau trong)
Nguon: cac Cong TTDT / Thanh tra tinh cong khai theo Luat Khieu nai (van ban da cong bo hop phap).
Moi file la 1 vu viec cu the cua cong dan: Quyet dinh giai quyet khieu nai / Ket luan noi dung to cao...

Ghi chu:
- Nhieu cong .gov.vn dung chung chi SSL cau hinh loi -> script tat verify SSL (context CERT_NONE).
- Dat CRAWL_MORE = True de tu dong quet them cac vu moi tren cong Gia Lai (kho /upload/2005340).
"""
import os
import ssl
import re
import urllib.request
import urllib.parse

OUT_DIR = r"D:\TVPL_data\data_khieunai"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# gov.vn hay loi chung chi -> bo qua verify SSL
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# Quet them cac vu moi tu trang danh muc (tuy chon)
CRAWL_MORE = False
INDEX_PAGES = [
    "https://gialai.gov.vn/thong-tin-tra-cuu/ket-qua-giai-quyet-khieu-nai-to-cao",
]

# ===== Danh sach van ban THAT da verify tai duoc (ten_file -> URL) =====
FILES = {
    "01_kn_nguyen_thi_nguyet_quangngai.pdf": "https://bavi.quangngai.gov.vn/upload/2007096/20251031/QD%20GIAI%20QUYET%20KHIEU%20NAI%20LAN%20DAU%20(Nguyen%20Th%E1%BB%8B%20Nguy%E1%BB%87t).pdf",
    "02_kn_1787_gialai_2022.pdf":            "https://gialai.gov.vn/upload/2005340/20220714/1787_g_042cc.pdf",
    "03_kn_l2_cao_hoang_doan_vien.pdf":      "https://gialai.gov.vn/upload/2005340/20241011/CAO_HOANG_DOAN_VIEN______QN____L2___10_10_2024__1__c85c6.pdf",
    "04_bao_cao_89_gialai_2025.pdf":         "https://gialai.gov.vn/upload/2005340/20251017/89BC_b47b8.pdf",
    "05_qd_2702_gialai_2025.pdf":            "https://gialai.gov.vn/upload/2005340/20251125/2702QD_73b0c.pdf",
    "06_kn_l2_bui_thi_thien_hoainhon.pdf":   "https://gialai.gov.vn/upload/2005340/20260627/BUI_THI_THIEN______P_HOAI_NHON_NAM_______L2______04_6_2026_7088d.pdf",
    "07_qd_l2_vu_ong_phong.pdf":             "https://gialai.gov.vn/upload/2005340/20260627/Copy_of_QUYET_DINH_GIAI_QUYET_LAN_2_VU_ONG_PHONG_961a3.pdf",
    "08_kn_le_thi_chanh_phumydong.pdf":      "https://gialai.gov.vn/upload/2005340/20260627/Le_Thi_Chanh_o_xa_Phu_My_Dong______01_6_2026_81935.pdf",
    "09_kn_l2_nguyen_thi_ha_phumydong.pdf":  "https://gialai.gov.vn/upload/2005340/20260627/NGUYEN_THI_HA____XA_PHU_MY_DONG_____L2______25_5_2026_07f11.pdf",
    "10_kn_nong_tan_du_an_cathaibay.pdf":    "https://gialai.gov.vn/upload/2005340/20260627/Nong_Tan_hiep_anh_huong_Du_an_Cat_Hai_Bay_ff7ab.pdf",
    "11_kn_pham_thi_hoa_degi.pdf":           "https://gialai.gov.vn/upload/2005340/20260627/Pham_Thi_Hoa_o_xa_De_Gi______01_6_2026_cdc18.pdf",
    "12_qd_giai_quyet_lan2.pdf":             "https://gialai.gov.vn/upload/2005340/20260627/QUYET_DINH_GIAI_QUYET_LAN_2_97a98.pdf",
    "13_qd2908_dinhchi_nguyen_thi_thua.pdf": "https://gialai.gov.vn/upload/2005340/20260729/QD2908_dinh_chi_gqkn_Nguyen_Thi_Thua_o_xa_De_Gi_ad101_5f3e0.pdf",
    "14_qd2947_pham_hong_thai_quynhon.pdf":  "https://gialai.gov.vn/upload/2005340/20260729/QD2947_Pham_Hong_Thai_o_P__Quy_Nhon_______08_7_2026_1a4e6_47280.pdf",
    "15_qd2948_pham_thi_hong_phuong.pdf":    "https://gialai.gov.vn/upload/2005340/20260729/QD2948_Pham_Thi_Hong_Phuong_o_P__An_Nhon_Dong______08_7_2026_67e8d_84e49.pdf",
    "16_qd_khieu_nai_binhdinh_2021.pdf":     "https://quynhon.binhdinh.gov.vn/upload/105285/20230831/5d1f4487fdcac1d16eb54d996a1cb2065162_20qd_202021.pdf",
    "17_qd_khieu_nai_binhdinh_2022.pdf":     "https://quynhon.binhdinh.gov.vn/upload/105285/20230831/fedcf668ad7fc91825bd37f5deb9b3e92666_20qd_202022.pdf",
    "18_tb_ubnd_quynhonbac_2025.pdf":        "https://quynhonbac.gialai.gov.vn/upload/105720/20251001/123_TB-UBND_26092025-signed_21838.pdf",
    "19_qd_xacminh_kn_quangngai_2026.pdf":   "https://vanban.quangngai.gov.vn/upload/2007099/20260616/692__Qdinh_xac_minh_signed_e3744.pdf",
}


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout, context=CTX)


def crawl_more(existing_urls):
    """Quet cac trang danh muc -> lay link chi tiet -> trich PDF trong /upload/."""
    kw = re.compile(r"(khieu-nai|to-cao)", re.I)
    detail = set()
    for idx in INDEX_PAGES:
        try:
            html = fetch(idx, 40).read().decode("utf-8", "ignore")
            for href in re.findall(r'href=["\']([^"\']+)["\']', html):
                if kw.search(href) and href.endswith(".html"):
                    detail.add(urllib.parse.urljoin(idx, href))
        except Exception as e:
            print("  [crawl] loi index:", e)
    found = {}
    for d in list(detail)[:60]:
        try:
            html = fetch(d, 40).read().decode("utf-8", "ignore")
            for m in re.findall(r'file=(/upload/[^"\'&]+\.pdf)', html):      # pdfjs viewer
                found.setdefault(urllib.parse.urljoin(d, m), None)
            for m in re.findall(r'(?i)(?:href|src)=["\'](/upload/[^"\']+\.pdf)["\']', html):
                found.setdefault(urllib.parse.urljoin(d, m), None)
        except Exception:
            pass
    # dat ten file tu duoi URL, bo trung
    extra = {}
    for i, u in enumerate(sorted(found), 1):
        if u in existing_urls:
            continue
        base = os.path.basename(urllib.parse.urlparse(u).path)
        extra[f"crawl_{i:02d}_{base}"] = u
    print(f"  [crawl] tim them {len(extra)} van ban moi")
    return extra


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = dict(FILES)
    if CRAWL_MORE:
        files.update(crawl_more(set(FILES.values())))

    ok = fail = 0
    for name, url in files.items():
        out = os.path.join(OUT_DIR, name)
        try:
            data = fetch(url).read()
            if not (data[:5].startswith(b"%PDF") or name.lower().endswith((".doc", ".docx"))):
                print(f"SKIP {name:<40} (khong phai file van ban)")
                fail += 1
                continue
            with open(out, "wb") as f:
                f.write(data)
            print(f"OK   {name:<40} {len(data):>9,} bytes")
            ok += 1
        except Exception as e:
            print(f"FAIL {name:<40} ({e})")
            fail += 1
    print(f"\n==> Tai xong: {ok} OK, {fail} loi/skip. Thu muc: {OUT_DIR}")


if __name__ == "__main__":
    main()
