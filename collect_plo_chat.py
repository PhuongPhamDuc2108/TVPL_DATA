# -*- coding: utf-8 -*-
"""
Thu thập TOÀN BỘ hỏi - đáp chuyên mục "Chat với chuyên gia" của Báo Pháp Luật
TP.HCM (PLO, chạy trên nền tuoitre.vn):
    https://tuoitre.vn/plo/phap-luat/chat-voi-chuyen-gia.htm

Bạn đọc gửi câu hỏi -> luật sư/chuyên gia (giảng viên luật, luật sư đoàn...) giải
đáp, có ghi ngày và trích dẫn điều luật -> hợp yêu cầu "câu trả lời mới, trích dẫn".

Định dạng JSON đầu ra GIỐNG HỆT mẫu chinhsachonline (mảng phẳng, đúng 8 khóa):
    linh_vuc, nguon, ngay, tieu_de, cau_hoi, dap_an, van_ban_dan_chieu, trich_dan
-> dùng chung được với trình xem public/index.html.

Bộ tách trích dẫn pháp lý (điều/khoản/điểm + văn bản) được TÁI SỬ DỤNG từ
collect_chinhsachonline.py để không lặp code.

Cấu trúc nguồn:
  - Danh sách nạp qua "timeline" (AJAX loadmore), 20 câu/trang:
        https://tuoitre.vn/plo/timeline/109311/trang-{N}.htm   (cần header XHR)
    Mỗi câu = <article class="box-category-item">: tiêu đề+URL (a.box-category-link-title),
    lĩnh vực (a.box-category-category), ngày (span.box-category-time).
    Trang rỗng -> DỪNG.
  - Chi tiết: tiêu đề h1.article__title; nội dung [data-role=content].
    Tách câu hỏi/đáp án theo mốc "...đặt câu hỏi:" và "...giải đáp/trả lời... như sau:".

Cách dùng / checkpoint: giống collect_chinhsachonline.py.
    python collect_plo_chat.py                 # lấy HẾT
    python collect_plo_chat.py --count 20       # xem thử 20 câu
"""

import argparse
import json
import os
import random
import re
import sys
import time

try:
    from curl_cffi import requests as _cc_requests
    _HAS_CURL_CFFI = True
except Exception:
    _HAS_CURL_CFFI = False
    _cc_requests = None
import urllib.request
import urllib.error

from bs4 import BeautifulSoup

# Tái sử dụng bộ tách trích dẫn + tiện ích từ crawler chinhsachonline (cùng thư mục).
from collect_chinhsachonline import extract_citations, block_text, _atomic_dump, CLEAN_KEYS

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SITE = "https://tuoitre.vn"
TIMELINE_FMT = SITE + "/plo/timeline/{zone}/trang-{p}.htm"
SOURCE = "tuoitre.vn/plo"
# Các chuyên mục hỏi - đáp pháp luật của PLO cần lấy (zone tự phát hiện từ trang).
SECTIONS = [
    ("Chat với chuyên gia", SITE + "/plo/phap-luat/chat-voi-chuyen-gia.htm"),
    ("Tôi muốn hỏi",        SITE + "/plo/ban-doc/toi-muon-hoi.htm"),
]
_RE_ZONE = re.compile(r'id="hdZoneId"[^>]*value="(\d+)"')
IMPERSONATE = "chrome120"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}

MAX_RETRIES = 6
BACKOFF_BASE = 2.0
BACKOFF_CAP = 120.0
RETRY_STATUS = (429, 500, 502, 503, 504)


def _backoff(attempt, retry_after=None):
    if retry_after and str(retry_after).isdigit():
        return float(retry_after)
    wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    return wait + random.uniform(0, wait * 0.3)


def fetch(session, url, referer=None, xhr=False):
    """Tải 1 trang, tự retry 429/5xx. xhr=True -> gửi header AJAX (cho timeline)."""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    if xhr:
        headers["X-Requested-With"] = "XMLHttpRequest"
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
                if e.code not in RETRY_STATUS or attempt >= MAX_RETRIES:
                    raise
                time.sleep(_backoff(attempt, e.headers.get("Retry-After") if e.headers else None))
            except urllib.error.URLError as e:
                last_err = e
                if attempt >= MAX_RETRIES:
                    raise
                time.sleep(_backoff(attempt))
    if last_err:
        raise last_err
    return ""


