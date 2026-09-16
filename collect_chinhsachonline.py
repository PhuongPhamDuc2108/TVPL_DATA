# -*- coding: utf-8 -*-
"""
Thu thập TOÀN BỘ hỏi - đáp từ "Giải đáp chính sách Online" của Cổng Thông tin
điện tử Chính phủ: https://chinhsachonline.chinhphu.vn/

Đây là nguồn CHÍNH THỐNG: người dân/doanh nghiệp hỏi, các Bộ - cơ quan nhà nước
trả lời trực tiếp, có ghi ngày và trích dẫn văn bản đang hiệu lực -> hợp yêu cầu
"câu trả lời mới, trích dẫn còn hiệu lực, đa lĩnh vực".

Định dạng JSON đầu ra GIỐNG HỆT mẫu cau_hoi_con_hieu_luc.json (mảng phẳng, mỗi
phần tử đúng 6 khóa):
    [
      {
        "linh_vuc": "Lao động - Tiền lương - Người có công",
        "nguon": "chinhsachonline.chinhphu.vn",
        "ngay": "12/08/2026 09:03",
        "tieu_de": "...",
        "cau_hoi": "...",
        "dap_an": "..."
      },
      ...
    ]

Cấu trúc trang nguồn:
  - Danh sách: /danh-sach-cau-hoi.htm , /danh-sach-cau-hoi/trang-N.htm
      * mỗi câu = div.box-item
      * lĩnh vực   : a.box-item-category
      * ngày giờ   : span.time  ("09:03 12/08/2026")
      * tiêu đề+URL: h3 a.question-title
    Site trả HTTP 200 kể cả khi hết -> DỪNG khi 1 trang không còn box-item nào.
  - Chi tiết: câu hỏi ở .detail__cquestion, đáp án ở .detail__rcontent.

Cách dùng:
    python collect_chinhsachonline.py                 # lấy HẾT (mặc định)
    python collect_chinhsachonline.py --count 30      # chỉ 30 câu đầu (xem thử)
    python collect_chinhsachonline.py --output cso.json --delay 1.5

Checkpoint / tiếp tục:
    Ghi ATOMIC theo lô (--save-every, mặc định 20 câu) + sau mỗi trang danh sách
    + khi Ctrl+C. Tắt giữa chừng thì chạy LẠI đúng lệnh cũ: các câu đã có (theo
    URL) được giữ nguyên, chỉ tải phần còn thiếu; đồng thời tự nhặt câu MỚI phát
    sinh ở đầu danh sách. Dùng --restart để bỏ checkpoint, làm lại từ đầu.

    File deliverable = <output> (đúng 6 khóa như mẫu).
    File resume      = <output>.ckpt.json (có thêm "url" để chống trùng).
"""

import argparse
import json
import os
import random
import re
import sys
import time

# Tải trang: ưu tiên curl_cffi (như collect_htpl.py); thiếu thì fallback urllib.
try:
    from curl_cffi import requests as _cc_requests
    _HAS_CURL_CFFI = True
except Exception:
    _HAS_CURL_CFFI = False
    _cc_requests = None
import urllib.request
import urllib.error

from bs4 import BeautifulSoup

# Console Windows mặc định cp1252 -> in tiếng Việt lỗi. Ép UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_URL = "https://chinhsachonline.chinhphu.vn"
LIST_URL = BASE_URL + "/danh-sach-cau-hoi.htm"
SOURCE = "chinhsachonline.chinhphu.vn"
IMPERSONATE = "chrome120"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}

MAX_RETRIES = 6
BACKOFF_BASE = 2.0
BACKOFF_CAP = 120.0
# Mã lỗi TẠM THỜI nên retry: quá tải (429) và lỗi gateway/máy chủ (5xx).
RETRY_STATUS = (429, 500, 502, 503, 504)


def _backoff(attempt, retry_after=None):
    if retry_after and str(retry_after).isdigit():
        return float(retry_after)
    wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    return wait + random.uniform(0, wait * 0.3)   # jitter để tránh dồn nhịp


