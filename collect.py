"""
Client thu thập dữ liệu từ endpoint /api/scrape của backend (main.py).

Nguồn: chuyên mục "Luật sư tư vấn" của luatvietnam.vn
(https://luatvietnam.vn/luat-su-tu-van.html). Với mỗi lĩnh vực trong CATEGORIES,
script gọi endpoint SSE /api/scrape?category=<slug>, đọc stream, gom các câu
hỏi lại, rồi gộp toàn bộ thành 1 file JSON hoàn chỉnh. Mặc định LẤY HẾT toàn bộ
câu hỏi của từng lĩnh vực (không lọc); dùng --count N nếu chỉ cần N câu.

Mỗi câu hỏi gồm: title (tiêu đề), question (câu hỏi người dùng gửi luật sư,
đã bỏ câu chào "Xin hỏi LuatVietnam:"), answer (bài trả lời đã dọn boilerplate),
author, date, url, reference.

Cách dùng:
    1. Chạy backend trước:   python main.py       (mặc định http://localhost:8000)
    2. Chạy script này:      python collect.py    (lấy hết ~2.000 câu, mất ~1 giờ)

Tùy chọn:
    python collect.py --count 20 --output data.json --base-url http://localhost:8000
    python collect.py --category hinh-su          # chỉ 1 lĩnh vực (lặp lại được)

Checkpoint / tiếp tục:
    File --output chính là checkpoint, được ghi ATOMIC sau MỖI câu hỏi. Nếu bị
    tắt giữa chừng (Ctrl+C, mất điện...), chỉ cần chạy LẠI đúng lệnh cũ:
    - Lĩnh vực đã "done" -> bỏ qua.
    - Lĩnh vực đang dở  -> GIỮ các câu đã thu, gửi danh sách URL đã có lên
      server để chỉ cào TIẾP những câu còn thiếu (resume đến từng câu).
    Dùng --restart để bỏ checkpoint và thu thập lại từ đầu.
"""

import argparse
import json
import os
import sys
import time

from curl_cffi import requests

from main import CATEGORIES

# Console Windows mặc định có thể dùng cp1252 -> in tiếng Việt bị lỗi. Ép UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def scrape_category(base_url: str, category: dict, count: int,
                    randomize: bool = True, pool_pages: int = 15,
                    exclude_urls=None, on_question=None) -> list:
    """Gọi endpoint SSE và trả về danh sách câu hỏi thu được cho 1 lĩnh vực.

    `exclude_urls`: các URL đã thu từ checkpoint -> server bỏ qua, chỉ cào phần
    còn thiếu (resume giữa chừng lĩnh vực). `count` là số câu cần thu THÊM.
    `on_question(question_dict)` (nếu có) được gọi ngay sau mỗi câu hỏi thu được
    -> dùng để ghi checkpoint từng câu, không mất tiến độ nếu bị gián đoạn.
    """
    url = f"{base_url}/api/scrape"
    body = {
        "category": category["slug"],
        "count": count,
        "randomize": randomize,
        "pool_pages": pool_pages,
        # Danh sách URL đã có -> gửi qua body JSON (quá dài cho query string).
        "exclude_urls": sorted(exclude_urls or []),
    }

    questions = []
    total = count

    # stream=True để đọc SSE theo từng dòng ngay khi server đẩy về.
    resp = requests.post(url, json=body, stream=True, timeout=None)
    try:
        resp.raise_for_status()

        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data:"):
                continue

            payload = json.loads(line[len("data:"):].strip())
            etype = payload.get("type")

            if etype == "total":
                total = payload.get("total", count)
                print(f"    → server báo tổng {total} câu hỏi")
            elif etype == "progress":
                msg = payload.get("message", "")
                print(f"    [{payload.get('current')}/{payload.get('total')}] {msg[:70]}")
            elif etype == "question":
                q = payload["data"]
                questions.append(q)
                if on_question:
                    on_question(q)          # ghi checkpoint ngay sau mỗi câu
            elif etype == "error":
                print(f"    ! lỗi: {payload.get('message')}", file=sys.stderr)
            elif etype == "done":
                print(f"    ✓ {payload.get('message')}")
                break
    finally:
        # Đóng kết nối NGAY cả khi bị Ctrl+C giữa chừng -> server phát hiện
        # client ngắt và dừng cào, không chạy ngầm tiếp.
        resp.close()

    return questions


