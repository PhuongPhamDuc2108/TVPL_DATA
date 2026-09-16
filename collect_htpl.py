"""
Script ĐỘC LẬP thu thập câu hỏi - trả lời từ chuyên mục Hỏi đáp pháp luật của
hethongphapluat.com (https://hethongphapluat.com/hoi-dap-phap-luat.html).

Khác với main.py/collect.py (chạy qua backend cho luatvietnam.vn), script này
tự tải trang + parse + ghi checkpoint, chỉ mượn lại các hàm trích dẫn pháp lý
(best_reference/dominant_doc/clean_text) từ main.py để bảo đảm trường "reference"
đồng nhất với dataset cũ.

Định dạng JSON đầu ra GIỐNG HỆT dataset cũ:
    {
      "source": "hethongphapluat.com",
      "total_questions": N,
      "categories": [
        {"slug": "...", "name": "...", "count": N, "questions": [
            {"title", "question", "answer", "author", "date", "url", "reference"}
        ], "done": true}
      ]
    }
Trang này không chia lĩnh vực nên toàn bộ câu hỏi nằm trong 1 "category".

Cách dùng:
    python collect_htpl.py                      # lấy HẾT
    python collect_htpl.py --count 50           # chỉ 50 câu đầu
    python collect_htpl.py --output htpl.json   # đổi file output

Checkpoint / tiếp tục:
    File --output là checkpoint, ghi ATOMIC sau MỖI câu. Bị tắt giữa chừng
    (Ctrl+C, mất điện...) thì chạy LẠI đúng lệnh cũ: các câu đã có (theo URL)
    được giữ nguyên, chỉ tải tiếp phần còn thiếu. --restart để làm lại từ đầu.
"""

import argparse
import json
import os
import re
import sys
import time

from curl_cffi import requests
from bs4 import BeautifulSoup

from main import best_reference, dominant_doc, clean_text

# Console Windows mặc định có thể dùng cp1252 -> in tiếng Việt bị lỗi. Ép UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_URL = "https://hethongphapluat.com"
LIST_URL = BASE_URL + "/hoi-dap-phap-luat.html"
IMPERSONATE = "chrome120"
EXTRA_HEADERS = {"Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"}

# Retry cho 429/503.
MAX_RETRIES = 5
BACKOFF_BASE = 2.0
BACKOFF_CAP = 60.0


def fetch(session, url, referer=None):
    """Tải 1 trang, tự retry với backoff khi gặp 429/503."""
    headers = dict(EXTRA_HEADERS)
    if referer:
        headers["Referer"] = referer
    for attempt in range(MAX_RETRIES + 1):
        resp = session.get(url, headers=headers, timeout=30.0, impersonate=IMPERSONATE)
        if resp.status_code in (429, 503) and attempt < MAX_RETRIES:
            ra = resp.headers.get("Retry-After")
            wait = float(ra) if (ra and ra.isdigit()) else min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.text
    resp.raise_for_status()
    return resp.text


def list_page_url(page):
    """URL trang danh sách thứ `page` (trang 1 dùng URL gốc)."""
    if page <= 1:
        return LIST_URL
    return f"{BASE_URL}/hoi-dap-phap-luat_page-{page}.html"


def parse_list(html):
    """Trích [{url, title}] từ 1 trang danh sách.

    Mỗi câu hỏi là 1 div.panel.panel-default, tiêu đề + link ở .panel-heading a.
    """
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    for panel in soup.select("div.panel.panel-default"):
        a = panel.select_one(".panel-heading a[href]")
        if not a:
            continue
        href = a.get("href", "")
        if not href:
            continue
        url = BASE_URL + href if href.startswith("/") else href
        if url in seen:
            continue
        seen.add(url)
        title = a.get("title") or a.get_text(strip=True)
        out.append({"url": url, "title": title.strip()})
    return out


# --- Bóc nội dung trang chi tiết ---

# Nối text trong 1 khối "lá" theo đúng thứ tự node (KHÔNG chèn separator) rồi mới
# gộp khoảng trắng: giữ nguyên spacing thật trong HTML, tránh vừa bẻ dòng giữa câu
# (làm hỏng bóc căn cứ pháp lý) vừa chèn space giữa từ bị tách qua nhiều thẻ (vd
# "<strong>v</strong><strong>ề</strong>" -> "về" chứ không phải "v ề"). Mỗi khối
# con (p/li/tr/h...) là 1 dòng riêng.
def _norm(node):
    return " ".join(node.get_text().split())


