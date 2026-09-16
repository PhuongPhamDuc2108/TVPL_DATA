# -*- coding: utf-8 -*-
"""
Tách CĂN CỨ PHÁP LÝ từ đoạn trả lời bằng LLM (Google Gemini API).
Đầu vào: câu trả lời (dap_an). Đầu ra: van_ban_dan_chieu + trich_dan CHUẨN
(tên văn bản gọn, đúng, không thừa/thiếu), ép theo JSON schema.

CHUẨN BỊ:
  - Lấy API key tại https://aistudio.google.com/apikey
  - Điền key vào file .env ở thư mục gốc (copy từ .env.example):
        GEMINI_API_KEY=xxxxx
    Hoặc đặt biến môi trường:  (cmd)        set GEMINI_API_KEY=xxxxx
                               (PowerShell) $env:GEMINI_API_KEY="xxxxx"
  - (tuỳ chọn) đổi model: set GEMINI_MODEL=gemini-2.5-flash

DÙNG:
  # Test 1 đoạn:
  python trich_dan_llm.py --text "Theo khoản 2 Điều 10 Nghị định 100/2019/NĐ-CP..."

  # Tách cả file dataset (thay van_ban_dan_chieu/trich_dan, giữ link theo số hiệu):
  python trich_dan_llm.py plo_hoidap_dataset.json
  python trich_dan_llm.py chinhsachonline_dataset.json --workers 6 --delay 0.2
  python trich_dan_llm.py plo_hoidap_dataset.json --limit 20 --out thu.json   # thử 20 câu

Có CACHE (<file>.llm_cache.json theo md5 của dap_an) -> chạy lại/nghẽn giữa chừng
không gọi lại API, chỉ làm phần còn thiếu.
"""
import argparse, collections, hashlib, json, os, re, sys, time, threading
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

import env_config  # noqa: F401  nạp .env trước khi đọc os.environ

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemma-4-31b-it")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Schema ép đầu ra (định dạng REST của Gemini: type VIẾT HOA).
_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "van_ban_dan_chieu": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "ten": {"type": "STRING"}, "so_hieu": {"type": "STRING"}}}},
        "trich_dan": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "van_ban": {"type": "STRING"}, "so_hieu": {"type": "STRING"},
            "dieu": {"type": "STRING"}, "khoan": {"type": "STRING"}, "diem": {"type": "STRING"},
            "trich_dan_goc": {"type": "STRING"}}}},
    },
    "required": ["van_ban_dan_chieu", "trich_dan"],
}

_PROMPT = """Bạn là trợ lý pháp lý người Việt. Từ ĐOẠN TRẢ LỜI dưới đây, hãy tách CHÍNH XÁC các căn cứ pháp lý được viện dẫn.

QUY TẮC:
1) van_ban_dan_chieu: liệt kê MỖI văn bản pháp luật được nhắc tới ĐÚNG MỘT LẦN:
   - ten: TÊN CHUẨN, NGẮN GỌN. TUYỆT ĐỐI không kèm mệnh đề mô tả phía sau.
     Ví dụ đúng: "Luật Giao thông đường bộ", "Nghị định 100/2019/NĐ-CP", "Bộ luật Dân sự 2015".
     Ví dụ SAI (thừa): "Luật Giao thông đường bộ) điều khiển xe...", "Luật BHYT, đã được sửa đổi...".
     Giữ NĂM nếu văn bản có ghi năm; giữ tên viết tắt nếu đoạn dùng viết tắt (vd "Luật BHYT").
   - so_hieu: số hiệu nếu có (vd "100/2019/NĐ-CP"), không có thì "".
2) trich_dan: MỖI lần viện dẫn một Điều/Khoản/Điểm cụ thể tạo 1 mục:
   - van_ban: tên chuẩn của văn bản chứa điều/khoản đó (như quy tắc 1)
   - so_hieu: nếu có
   - dieu / khoan / diem: CHỈ phần số hoặc chữ (dieu="10", khoan="2", diem="a"); không có thì "".
   - trich_dan_goc: cụm chữ nguyên văn trong đoạn (vd "khoản 2 Điều 10 Nghị định 100/2019/NĐ-CP").
3) CHỈ tách những gì THỰC SỰ có trong đoạn. KHÔNG bịa, KHÔNG thừa, KHÔNG thiếu.
4) Nếu đoạn không viện dẫn văn bản nào, trả về hai mảng rỗng.
5) CHỈ trả về DUY NHẤT một JSON đúng cấu trúc sau (không markdown, không giải thích thêm):
{"van_ban_dan_chieu":[{"ten":"","so_hieu":""}],"trich_dan":[{"van_ban":"","so_hieu":"","dieu":"","khoan":"","diem":"","trich_dan_goc":""}]}

ĐOẠN TRẢ LỜI:
\"\"\"
{text}
\"\"\""""

_RETRY_STATUS = (429, 500, 502, 503, 504)