def parse_list(html):
    """Trích [{url, tieu_de, linh_vuc, ngay}] từ 1 trang timeline."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for art in soup.select("article.box-category-item"):
        a = art.select_one("a.box-category-link-title") or art.select_one("h3 a[href]")
        if not a:
            continue
        href = (a.get("href") or "").strip()
        if not href:
            continue
        url = SITE + href if href.startswith("/") else href
        if url in seen:
            continue
        seen.add(url)
        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        cat_el = art.select_one("a.box-category-category")
        linh_vuc = cat_el.get_text(" ", strip=True) if cat_el else "Chat với chuyên gia"
        t_el = art.select_one(".box-category-time")
        ngay = ""
        if t_el:
            ngay = " ".join((t_el.get("title") or t_el.get_text(" ", strip=True)).split())
        out.append({"url": url, "tieu_de": title, "linh_vuc": linh_vuc, "ngay": ngay})
    return out


# Mốc bắt đầu ĐÁP ÁN: đoạn mở bằng động từ đáp, HOẶC "(chức danh) ... (động từ đáp)"
# — bắt cả kiểu không có dấu ":" ("...TS Trần Ngọc Tuấn, ĐH Luật, cho biết trong...").
_TITLE_TOKENS = (r"luật sư|ls|th\.?s|thạc sĩ|ts|tiến sĩ|pgs|gs|chuyên gia|giảng viên|"
                 r"luật gia|đại diện|bhxh|bảo hiểm xã hội|bộ|sở|công an|cơ quan|phòng|"
                 r"ban|toà|tòa|cục|chi cục|trung tâm|ubnd")
_ANS_VERB = (r"giải đáp|trả lời|cho biết|cho hay|phân tích|nhận định|"
             r"giải thích|trao đổi|chia sẻ|thông tin|phản hồi|tư vấn")
# Dùng [^\n]{0,80}? (KHÔNG chặn ở dấu ".") vì chức danh hay có "TP.HCM", "Th.S"...
_RE_ANS = re.compile(
    r"^(?:giải đáp|trả lời|tư vấn|phản hồi|về vấn đề|theo đó)\b"
    r"|(?:%s)\b[^\n]{0,80}?(?:%s)\b" % (_TITLE_TOKENS, _ANS_VERB),
    re.IGNORECASE)
# Lời khẩn của NGƯỜI HỎI ("Luật sư tư vấn giúp tôi", "nhờ luật sư"...) -> KHÔNG phải
# mốc trả lời, phải loại để không cắt nhầm.
_RE_PLEA = re.compile(r"(giúp|nhờ|mong|xin|cho)\s+(tôi|em|mình|con|cháu|luật sư|ls)\b", re.IGNORECASE)
# Vạch phân tách rõ nhất ở mục "Tôi muốn hỏi": dòng "Bạn đọc <tên/email>" KẾT THÚC
# câu hỏi; đáp án bắt đầu ngay sau đó.
_RE_BYLINE_SEP = re.compile(r"^\s*Bạn đọc\b", re.IGNORECASE)
# Dòng khuôn mẫu mở đầu câu hỏi -> bỏ khỏi phần câu hỏi.
_RE_Q_INTRO = re.compile(
    r"(gửi câu hỏi|gửi tới chuyên mục|đặt câu hỏi|có câu hỏi|thắc mắc|hỏi như sau|"
    r"nội dung câu hỏi|bạn đọc.{0,50}hỏi\s*:?\s*$)", re.IGNORECASE)
# Cụm TÊN TỔ CHỨC hay bị nhận nhầm thành "văn bản" ở nguồn này (khoa/trường/báo
# của chuyên gia): "Khoa Luật Dân sự", "Trường ĐH Luật TP.HCM", "báo Pháp Luật
# TP.HCM"... -> xoá KHỎI BẢN SAO dùng để bóc trích dẫn (đáp án hiển thị giữ nguyên).
_RE_ORG = re.compile(
    r"(?:Khoa|Bộ môn|Trường|Trường Đại học|Đại học|ĐH|Học viện|Viện|Đoàn|báo|Báo)\s+"
    r"(?:Đại học\s+)?(?:Pháp\s+)?Luật\b[^,\n;]*", re.IGNORECASE)
# Trích dẫn RÁC còn sót từ tên trường/báo: "Luật TP.HCM", "Luật Hà Nội"...
_BAD_DOC = re.compile(r"^(?:bộ\s+)?luật\s+(?:tp|tp\.?\s*hcm|hà\s*nội|sài\s*gòn)\b", re.IGNORECASE)
# Độ dài đáp án tối thiểu để coi là "có nội dung text" (loại bài chỉ có video).
_MIN_ANSWER = 120


def _is_byline(p):
    """Dòng byline tác giả (toàn chữ HOA, ngắn) hoặc dòng chỉ có ngày giờ."""
    return (bool(p) and p == p.upper() and len(p) <= 40 and re.search(r"[A-ZĐÀ-Ỵ]", p)) \
        or bool(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}[\s\d:]*", p))


def parse_detail(html, fallback_title=""):
    """Parse trang chi tiết -> dict {tieu_de, cau_hoi, dap_an, van_ban_dan_chieu, trich_dan}.

    dap_an = "" nếu bài không có phần trả lời dạng text (vd bài chỉ có video)."""
    soup = BeautifulSoup(html, "lxml")
    for junk in soup.select("script, style, figure, table, ins, iframe, noscript, "
                            "related-content, .related-content, .VCSortableInPreviewMode, "
                            "[type=RelatedOneNews], [type=author], .author, .detail-author, "
                            ".article__author, .author-info, .vne-ads"):
        junk.decompose()

    h1 = soup.select_one("h1.article__title") or soup.select_one("h1")
    tieu_de = (h1.get_text(" ", strip=True) if h1 else fallback_title) or fallback_title

    sapo_el = soup.select_one(".article__sapo") or soup.select_one("[class*=sapo]")
    sapo = re.sub(r"^\(PLO\)\s*-?\s*", "", sapo_el.get_text(" ", strip=True)) if sapo_el else ""

    body = soup.select_one("[data-role=content]") or soup.select_one("[itemprop=articleBody]")
    paras = [p for p in block_text(body).split("\n") if p.strip()] if body else []
    paras = [p for p in paras if not _is_byline(p)]                 # bỏ byline/ngày giờ
    while paras and _RE_Q_INTRO.search(paras[0]):                   # bỏ boilerplate mở đầu
        paras.pop(0)

    # (1) Ưu tiên vạch "Bạn đọc ..." (kết thúc câu hỏi) — mốc chắc chắn nhất.
    sep = next((i for i, p in enumerate(paras) if _RE_BYLINE_SEP.match(p) and len(p) < 120), None)
    if sep is not None and sep + 1 < len(paras):
        cau_hoi = "\n".join(paras[:sep]).strip() or sapo
        dap_an = "\n".join(paras[sep + 1:]).strip()
    else:
        # (2) Mốc "(chức danh) ... (động từ trả lời)", bỏ qua lời khẩn của người hỏi.
        ans_idx = next((i for i, p in enumerate(paras)
                        if i >= 1 and _RE_ANS.search(p) and not _RE_PLEA.search(p)), None)
        if ans_idx is not None:
            cau_hoi = "\n".join(paras[:ans_idx]).strip() or sapo
            dap_an = "\n".join(paras[ans_idx:]).strip()
        else:
            cau_hoi = sapo
            dap_an = "\n".join(paras).strip()

    if len(dap_an) < _MIN_ANSWER:      # không có text trả lời -> để caller bỏ qua
        return {"tieu_de": tieu_de, "cau_hoi": cau_hoi, "dap_an": "",
                "van_ban_dan_chieu": [], "trich_dan": []}

    # Bóc trích dẫn trên bản sao đã XOÁ tên khoa/trường/báo -> tránh "văn bản" rác.
    docs, cites = extract_citations(body, _RE_ORG.sub(" ", dap_an))
    docs = [d for d in docs if not _BAD_DOC.match(d["ten"])]
    cites = [c for c in cites if not _BAD_DOC.match(c["van_ban"])]

    return {
        "tieu_de": tieu_de,
        "cau_hoi": cau_hoi,
        "dap_an": dap_an,
        "van_ban_dan_chieu": docs,
        "trich_dan": cites,
    }


def detect_zone(session, section_url):
    """Lấy zoneId (hdZoneId) từ trang chuyên mục để dựng URL timeline."""
    html = fetch(session, section_url)
    m = _RE_ZONE.search(html)
    if not m:
        raise RuntimeError(f"Không tìm thấy hdZoneId ở {section_url}")
    return m.group(1)


def crawl_section(session, name, section_url, args, records, done_urls, save, state):
    """Thu thập 1 chuyên mục PLO; nối kết quả vào `records` (chống trùng theo URL)."""
    zone = detect_zone(session, section_url)
    print(f"\n▶ Chuyên mục: {name}  (zone {zone})  {section_url}")
    collect_all = args.count <= 0
    page = 1
    while page <= args.max_pages:
        if not collect_all and len(records) >= args.count:
            break
        html = None
        for rnd in range(args.page_retries):
            try:
                html = fetch(session, TIMELINE_FMT.format(zone=zone, p=page), referer=section_url, xhr=True)
                break
            except Exception as e:
                cool = 20 * (rnd + 1)
                print(f"    ! trang {page} lỗi: {e} — nghỉ {cool}s rồi thử lại ({rnd + 1}/{args.page_retries})",
                      file=sys.stderr)
                time.sleep(cool)
        if html is None:
            print(f"    ! [{name}] trang {page} vẫn lỗi — bỏ dở mục này (checkpoint an toàn).", file=sys.stderr)
            break

        items = parse_list(html)
        if not items:
            print(f"    [{name}] trang {page}: 0 câu -> hết chuyên mục.")
            break

        new_items = [it for it in items if it["url"] not in done_urls]
        print(f"    [{name}] trang {page}: {len(items)} câu ({len(new_items)} mới) — tổng đã lưu: {len(records)}")

        for it in new_items:
            if not collect_all and len(records) >= args.count:
                break
            try:
                d = parse_detail(fetch(session, it["url"], referer=section_url), fallback_title=it["tieu_de"])
                if not d["dap_an"]:
                    print(f"        ! bỏ qua (video/không có text): {it['tieu_de'][:58]}", file=sys.stderr)
                    done_urls.add(it["url"])
                    continue
                records.append({
                    "linh_vuc": it["linh_vuc"], "nguon": SOURCE, "ngay": it["ngay"],
                    "tieu_de": d["tieu_de"] or it["tieu_de"], "cau_hoi": d["cau_hoi"],
                    "dap_an": d["dap_an"], "van_ban_dan_chieu": d["van_ban_dan_chieu"],
                    "trich_dan": d["trich_dan"], "url": it["url"],
                })
                done_urls.add(it["url"])
                state["new"] += 1
                if len(records) % max(1, args.save_every) == 0:
                    save(); print(f"        · đã lưu {len(records)} câu")
            except Exception as e:
                print(f"        ! lỗi câu {it['url']}: {e}", file=sys.stderr)
            time.sleep(args.delay)

        save()
        page += 1
        time.sleep(args.delay)


def main():
    ap = argparse.ArgumentParser(
        description="Thu thập hỏi - đáp pháp luật PLO (Chat với chuyên gia + Tôi muốn hỏi) -> JSON (mẫu 8 khoá).")
    ap.add_argument("--count", type=int, default=0, help="Số câu cần lấy; 0 = LẤY HẾT (mặc định)")
    ap.add_argument("--output", default="plo_hoidap_dataset.json", help="File JSON deliverable (8 khoá)")
    ap.add_argument("--sections", default="", help="Danh sách URL chuyên mục (phẩy ngăn cách); rỗng = cả 2 mục mặc định")
    ap.add_argument("--max-pages", type=int, default=1000, help="Số trang timeline tối đa mỗi mục (mặc định 1000)")
    ap.add_argument("--delay", type=float, default=1.0, help="Giây nghỉ giữa mỗi request (mặc định 1.0)")
    ap.add_argument("--page-retries", type=int, default=4, help="Số vòng thử lại 1 trang khi lỗi 502/chặn (mặc định 4)")
    ap.add_argument("--save-every", type=int, default=20, help="Ghi checkpoint sau mỗi N câu (mặc định 20)")
    ap.add_argument("--restart", action="store_true", help="Bỏ checkpoint, thu thập lại từ đầu")
    args = ap.parse_args()

    if args.sections.strip():
        sections = [(u.strip(), u.strip()) for u in args.sections.split(",") if u.strip()]
    else:
        sections = SECTIONS

    OUTPUT, CKPT = args.output, args.output + ".ckpt.json"
    records = []
    if os.path.exists(CKPT) and not args.restart:
        try:
            with open(CKPT, encoding="utf-8") as f:
                records = json.load(f).get("records", [])
            print(f"↻ Nạp checkpoint {CKPT}: đã có {len(records)} câu.")
        except Exception as e:
            print(f"! Không đọc được checkpoint ({e}), bắt đầu mới.", file=sys.stderr)
            records = []
    done_urls = {r.get("url") for r in records if r.get("url")}

    def save():
        _atomic_dump(CKPT, {"source": SOURCE, "total": len(records), "records": records})
        _atomic_dump(OUTPUT, [{k: r.get(k, "") for k in CLEAN_KEYS} for r in records])

    session = _cc_requests.Session() if _HAS_CURL_CFFI else None
    print(f"HTTP engine: {'curl_cffi' if _HAS_CURL_CFFI else 'urllib (fallback)'}  |  {len(sections)} chuyên mục")
    if done_urls:
        print(f"    ↻ đã có {len(done_urls)} câu, sẽ bỏ qua và thu phần còn thiếu / câu mới.")

    state = {"new": 0}
    try:
        for name, url in sections:
            if args.count > 0 and len(records) >= args.count:
                break
            crawl_section(session, name, url, args, records, done_urls, save, state)
        save()
        print(f"\nHoàn thành! Tổng {len(records)} câu (+{state['new']} mới lần chạy này).")
        print(f"  Deliverable (8 khoá): {OUTPUT}")
        print(f"  Checkpoint resume   : {CKPT}")
    except KeyboardInterrupt:
        save()
        print(f"\n■ Đã dừng. Đã lưu {len(records)} câu -> {OUTPUT}. Chạy lại lệnh cũ để thu TIẾP.", file=sys.stderr)


if __name__ == "__main__":
    main()