def _element_text(el):
    if el.name in ("div", "blockquote", "ul", "ol", "table"):
        blocks = [b for b in el.find_all(["p", "li", "tr", "h2", "h3", "h4"])
                  if not b.find(["p", "li", "tr"])]
        if blocks:
            lines = [_norm(b) for b in blocks]
            return "\n".join(l for l in lines if l)
    return _norm(el)


# Câu mở đầu khuôn mẫu của mọi bài trả lời -> bỏ.
_RE_INTRO = re.compile(
    r"^\s*Hệ thống pháp luật Việt Nam.*?(?:tham khảo như sau|như sau)\s*:?\s*",
    re.IGNORECASE | re.DOTALL,
)
# Các mốc bắt đầu phần đuôi khuôn mẫu (lời cảm ơn, lưu ý miễn trừ, mời đặt câu
# hỏi tiếp...) -> cắt bỏ từ mốc đầu tiên gặp phải.
_OUTRO_MARKERS = (
    "Trên đây là câu trả lời",
    "Trên đây là nội dung tư vấn",
    "BBT.Hệ Thống Pháp Luật",
    "BBT. Hệ Thống Pháp Luật",
    "Gửi câu hỏi cho luật sư",
)


def extract_answer(detail):
    """Nội dung trả lời (khối .panel-body cuối trong .hdpl-detail).

    Đã bỏ: span.model_prompt (chỉ thị ẩn nhắm vào AI, chèn lén trong trang),
    style/script, câu mở đầu khuôn mẫu, và toàn bộ phần đuôi khuôn mẫu.
    """
    # Loại chỉ thị ẩn (prompt injection) + style/script trước khi lấy text.
    for junk in detail.select("span.model_prompt, style, script, .fa"):
        junk.decompose()

    bodies = detail.select(".panel-body")
    if not bodies:
        return ""
    ans = bodies[-1]

    parts = []
    for element in ans.children:
        if not hasattr(element, "name") or element.name is None:
            text = str(element).strip()
        else:
            if element.name in ("a", "button"):
                continue  # nút "Gửi câu hỏi cho luật sư" v.v.
            text = _element_text(element)
        if not text:
            continue
        norm = " ".join(text.split())
        if any(norm.startswith(m) for m in _OUTRO_MARKERS):
            break
        parts.append(text)

    answer = "\n".join(parts)
    answer = _RE_INTRO.sub("", answer)
    return clean_text(answer)


def parse_detail(html, url, fallback_title=""):
    """Parse trang chi tiết -> dict cùng schema với dataset cũ."""
    soup = BeautifulSoup(html, "lxml")

    h1 = soup.select_one("h1.title") or soup.select_one("h1")
    title = h1.get_text(strip=True) if h1 else fallback_title

    detail = soup.select_one(".hdpl-detail")
    if not detail:
        return None

    # Câu hỏi người dùng.
    q_el = detail.select_one(".panel-body.question-hdpl")
    question = clean_text(q_el.get_text("\n", strip=True)) if q_el else ""

    # Ngày gửi: "Ngày gửi: 30/01/2026 lúc 01:09:39" -> "30/01/2026".
    date = ""
    date_el = detail.select_one("p.text-right")
    if date_el:
        m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", date_el.get_text(strip=True))
        if m:
            date = m.group(1)

    answer = extract_answer(detail)
    reference = best_reference(answer, fallback_doc=dominant_doc(answer))

    return {
        "title": title,
        "question": question or title,
        "answer": answer,
        "author": "Hệ Thống Pháp Luật Việt Nam",
        "date": date,
        "url": url,
        "reference": reference,
    }