# --------------------------------------------------------------------------- #
# Tải trang
# --------------------------------------------------------------------------- #
def fetch(session, url, referer=None):
    """Tải 1 trang, tự retry với backoff khi gặp 429/5xx (bao gồm 502)."""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        if _HAS_CURL_CFFI:
            resp = session.get(url, headers=headers, timeout=30.0, impersonate=IMPERSONATE)
            if resp.status_code in RETRY_STATUS and attempt < MAX_RETRIES:
                time.sleep(_backoff(attempt, resp.headers.get("Retry-After")))
                continue
            resp.raise_for_status()
            return resp.text
        else:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30.0) as r:
                    return r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                last_err = e
                # 4xx (trừ 429) là lỗi CỐ ĐỊNH -> không phí retry.
                if e.code not in RETRY_STATUS or attempt >= MAX_RETRIES:
                    raise
                time.sleep(_backoff(attempt, e.headers.get("Retry-After") if e.headers else None))
                continue
            except urllib.error.URLError as e:      # lỗi mạng tạm thời
                last_err = e
                if attempt >= MAX_RETRIES:
                    raise
                time.sleep(_backoff(attempt))
                continue
    if last_err:
        raise last_err
    return ""


def list_page_url(page):
    """URL trang danh sách thứ `page` (trang 1 dùng URL gốc)."""
    if page <= 1:
        return LIST_URL
    return f"{BASE_URL}/danh-sach-cau-hoi/trang-{page}.htm"


# --------------------------------------------------------------------------- #
# Parse
# --------------------------------------------------------------------------- #
def norm_date(s):
    """'09:03 12/08/2026' -> '12/08/2026 09:03' (ngày trước, giờ sau)."""
    s = " ".join((s or "").split())
    d = re.search(r"\d{1,2}/\d{1,2}/\d{4}", s)
    t = re.search(r"\d{1,2}:\d{2}", s)
    if d and t:
        return f"{d.group(0)} {t.group(0)}"
    if d:
        return d.group(0)
    return s


def parse_list(html):
    """Trích [{url, tieu_de, linh_vuc, ngay}] từ 1 trang danh sách.

    Lĩnh vực lấy theo từng box-item; nếu item thiếu thì kế thừa lĩnh vực gần nhất.
    """
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    last_cat = ""
    for item in soup.select("div.box-item"):
        cat_el = item.select_one("a.box-item-category")
        if cat_el:
            last_cat = " ".join(cat_el.get_text(" ", strip=True).split())

        a = item.select_one("h3 a.question-title") or item.select_one("a.question-title")
        if not a:
            continue
        href = a.get("href", "").strip()
        if not href:
            continue
        url = BASE_URL + href if href.startswith("/") else href
        if url in seen:
            continue
        seen.add(url)

        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        time_el = item.select_one("span.time")
        ngay = norm_date(time_el.get_text(" ", strip=True)) if time_el else ""

        out.append({"url": url, "tieu_de": title, "linh_vuc": last_cat, "ngay": ngay})
    return out


def block_text(container):
    """Text theo khối: mỗi <p>/<li> lá là 1 dòng, chuẩn hoá khoảng trắng trong khối.

    Giữ các thẻ inline (nhất là <a> số hiệu văn bản) NẰM CÙNG DÒNG với câu, tránh
    bẻ dòng giữa "Nghị định số 248/2025/NĐ-CP".
    """
    if container is None:
        return ""
    blocks = [b for b in container.find_all(["p", "li"]) if not b.find(["p", "li"])]
    if blocks:
        lines = [" ".join(b.get_text(" ").split()) for b in blocks]
        return "\n".join(l for l in lines if l)
    return " ".join(container.get_text(" ").split())


