# -*- coding: utf-8 -*-
"""
Cao DON KHIEU NAI / TO CAO da dien noi dung tu tailieu.vn (dang "mau da dien vi du",
giong cau truc don dan gui di: Kinh gui / Ho ten / CMND / Noi dung khieu nai + tinh huong).

Cach hoat dong:
  - tailieu.vn CHAN trang /tag/ va /tim-kiem/ (403) nhung cho tai trang /doc/ le (200).
  - => BFS: bat dau tu vai URL /doc/ da biet, moi trang lay them link "tai lieu lien quan"
    (chi nhung link co khieu-nai / to-cao / khieu-kien trong URL) roi mo rong.
  - Boc text don ngay trong HTML preview (don 1 trang nam san trong trang), luu .docx + .txt.

Ghi chu:
  - Nut Download cua tailieu.vn can dang nhap/point -> script KHONG tai file goc,
    ma lay phan text preview (chinh la toan van don). Du de test boc tach.
  - Don o day la MAU DA DIEN VI DU (co cho "……" + doan vi du). Don dien cu the 100%
    (ten/dia chi/CCCD that) nam tren Scribd nhung site do chan bot (can login).
"""
import os
import re
import ssl
import time
import urllib.request

OUT_DIR = r"D:\TVPL_data\data_khieunai\don_thu"
MAX_DOCS = 40          # tang len neu muon nhieu hon
DELAY = 0.5            # giay, cho lich su voi server
MAKE_DOCX = True
MAKE_TXT = True

SEEDS = [
    "https://tailieu.vn/doc/mau-don-khieu-nai-ve-xay-dung-trai-phep-tren-dia-ban-2957635.html",
    "https://tailieu.vn/doc/mau-don-khieu-nai-lan-chiem-loi-di-chung-2957595.html",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi,en;q=0.9",
    "Referer": "https://tailieu.vn/",
}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

DOC_RE = re.compile(r'https?://tailieu\.vn/doc/[a-z0-9\-]+-\d+\.html')
URL_KW = re.compile(r'(khieu-nai|to-cao|khieu-kien)', re.I)
SLUG_RE = re.compile(r'/doc/([a-z0-9\-]+)-\d+\.html')
END_MARKERS = ["Tài liệu liên quan", "Gợi ý tài liệu", "Tài liệu cùng", "Bình luận",
               "Có thể bạn quan tâm", "Nội dung Text", "YOMEDIA", "Tài liệu mới",
               "Tài liệu khác", "Nội dung tài liệu"]


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=45, context=CTX).read().decode("utf-8", "ignore")


def detag(h):
    h = re.sub(r'(?is)<script.*?</script>|<style.*?</style>', ' ', h)
    h = re.sub(r'(?s)<[^>]+>', ' ', h)
    h = re.sub(r'&nbsp;|&#\d+;|&amp;', ' ', h)
    return re.sub(r'[ \t]+', ' ', h)


def extract_don(html):
    t = detag(html)
    s = t.find("CỘNG HÒA XÃ HỘI")
    if s < 0:
        s = t.find("ĐƠN ")
    if s < 0:
        return None
    ends = [t.find(m, s) for m in END_MARKERS if t.find(m, s) > 0]
    e = min(ends) if ends else s + 6000
    body = t[s:e].strip()
    # phai la don khieu nai / to cao that su
    up = body.upper()
    if "KHIẾU NẠI" not in up and "TỐ CÁO" not in up:
        return None
    return re.sub(r'\s{3,}', '\n', body)


def save(slug, body):
    if MAKE_TXT:
        with open(os.path.join(OUT_DIR, slug + ".txt"), "w", encoding="utf-8") as f:
            f.write(body)
    if MAKE_DOCX:
        try:
            from docx import Document
            d = Document()
            for ln in body.split("\n"):
                if ln.strip():
                    d.add_paragraph(ln.strip())
            d.save(os.path.join(OUT_DIR, slug + ".docx"))
        except Exception as e:
            print("   (docx loi, chi luu txt):", e)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    queue = list(SEEDS)
    seen = set()
    saved = 0
    while queue and saved < MAX_DOCS:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = get(url)
        except Exception as e:
            print("  err:", url[-50:], e)
            continue
        # mo rong hang doi
        for r in DOC_RE.findall(html):
            if r not in seen and URL_KW.search(r):
                queue.append(r)
        body = extract_don(html)
        if not body or len(body) < 150:
            continue
        m = SLUG_RE.search(url)
        slug = (m.group(1) if m else "don")[:60]
        save(slug, body)
        saved += 1
        print(f"  OK ({len(body):>4} ky tu) [queue={len(queue)}]: {slug}")
        time.sleep(DELAY)

    print(f"\n==> Luu {saved} don vao {OUT_DIR}")
    print(f"    (con {len(queue)} link trong hang doi — tang MAX_DOCS de lay them)")


if __name__ == "__main__":
    main()