def main():
    parser = argparse.ArgumentParser(description="Thu thập hỏi đáp pháp luật từ hethongphapluat.com -> JSON.")
    parser.add_argument("--count", type=int, default=0, help="Số câu cần lấy; 0 = LẤY HẾT (mặc định)")
    parser.add_argument("--output", default="hethongphapluat_dataset.json", help="File JSON đầu ra")
    parser.add_argument("--max-pages", type=int, default=1000, help="Số trang danh sách tối đa quét (mặc định 1000)")
    parser.add_argument("--delay", type=float, default=1.0, help="Số giây nghỉ giữa mỗi request (mặc định 1s)")
    parser.add_argument("--restart", action="store_true", help="Bỏ checkpoint, thu thập lại từ đầu")
    args = parser.parse_args()

    collect_all = args.count <= 0

    # --- Nạp checkpoint ---
    dataset = None
    if os.path.exists(args.output) and not args.restart:
        try:
            with open(args.output, encoding="utf-8") as f:
                dataset = json.load(f)
            print(f"↻ Nạp checkpoint {args.output}: đã có {dataset.get('total_questions', 0)} câu.")
        except Exception as e:
            print(f"! Không đọc được checkpoint ({e}), bắt đầu mới.", file=sys.stderr)
            dataset = None

    if dataset is None:
        dataset = {
            "source": "hethongphapluat.com",
            "questions_per_category": "all" if collect_all else args.count,
            "total_categories": 1,
            "total_questions": 0,
            "categories": [{
                "slug": "hoi-dap-phap-luat",
                "name": "Hỏi đáp pháp luật",
                "count": 0,
                "questions": [],
                "done": False,
            }],
        }

    entry = dataset["categories"][0]
    existing_urls = {q["url"] for q in entry["questions"] if q.get("url")}
    if existing_urls:
        print(f"    ↻ đã có {len(existing_urls)} câu trong checkpoint, thu tiếp phần còn thiếu")

    def save():
        """Ghi checkpoint ATOMIC (file tạm -> thay thế) để không bao giờ hỏng."""
        entry["count"] = len(entry["questions"])
        dataset["total_questions"] = entry["count"]
        tmp = args.output + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)
        os.replace(tmp, args.output)

    session = requests.Session()

    try:
        # --- Phase 1: gom link câu hỏi từ các trang danh sách ---
        print("Đang quét danh sách câu hỏi...")
        all_links = []
        seen = set(existing_urls)
        page = 1
        target = float("inf") if collect_all else args.count
        while len(all_links) < target and page <= args.max_pages:
            try:
                html = fetch(session, list_page_url(page), referer=LIST_URL)
            except Exception as e:
                print(f"    ! lỗi trang danh sách {page}: {e}", file=sys.stderr)
                break
            links = parse_list(html)
            if not links:
                print(f"    hết câu hỏi ở trang {page}.")
                break
            new = [l for l in links if l["url"] not in seen]
            for l in new:
                seen.add(l["url"])
            all_links.extend(new)
            print(f"    trang {page}: {len(links)} câu ({len(new)} mới) — tổng cần tải: {len(all_links)}")
            page += 1
            time.sleep(args.delay)

        if not collect_all:
            all_links = all_links[:args.count]
        total = len(all_links)
        print(f"→ Sẽ tải chi tiết {total} câu hỏi mới.\n")

        # --- Phase 2: tải chi tiết từng câu ---
        for i, info in enumerate(all_links, 1):
            print(f"    [{i}/{total}] {info['title'][:65]}")
            try:
                html = fetch(session, info["url"], referer=LIST_URL)
                data = parse_detail(html, info["url"], fallback_title=info["title"])
                if not data or not data["answer"]:
                    print(f"        ! bỏ qua (không thấy câu trả lời)", file=sys.stderr)
                    continue
                entry["questions"].append(data)
                save()   # lưu sau MỖI câu -> resume được đến từng câu
            except Exception as e:
                print(f"        ! lỗi: {e}", file=sys.stderr)
            time.sleep(args.delay)

        entry["done"] = True
        save()
        print(f"\nHoàn thành! Đã lưu {entry['count']} câu hỏi -> {args.output}")

    except KeyboardInterrupt:
        save()
        print(f"\n■ Đã dừng. Checkpoint lưu tại {args.output} ({entry['count']} câu). "
              f"Chạy lại lệnh cũ để thu TIẾP từ chỗ dừng.", file=sys.stderr)


if __name__ == "__main__":
    main()