# Gemma qua Gemini API thường KHÔNG nhận responseSchema/responseMimeType.
# Thử lần lượt từ "xịn" -> "trơn"; nhớ config chạy được để dùng cho các call sau.
_CONFIGS = [
    {"responseMimeType": "application/json", "responseSchema": _SCHEMA, "temperature": 0},
    {"responseMimeType": "application/json", "temperature": 0},
    {"temperature": 0},
]
_cfg = [2 if "gemma" in MODEL.lower() else 0]   # Gemma không hỗ trợ responseSchema -> dùng config trơn


def _parse_json(s):
    """Bóc JSON kể cả khi model bọc ```json ... ``` hoặc kèm chữ thừa."""
    s = (s or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except Exception:
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            return json.loads(s[a:b + 1])
        raise


def extract_citations_llm(text, api_key=None, model=None, timeout=300, retries=5):
    """Gọi model, trả {van_ban_dan_chieu, trich_dan}."""
    key = api_key or API_KEY
    if not key:
        raise RuntimeError("Chưa có GEMINI_API_KEY - điền vào file .env ở thư mục "
                           "gốc dự án (copy từ .env.example).")
    if not (text or "").strip():
        return {"van_ban_dan_chieu": [], "trich_dan": []}
    prompt = _PROMPT.replace("{text}", text)
    url = ENDPOINT.format(model=model or MODEL) + "?key=" + key
    last = None
    for attempt in range(retries + 1):
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": _CONFIGS[_cfg[0]]}
        payload = json.dumps(body).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            parts = resp["candidates"][0]["content"].get("parts", [])
            # BỎ các part "thought" (Gemma là model suy luận) — chỉ lấy phần trả lời.
            txt = "".join(p.get("text", "") for p in parts if p.get("text") and not p.get("thought"))
            out = _parse_json(txt)
            return {"van_ban_dan_chieu": out.get("van_ban_dan_chieu") or [],
                    "trich_dan": out.get("trich_dan") or []}
        except urllib.error.HTTPError as e:
            msg = e.read()[:400].decode("utf-8", "replace")
            last = f"HTTP {e.code}: {msg}"
            if e.code == 400 and _cfg[0] < len(_CONFIGS) - 1 and \
               re.search(r"responseSchema|responseMimeType|not supported|Unknown name|Invalid", msg, re.I):
                _cfg[0] += 1  # model không nhận config này -> hạ cấp rồi thử lại
                continue
            if e.code in _RETRY_STATUS and attempt < retries:
                time.sleep(min(2 ** attempt, 30)); continue
            raise RuntimeError(last)
        except (urllib.error.URLError, KeyError, IndexError, ValueError) as e:
            last = repr(e)
            if attempt < retries:
                time.sleep(min(2 ** attempt, 30)); continue
            raise RuntimeError(last)
    raise RuntimeError(last or "unknown")


class RateLimiter:
    """Giới hạn theo CẢ số request/phút (rpm) LẪN token/phút (tpm) — cửa sổ trượt 60s."""
    def __init__(self, rpm, tpm):
        self.rpm, self.tpm = rpm, tpm
        self.ev = collections.deque()   # (timestamp, tokens)
        self.lock = threading.Lock()

    def acquire(self, tokens):
        while True:
            with self.lock:
                now = time.time()
                while self.ev and now - self.ev[0][0] >= 60:
                    self.ev.popleft()
                cnt = len(self.ev)
                tok = sum(e[1] for e in self.ev)
                if (self.rpm <= 0 or cnt + 1 <= self.rpm) and (self.tpm <= 0 or tok + tokens <= self.tpm):
                    self.ev.append((now, tokens))
                    return
                wait = 60 - (now - self.ev[0][0]) if self.ev else 1.0
            time.sleep(max(0.2, min(wait, 5)))


def _est_tokens(text):
    """Ước lượng token 1 request (prompt + đầu ra). Tiếng Việt ~ 1 token / 3 ký tự."""
    return len(_PROMPT.replace("{text}", text or "")) // 3 + 900   # +900: Gemma tốn token "suy luận"


def _links_of(rec):
    """Bản đồ số hiệu -> link từ dữ liệu gốc (để gắn lại sau khi LLM tách)."""
    m = {}
    for v in (rec.get("van_ban_dan_chieu") or []):
        if v.get("so_hieu") and v.get("link"):
            m.setdefault(v["so_hieu"], v["link"])
    for c in (rec.get("trich_dan") or []):
        if c.get("so_hieu") and c.get("link"):
            m.setdefault(c["so_hieu"], c["link"])
    return m


def _attach_links(res, link_map):
    for v in res["van_ban_dan_chieu"]:
        v["link"] = link_map.get(v.get("so_hieu", ""), "")
    for c in res["trich_dan"]:
        c["link"] = link_map.get(c.get("so_hieu", ""), "")
    return res


def _hash(t):
    return hashlib.md5((t or "").encode("utf-8")).hexdigest()


def _atomic(path, obj, indent=None):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def process_file(fp, args):
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    if args.limit:
        data = data[:args.limit]
    out = args.out or fp
    cache_path = fp + ".llm_cache.json"
    cache = {}
    if os.path.exists(cache_path):
        try: cache = json.load(open(cache_path, encoding="utf-8"))
        except Exception: cache = {}

    def save_output():
        """Ghép cache vào data (giữ link theo số hiệu) rồi ghi file .json."""
        n_ok = 0
        for r in data:
            c = cache.get(_hash(r.get("dap_an") or ""))
            if c:
                res = {"van_ban_dan_chieu": [dict(v) for v in c["van_ban_dan_chieu"]],
                       "trich_dan": [dict(x) for x in c["trich_dan"]]}
                _attach_links(res, _links_of(r))
                r["van_ban_dan_chieu"] = res["van_ban_dan_chieu"]
                r["trich_dan"] = res["trich_dan"]
                n_ok += 1
        _atomic(out, data, indent=2)
        return n_ok

    todo = [(i, r) for i, r in enumerate(data)
            if (r.get("dap_an") or "").strip() and _hash(r["dap_an"]) not in cache]
    total = len(todo)
    print(f"{fp}: {len(data)} câu | đã cache {len(data)-total} | cần gọi LLM {total}")
    if not total:
        n = save_output(); print(f"✓ {out}: đủ từ cache ({n} câu)."); return
    print(f"   giới hạn {args.rpm} req/phút · {args.tpm} token/phút · {args.workers} luồng — Ctrl+C để dừng.\n")

    limiter = RateLimiter(args.rpm, args.tpm)

    def do_one(item):
        i, r = item
        limiter.acquire(_est_tokens(r["dap_an"]))
        try:
            return i, r, extract_citations_llm(r["dap_an"], model=args.model), None
        except Exception as e:
            return i, r, None, str(e)

    n = 0
    ex = ThreadPoolExecutor(max_workers=args.workers)
    futs = [ex.submit(do_one, it) for it in todo]
    try:
        for fut in as_completed(futs):
            i, r, res, err = fut.result()
            n += 1
            tt = (r.get("tieu_de") or "")[:50]
            if err:
                print(f"[{n}/{total}] ✗ LỖI câu {i}: {err[:90]}")
                continue
            cache[_hash(r["dap_an"])] = res
            _atomic(cache_path, cache)                 # checkpoint: lưu ngay mỗi câu
            vb = " · ".join(v.get("ten", "") for v in res["van_ban_dan_chieu"][:3])
            print(f"[{n}/{total}] {tt}  →  {len(res['van_ban_dan_chieu'])} VB / {len(res['trich_dan'])} trích dẫn"
                  + (f"  | {vb[:58]}" if vb else ""))
            if n % args.save_every == 0:
                save_output()
    except KeyboardInterrupt:
        print("\n■ Ctrl+C — dừng, đang lưu tiến độ...")
        ex.shutdown(wait=False, cancel_futures=True)
        save_output()
        print(f"■ Đã lưu {out} + checkpoint {cache_path}. Chạy lại lệnh cũ để thu tiếp.")
        return
    ex.shutdown(wait=True)
    n_ok = save_output()
    nvb = sum(len(r.get("van_ban_dan_chieu", [])) for r in data)
    ntd = sum(len(r.get("trich_dan", [])) for r in data)
    print(f"\n✓ {out}: {n_ok} câu — {nvb} văn bản, {ntd} trích dẫn.")


def main():
    ap = argparse.ArgumentParser(description="Tách căn cứ pháp lý bằng Gemini LLM.")
    ap.add_argument("files", nargs="*", help="File dataset JSON cần tách")
    ap.add_argument("--text", help="Chỉ tách 1 đoạn (in JSON ra màn hình)")
    ap.add_argument("--out", help="File ra (mặc định ghi đè file vào)")
    ap.add_argument("--model", default=MODEL, help=f"Model (mặc định {MODEL})")
    ap.add_argument("--workers", type=int, default=4, help="Số luồng gọi song song (mặc định 4)")
    ap.add_argument("--rpm", type=int, default=28, help="Giới hạn request/phút (Gemma free ~30 -> để 28)")
    ap.add_argument("--tpm", type=int, default=15000, help="Giới hạn token/phút (Gemma free ~16K -> để 15000)")
    ap.add_argument("--limit", type=int, default=0, help="Chỉ xử lý N câu đầu (để thử)")
    ap.add_argument("--save-every", type=int, default=10, help="Ghi file .json output sau mỗi N câu (cache lưu mỗi câu)")
    args = ap.parse_args()

    if args.text:
        res = extract_citations_llm(args.text, model=args.model)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    if not args.files:
        ap.error("Cần truyền file JSON, hoặc dùng --text để thử 1 đoạn.")
    for fp in args.files:
        process_file(fp, args)


if __name__ == "__main__":
    main()