# --------------------------------------------------------------------------- #
# Bộ máy TÁCH TRÍCH DẪN pháp lý (port từ main.py để script đứng độc lập, không
# phải import main -> tránh gotcha venv). Nhận diện: loại + số hiệu/tên văn bản,
# và điểm/khoản/Điều; rồi ghép điều-khoản với văn bản gần nhất.
# --------------------------------------------------------------------------- #
_VN_UPPER = ("A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ"
             "ÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ")
_VN_LOWER = ("a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệ"
             "ìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ")

_DOC_NUM = (
    r"(?:Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết|Quyết định|"
    r"Pháp lệnh|Văn bản hợp nhất)\s+(?:số\s+)?\d+[/-]?\d*(?:[/-][A-ZĐ][A-ZĐ0-9\-]*)*(?:\s+\d{4})?"
)
_YEAR = r"(?:19|20)\d{2}"
_NAME_BODY = (r"[" + _VN_UPPER + r"](?:[^,.;:\n0-9]|,(?=\s+[" + _VN_LOWER + r"]))" r"{2,90}?")
_DOC_NAME_STOP = (
    r"(?:Bộ luật|Luật|Pháp lệnh)\s+" + _NAME_BODY +
    r"(?:\s+(?:năm\s+)?" + _YEAR + r")?"
    r"(?=\s+(?:quy định|sửa đổi|bổ sung|bao gồm|hiện hành|thì|là|gồm|"
    r"nêu|về|khi|do|cho|tại|theo|được|cụ thể|như sau|hướng dẫn|áp dụng)\b"
    r"|\s*[.;:\n]|\s+,|,\s+[" + _VN_UPPER + r"]|$)"
)
_DOC_NAME_YEAR = (r"(?:Bộ luật|Luật|Pháp lệnh)\s+" + _NAME_BODY + r"\s+(?:năm\s+)?" + _YEAR + r"\b")
_DOC_NAME_NUM = (r"(?:Bộ luật|Luật|Pháp lệnh)\s+" + _NAME_BODY +
                 r"\s+số\s+\d+[/-]\d+(?:[/-][A-ZĐ][A-ZĐ0-9\-]*)?")
_DOC = (f"(?:{_DOC_NUM}|{_DOC_NAME_NUM}|{_DOC_NAME_STOP}|{_DOC_NAME_YEAR}"
        f"|Hiến pháp(?:\\s+(?:năm\\s+)?{_YEAR})?)")

# điểm/khoản/Điều — IGNORECASE để bắt cả dạng đầu câu ("Khoản 2, Điều 10").
_RE_ART = re.compile(
    r"(?:điểm\s+([a-zđ])\s*[,)]?\s+)?(?:khoản\s+(\d+)\s*[,)]?\s+)?[Đđ]iều\s+(\d+[a-zđ]?)",
    re.IGNORECASE,
)
_RE_DOC = re.compile(_DOC)
_RE_SOHIEU = re.compile(r"\d+[/-]\d{2,4}[/-][A-ZĐ][A-ZĐ0-9\-]*")


def _clean_cite(s):
    s = re.sub(r"\s+", " ", s or "").strip(" .,;:")
    return re.sub(r"\s+(?:và|hoặc|cùng|của)$", "", s)


def _so_hieu(doc):
    m = _RE_SOHIEU.search(doc or "")
    return m.group(0) if m else ""


def _dominant_doc(text):
    """Văn bản được viện dẫn nhiều nhất trong bài (gắn cho điều 'mồ côi')."""
    counts, order = {}, {}
    for i, m in enumerate(_RE_DOC.finditer(re.sub(r"\s+", " ", text or ""))):
        d = _clean_cite(m.group(0))
        counts[d] = counts.get(d, 0) + 1
        order.setdefault(d, i)
    if not counts:
        return ""
    return max(counts, key=lambda d: (counts[d], bool(_RE_SOHIEU.search(d)), -order[d]))


def _link_map(node):
    """Bản đồ {số hiệu -> link gốc} từ các thẻ <a> trong khối trả lời."""
    m = {}
    if node is None:
        return m
    for a in node.find_all("a", href=True):
        sh = _so_hieu(" ".join(a.get_text(" ").split()))
        if sh and sh not in m:
            m[sh] = a["href"]
    return m