def main():
    parser = argparse.ArgumentParser(description="Thu thập câu hỏi từ backend luatvietnam.vn và gộp thành 1 file JSON.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL backend (mặc định http://localhost:8000)")
    parser.add_argument("--count", type=int, default=0, help="Số câu hỏi mỗi lĩnh vực; 0 = LẤY HẾT (mặc định)")
    parser.add_argument("--all", action="store_true", help="Lấy HẾT câu hỏi mỗi lĩnh vực (tương đương --count 0, giữ để tương thích)")
    parser.add_argument("--output", default="luatvietnam_dataset.json", help="File JSON đầu ra")
    parser.add_argument("--category", action="append", help="Chỉ thu thập lĩnh vực này (slug). Lặp lại để chọn nhiều lĩnh vực.")
    parser.add_argument("--delay", type=float, default=5.0, help="Số giây nghỉ giữa mỗi lĩnh vực để tránh 429 (mặc định 5s)")
    parser.add_argument("--pool-pages", type=int, default=15, help="Số trang tối đa quét để tạo pool chọn ngẫu nhiên (mặc định 15, mỗi trang 50 câu)")
    parser.add_argument("--no-random", action="store_true", help="Lấy các câu đầu tiên thay vì ngẫu nhiên (chỉ có tác dụng khi --count > 0)")
    parser.add_argument("--restart", action="store_true", help="Bỏ qua checkpoint, thu thập lại từ đầu (ghi đè file output)")
    args = parser.parse_args()

    # Chọn danh sách lĩnh vực cần thu thập.
    if args.category:
        wanted = set(args.category)
        categories = [c for c in CATEGORIES if c["slug"] in wanted]
        missing = wanted - {c["slug"] for c in categories}
        if missing:
            print(f"Cảnh báo: không tìm thấy slug: {', '.join(missing)}", file=sys.stderr)
    else:
        categories = CATEGORIES

    # count=0 báo cho backend LẤY HẾT câu hỏi của lĩnh vực.
    count = 0 if args.all else args.count

    # --- Nạp checkpoint (nếu có) ---
    dataset = None
    if os.path.exists(args.output) and not args.restart:
        try:
            with open(args.output, encoding="utf-8") as f:
                dataset = json.load(f)
            done = [c["slug"] for c in dataset.get("categories", []) if c.get("done")]
            print(f"↻ Nạp checkpoint {args.output}: đã xong {len(done)} lĩnh vực.")
        except Exception as e:
            print(f"! Không đọc được checkpoint ({e}), bắt đầu mới.", file=sys.stderr)
            dataset = None

    if dataset is None:
        dataset = {
            "source": "luatvietnam.vn",
            "questions_per_category": "all" if args.all else args.count,
            "total_categories": len(categories),
            "total_questions": 0,
            "categories": [],
        }

    def save():
        """Ghi checkpoint ATOMIC: ghi file tạm rồi thay thế, để nếu bị tắt đúng
        lúc đang ghi thì file cũ vẫn nguyên vẹn (không bao giờ hỏng checkpoint)."""
        dataset["total_questions"] = sum(len(c.get("questions", [])) for c in dataset["categories"])
        tmp = args.output + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)
        os.replace(tmp, args.output)

    done_slugs = {c["slug"] for c in dataset["categories"] if c.get("done")}

    for idx, category in enumerate(categories, 1):
        slug = category["slug"]
        header = f"[{idx}/{len(categories)}] {category['name']} ({slug})"

        # Lĩnh vực đã xong ở lần chạy trước -> bỏ qua.
        if slug in done_slugs:
            print(f"{header} — ✓ đã xong (checkpoint), bỏ qua")
            continue
        print(header)

        # Lấy lại entry dở dang từ checkpoint (GIỮ NGUYÊN các câu đã thu) hoặc
        # tạo mới nếu lĩnh vực chưa từng được thu.
        entry = next((c for c in dataset["categories"] if c["slug"] == slug), None)
        if entry is None:
            entry = {"slug": slug, "name": category["name"], "count": 0, "questions": [], "done": False}
            dataset["categories"].append(entry)
        existing_urls = {q["url"] for q in entry["questions"] if q.get("url")}
        if existing_urls:
            print(f"    ↻ checkpoint: đã có {len(existing_urls)} câu, thu tiếp phần còn thiếu")

        # Có giới hạn --count: chỉ cần thu THÊM phần còn thiếu so với checkpoint.
        need = count
        if count > 0:
            need = count - len(entry["questions"])
            if need <= 0:
                entry["done"] = True
                save()
                print(f"    ✓ đã đủ {len(entry['questions'])} câu từ checkpoint, bỏ qua")
                continue

        save()   # ghi ngay -> checkpoint biết đang tải lĩnh vực này

        def on_question(q, _entry=entry):
            _entry["questions"].append(q)
            _entry["count"] = len(_entry["questions"])
            save()   # lưu sau MỖI câu -> không mất tiến độ nếu bị tắt

        try:
            scrape_category(
                args.base_url, category, need,
                randomize=not args.no_random,
                pool_pages=args.pool_pages,
                exclude_urls=existing_urls,
                on_question=on_question,
            )
            entry["done"] = True     # đánh dấu lĩnh vực hoàn tất
            save()
            print(f"    ✓ xong {entry['count']} câu, đã lưu checkpoint")
        except KeyboardInterrupt:
            save()
            print(f"\n■ Đã dừng. Checkpoint lưu tại {args.output} "
                  f"({entry['count']} câu lĩnh vực này). Chạy lại lệnh cũ để "
                  f"thu TIẾP từ chỗ dừng, không làm lại từ đầu.", file=sys.stderr)
            return
        except Exception as e:
            save()
            print(f"    ! lỗi lĩnh vực (chưa xong, chạy lại sẽ thu tiếp phần thiếu): {e}", file=sys.stderr)

        # Nghỉ giữa các lĩnh vực để giãn tải request tới trang gốc (tránh 429).
        if idx < len(categories):
            print(f"    … nghỉ {args.delay:g}s trước lĩnh vực tiếp theo")
            try:
                time.sleep(args.delay)
            except KeyboardInterrupt:
                save()
                print(f"\n■ Đã dừng. Checkpoint lưu tại {args.output}. "
                      f"Chạy lại lệnh này để tải tiếp từ lĩnh vực đang dở.", file=sys.stderr)
                return

    save()
    done_count = sum(1 for c in dataset["categories"] if c.get("done"))
    print(f"\nHoàn thành! Đã lưu {dataset['total_questions']} câu hỏi, "
          f"{done_count}/{len(categories)} lĩnh vực xong -> {args.output}")


if __name__ == "__main__":
    main()
