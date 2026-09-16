# -*- coding: utf-8 -*-
"""
Thu thập INCREMENTAL các câu hỏi MỚI NHẤT từ luatvietnam.vn (chuyên mục Luật sư
tư vấn), chỉ lấy những câu CHƯA có trong luatvietnam_dataset.json.

Vì trang liệt kê mới-nhất-trước, script quét vài trang đầu của từng lĩnh vực,
lọc URL chưa có, tải chi tiết (dùng LẠI parser của main.py để trường 'reference'
đồng nhất), rồi merge vào dataset. Dừng sớm 1 lĩnh vực sau `patience` trang liên
tiếp không có câu mới (đã bắt kịp lần crawl trước).

Cách dùng:
    venv/Scripts/python.exe collect_incremental.py                 # tất cả lĩnh vực
    venv/Scripts/python.exe collect_incremental.py --max-pages 8
    venv/Scripts/python.exe collect_incremental.py --category giao-thong --category bao-hiem
"""
import argparse, json, os, sys, time, types

# --- Shim: chèn 'fastapi' giả để import main.py không dựng app thật ---
def _install_fastapi_shim():
    def ident_decorator(*a, **k):
        def deco(f): return f
        return deco
    class _App:
        def __init__(self, *a, **k): pass
        def add_middleware(self, *a, **k): pass
        def get(self, *a, **k): return ident_decorator()
        def post(self, *a, **k): return ident_decorator()
        def mount(self, *a, **k): pass
    def _passthru(*a, **k): return None
    fa = types.ModuleType("fastapi")
    fa.FastAPI = _App
    fa.Query = _passthru
    fa.Body = _passthru
    fa.Request = object
    sub_static = types.ModuleType("fastapi.staticfiles")
    sub_static.StaticFiles = lambda *a, **k: None
    sub_resp = types.ModuleType("fastapi.responses")
    sub_resp.StreamingResponse = object
    sub_resp.JSONResponse = lambda *a, **k: None
    sub_cors = types.ModuleType("fastapi.middleware.cors")
    sub_cors.CORSMiddleware = object
    sub_mw = types.ModuleType("fastapi.middleware")
    fa.staticfiles = sub_static
    fa.responses = sub_resp
    fa.middleware = sub_mw
    for name, mod in [("fastapi", fa), ("fastapi.staticfiles", sub_static),
                      ("fastapi.responses", sub_resp), ("fastapi.middleware", sub_mw),
                      ("fastapi.middleware.cors", sub_cors)]:
        sys.modules[name] = mod

_install_fastapi_shim()

from curl_cffi import requests
from main import (CATEGORIES, CATEGORY_BY_SLUG, category_page_url,
                  parse_question_list, parse_detail_page, IMPERSONATE, EXTRA_HEADERS)

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

MAX_RETRIES = 5
BACKOFF_BASE = 2.0
BACKOFF_CAP = 60.0


def fetch(session, url, referer=None):
    headers = dict(EXTRA_HEADERS)
    if referer:
        headers["Referer"] = referer
    for attempt in range(MAX_RETRIES + 1):
        r = session.get(url, headers=headers, timeout=30.0, impersonate=IMPERSONATE)
        if r.status_code in (429, 503) and attempt < MAX_RETRIES:
            ra = r.headers.get("Retry-After")
            wait = float(ra) if (ra and ra.isdigit()) else min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
            time.sleep(wait); continue
        r.raise_for_status()
        return r.text
    r.raise_for_status()
    return r.text


def main_run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="luatvietnam_dataset.json")
    ap.add_argument("--max-pages", type=int, default=6, help="Số trang tối đa quét mỗi lĩnh vực")
    ap.add_argument("--patience", type=int, default=2, help="Dừng lĩnh vực sau N trang liên tiếp không có câu mới")
    ap.add_argument("--category", action="append", help="Chỉ lĩnh vực này (slug), lặp lại được")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--new-output", default="luatvietnam_new_only.json", help="File chỉ chứa câu MỚI thu lần này")
    args = ap.parse_args()

    if not os.path.exists(args.output):
        print(f"! Không thấy {args.output}", file=sys.stderr); return
    dataset = json.load(open(args.output, encoding="utf-8"))
    cats_by_slug = {c["slug"]: c for c in dataset["categories"]}
    existing_urls = set()
    for c in dataset["categories"]:
        for q in c.get("questions", []):
            if q.get("url"): existing_urls.add(q["url"])
    print(f"↻ Dataset hiện có {len(existing_urls)} câu.")

    wanted = args.category or [c["slug"] for c in CATEGORIES]
    session = requests.Session()
    new_all = []

    def save():
        dataset["total_questions"] = sum(len(c.get("questions", [])) for c in dataset["categories"])
        tmp = args.output + ".tmp"
        json.dump(dataset, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        os.replace(tmp, args.output)

    for slug in wanted:
        cat = CATEGORY_BY_SLUG.get(slug)
        if not cat:
            print(f"  ! bỏ qua slug lạ: {slug}"); continue
        print(f"\n== {cat['name']} ({slug})")
        # gom link mới từ các trang đầu
        new_links, empty_streak = [], 0
        for page in range(1, args.max_pages + 1):
            try:
                html = fetch(session, category_page_url(cat, page), referer=category_page_url(cat, 1))
            except Exception as e:
                print(f"   ! lỗi trang {page}: {e}", file=sys.stderr); break
            links = parse_question_list(html)
            if not links:
                print(f"   trang {page}: hết câu."); break
            fresh = [l for l in links if l["url"] not in existing_urls and l["url"] not in {x['url'] for x in new_links}]
            print(f"   trang {page}: {len(links)} câu, {len(fresh)} mới")
            new_links.extend(fresh)
            empty_streak = empty_streak + 1 if not fresh else 0
            if empty_streak >= args.patience:
                print(f"   → {args.patience} trang liên tiếp không có câu mới, dừng lĩnh vực.")
                break
            time.sleep(args.delay)

        if not new_links:
            print("   (không có câu mới)"); continue

        # tải chi tiết
        entry = cats_by_slug.get(slug)
        if entry is None:
            entry = {"slug": slug, "name": cat["name"], "count": 0, "questions": [], "done": True}
            dataset["categories"].append(entry); cats_by_slug[slug] = entry
        print(f"   → tải chi tiết {len(new_links)} câu mới")
        for i, info in enumerate(new_links, 1):
            try:
                html = fetch(session, info["url"], referer=category_page_url(cat, 1))
                data = parse_detail_page(html, info["url"], listing_title=info["title"], listing_date=info.get("date", ""))
                if not data["answer"]:
                    print(f"      [{i}] bỏ (không có trả lời)"); continue
                entry["questions"].append(data)
                entry["count"] = len(entry["questions"])
                existing_urls.add(info["url"])
                new_all.append({**data, "linh_vuc": cat["name"]})
                save()
                print(f"      [{i}/{len(new_links)}] [{data['date'][-12:]}] {data['title'][:55]}")
            except Exception as e:
                print(f"      [{i}] lỗi: {e}", file=sys.stderr)
            time.sleep(args.delay)

    save()
    json.dump(new_all, open(args.new_output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nXong. Thu {len(new_all)} câu MỚI. Tổng dataset: {dataset['total_questions']} câu.")
    print(f"→ Câu mới lưu riêng: {args.new_output}")


if __name__ == "__main__":
    main_run()