def extract_citations(node, text):
    """Trả về (van_ban_dan_chieu, trich_dan) đã tách cấu trúc từ đoạn trả lời.

    - van_ban_dan_chieu: [{ten, so_hieu, link}] — mọi văn bản được dẫn (đã gộp trùng).
    - trich_dan: [{van_ban, so_hieu, dieu, khoan, diem, trich_dan_goc, link}] — mỗi
      lần dẫn điều/khoản, ghép với văn bản đứng liền sau (hoặc gần nhất/chủ đạo).
    """
    t = re.sub(r"\s+", " ", text or "")
    links = _link_map(node)
    dom = _dominant_doc(t)

    # 1) Danh sách văn bản (gộp trùng, giữ thứ tự xuất hiện).
    docs, seen_doc = [], set()
    doc_pos = []
    for m in _RE_DOC.finditer(t):
        d = _clean_cite(m.group(0))
        doc_pos.append((m.start(), m.end(), d))
        if d not in seen_doc:
            seen_doc.add(d)
            sh = _so_hieu(d)
            docs.append({"ten": d, "so_hieu": sh, "link": links.get(sh, "")})

    # 2) Từng trích dẫn điều/khoản -> ghép văn bản gần nhất.
    cites, seen_cite = [], set()
    for am in _RE_ART.finditer(t):
        diem = (am.group(1) or "").lower()
        khoan = am.group(2) or ""
        dieu = (am.group(3) or "").lower()

        doc = ""
        adjacent = [d for d in doc_pos if 0 <= d[0] - am.end() <= 3]
        if adjacent:
            doc = adjacent[0][2]
        elif doc_pos:
            nearest = min(doc_pos, key=lambda d: min(abs(d[0] - am.start()), abs(d[0] - am.end())))
            if min(abs(nearest[0] - am.start()), abs(nearest[0] - am.end())) <= 150:
                doc = nearest[2]
        if not doc:
            doc = dom

        key = (doc, dieu, khoan, diem)
        if key in seen_cite:
            continue
        seen_cite.add(key)
        raw = am.group(0).strip()
        if doc and doc.lower() not in raw.lower():
            raw = f"{raw} {doc}"
        sh = _so_hieu(doc)
        cites.append({
            "van_ban": doc,
            "so_hieu": sh,
            "dieu": dieu,
            "khoan": khoan,
            "diem": diem,
            "trich_dan_goc": _clean_cite(raw),
            "link": links.get(sh, ""),
        })

    # 3) LÀM SẠCH tên văn bản (cắt phần "bắt lố") + gộp lại trùng (giữ tên tốt nhất).
    from lam_sach_ten import clean_name, doc_key, ten_score
    cdocs, seen = [], {}
    for d in docs:
        d["ten"] = clean_name(d["ten"])
        d["so_hieu"] = d["so_hieu"] or _so_hieu(d["ten"])
        k = doc_key(d["ten"], d["so_hieu"])
        if k in seen:
            e = seen[k]
            if not e["link"] and d["link"]: e["link"] = d["link"]
            if not e["so_hieu"] and d["so_hieu"]: e["so_hieu"] = d["so_hieu"]
            if ten_score(d["ten"]) > ten_score(e["ten"]): e["ten"] = d["ten"]
        else:
            seen[k] = d; cdocs.append(d)
    ccites, seenc = [], {}
    for c in cites:
        c["van_ban"] = clean_name(c["van_ban"])
        c["so_hieu"] = c["so_hieu"] or _so_hieu(c["van_ban"])
        k = (doc_key(c["van_ban"], c["so_hieu"]), c["dieu"], c["khoan"], c["diem"])
        if k in seenc:
            e = seenc[k]
            if not e["link"] and c["link"]: e["link"] = c["link"]
            if ten_score(c["van_ban"]) > ten_score(e["van_ban"]): e["van_ban"] = c["van_ban"]
            continue
        seenc[k] = c; ccites.append(c)
    return cdocs, ccites


def parse_detail(html, fallback_title=""):
    """Parse trang chi tiết -> dict {tieu_de, cau_hoi, dap_an, van_ban_dan_chieu, trich_dan}."""
    soup = BeautifulSoup(html, "lxml")
    for junk in soup.select("script, style"):
        junk.decompose()

    h1 = soup.select_one("h1")
    tieu_de = h1.get_text(" ", strip=True) if h1 else fallback_title
    tieu_de = re.sub(r"^\s*Hỏi\s*:\s*", "", tieu_de).strip() or fallback_title

    cau_hoi = block_text(soup.select_one(".detail__cquestion"))

    ans = soup.select_one(".detail__rcontent")
    if ans is None:  # fallback: cả khối reply, bỏ tiêu đề "Trả lời"
        ans = soup.select_one(".detail__reply")
        if ans is not None:
            ct = ans.select_one(".detail__ctitle")
            if ct:
                ct.decompose()
    dap_an = block_text(ans)
    dap_an = re.sub(r"^\s*Trả lời\s*\n?", "", dap_an).strip()

    van_ban_dan_chieu, trich_dan = extract_citations(ans, dap_an)

    return {
        "tieu_de": tieu_de,
        "cau_hoi": cau_hoi,
        "dap_an": dap_an,
        "van_ban_dan_chieu": van_ban_dan_chieu,
        "trich_dan": trich_dan,
    }


# --------------------------------------------------------------------------- #
# Lưu checkpoint / deliverable
# --------------------------------------------------------------------------- #
CLEAN_KEYS = ("linh_vuc", "nguon", "ngay", "tieu_de", "cau_hoi", "dap_an",
              "van_ban_dan_chieu", "trich_dan")


def _atomic_dump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(
        description="Thu thập hỏi - đáp chinhsachonline.chinhphu.vn -> JSON (mẫu cau_hoi_con_hieu_luc.json).")
    ap.add_argument("--count", type=int, default=0, help="Số câu cần lấy; 0 = LẤY HẾT (mặc định)")
    ap.add_argument("--output", default="chinhsachonline_dataset.json", help="File JSON deliverable (6 khoá)")
    ap.add_argument("--max-pages", type=int, default=5000, help="Số trang danh sách tối đa quét (mặc định 5000)")
    ap.add_argument("--delay", type=float, default=1.0, help="Giây nghỉ giữa mỗi request (mặc định 1.0)")
    ap.add_argument("--page-retries", type=int, default=4, help="Số vòng thử lại 1 trang danh sách khi lỗi 502/chặn (mặc định 4)")
    ap.add_argument("--save-every", type=int, default=20, help="Ghi checkpoint sau mỗi N câu (mặc định 20)")
    ap.add_argument("--restart", action="store_true", help="Bỏ checkpoint, thu thập lại từ đầu")
    args = ap.parse_args()

    collect_all = args.count <= 0
    OUTPUT = args.output
    CKPT = OUTPUT + ".ckpt.json"

    # --- Nạp checkpoint ---
    records = []          # mỗi phần tử: 6 khoá + "url" (để chống trùng khi resume)
    if os.path.exists(CKPT) and not args.restart:
        try:
            with open(CKPT, encoding="utf-8") as f:
                ck = json.load(f)
            records = ck.get("records", [])
            print(f"↻ Nạp checkpoint {CKPT}: đã có {len(records)} câu.")
        except Exception as e:
            print(f"! Không đọc được checkpoint ({e}), bắt đầu mới.", file=sys.stderr)
            records = []

    done_urls = {r.get("url") for r in records if r.get("url")}

    def save(page):
        ck = {"source": SOURCE, "last_page": page, "total": len(records), "records": records}
        _atomic_dump(CKPT, ck)
        clean = [{k: r.get(k, "") for k in CLEAN_KEYS} for r in records]
        _atomic_dump(OUTPUT, clean)

    session = _cc_requests.Session() if _HAS_CURL_CFFI else None
    engine = "curl_cffi" if _HAS_CURL_CFFI else "urllib (fallback)"
    print(f"Nguồn: {LIST_URL}  |  HTTP engine: {engine}")
    if done_urls:
        print(f"    ↻ đã có {len(done_urls)} câu, sẽ bỏ qua và thu phần còn thiếu / câu mới.")

    page = 1
    new_this_run = 0
    try:
        while page <= args.max_pages:
            # điều kiện dừng theo --count: đủ tổng số câu mong muốn
            if not collect_all and len(records) >= args.count:
                break
            # Trang danh sách: fetch() đã tự retry 429/5xx; thêm vài vòng NGHỈ DÀI
            # để vượt qua 502/chặn tạm kéo dài trước khi mới chịu dừng.
            html = None
            for rnd in range(args.page_retries):
                try:
                    html = fetch(session, list_page_url(page), referer=LIST_URL)
                    break
                except Exception as e:
                    cool = 20 * (rnd + 1)
                    print(f"    ! trang danh sách {page} lỗi: {e} — nghỉ {cool}s rồi thử lại "
                          f"({rnd + 1}/{args.page_retries})", file=sys.stderr)
                    time.sleep(cool)
            if html is None:
                print(f"    ! trang {page} vẫn lỗi sau {args.page_retries} lần — dừng (checkpoint an toàn). "
                      f"Chạy LẠI đúng lệnh cũ để thu tiếp từ đây.", file=sys.stderr)
                break

            items = parse_list(html)
            if not items:
                print(f"    trang {page}: 0 câu -> hết danh sách. Kết thúc.")
                break

            new_items = [it for it in items if it["url"] not in done_urls]
            print(f"    trang {page}: {len(items)} câu ({len(new_items)} mới) — tổng đã lưu: {len(records)}")

            for it in new_items:
                if not collect_all and len(records) >= args.count:
                    break
                try:
                    dhtml = fetch(session, it["url"], referer=list_page_url(page))
                    d = parse_detail(dhtml, fallback_title=it["tieu_de"])
                    if not d["dap_an"]:
                        print(f"        ! bỏ qua (chưa có trả lời): {it['tieu_de'][:60]}", file=sys.stderr)
                        done_urls.add(it["url"])   # đánh dấu để không thử lại vô hạn
                        continue
                    records.append({
                        "linh_vuc": it["linh_vuc"],
                        "nguon": SOURCE,
                        "ngay": it["ngay"],
                        "tieu_de": d["tieu_de"] or it["tieu_de"],
                        "cau_hoi": d["cau_hoi"],
                        "dap_an": d["dap_an"],
                        "van_ban_dan_chieu": d["van_ban_dan_chieu"],
                        "trich_dan": d["trich_dan"],
                        "url": it["url"],
                    })
                    done_urls.add(it["url"])
                    new_this_run += 1
                    if len(records) % max(1, args.save_every) == 0:
                        save(page)
                        print(f"        · đã lưu {len(records)} câu")
                except Exception as e:
                    print(f"        ! lỗi câu {it['url']}: {e}", file=sys.stderr)
                time.sleep(args.delay)

            save(page)          # chốt sau mỗi trang danh sách
            page += 1
            time.sleep(args.delay)

        save(page)
        print(f"\nHoàn thành! Tổng {len(records)} câu (+{new_this_run} mới lần chạy này).")
        print(f"  Deliverable (6 khoá): {OUTPUT}")
        print(f"  Checkpoint resume   : {CKPT}")

    except KeyboardInterrupt:
        save(page)
        print(f"\n■ Đã dừng. Đã lưu {len(records)} câu -> {OUTPUT}. "
              f"Chạy lại lệnh cũ để thu TIẾP.", file=sys.stderr)


if __name__ == "__main__":
    main()
