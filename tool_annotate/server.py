# -*- coding: utf-8 -*-
"""
Web tool gan nhan (annotate) ho so don thu -> JSON, kem OCR tieng Viet.

Chay:  python server.py
Mo:    http://127.0.0.1:8765

Thu muc:
  ../data_mau        PDF goc (chi doc)
  ../data_mau_json   JSON gan nhan
  ../data_mau_ocr    Cache ket qua OCR
  ./tessdata         vie.traineddata + eng + osd
"""
import atexit
import datetime
import json
import mimetypes
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data_mau")
OUT_DIR = os.path.join(ROOT_DIR, "data_mau_json")
OCR_DIR = os.path.join(ROOT_DIR, "data_mau_ocr")
PDFT_DIR = os.path.join(ROOT_DIR, "data_mau_pdf_text")
STATIC_DIR = os.path.join(BASE_DIR, "static")
TESSDATA_DIR = os.path.join(BASE_DIR, "tessdata")
PORT = int(os.environ.get("ANNOTATE_PORT", "8765"))

OCR_LANG = "vie"
OCR_DEFAULT_DPI = 300
OCR_WORKERS = 2
GEMINI_WORKERS = 2          # so FILE chay song song (moi file lai chay nhieu trang)

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(OCR_DIR, exist_ok=True)
os.makedirs(PDFT_DIR, exist_ok=True)

# ---- kiem tra thu vien truoc khi chay, bao loi de hieu ----
_missing = []
for _mod, _pkg in (("cv2", "opencv-python"), ("fitz", "pymupdf"), ("numpy", "numpy")):
    try:
        __import__(_mod)
    except ImportError:
        _missing.append(_pkg)
if _missing:
    sys.stderr.write(
        "\nTHIEU THU VIEN: %s\n"
        "Python dang dung: %s\n\n"
        "Cai bang lenh:\n    \"%s\" -m pip install %s\n\n"
        "Hoac chay server bang run.bat (tu chon dung interpreter).\n"
        % (", ".join(_missing), sys.executable, sys.executable, " ".join(_missing)))
    sys.exit(1)

import ocrlib
import gemini_ocr
import fitz  # PyMuPDF


def find_tesseract():
    cand = [
        os.environ.get("TESSERACT_EXE"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        shutil.which("tesseract"),
    ]
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


TESS_EXE = find_tesseract()
OCR_AVAILABLE = bool(TESS_EXE and fitz and os.path.isdir(TESSDATA_DIR))

GEMINI_MODEL = gemini_ocr.MODEL
GEMINI_AVAILABLE = bool(gemini_ocr.API_KEY)

_PAGE_CACHE = {}


# ------------------------------------------------------------------ helpers
def safe_name(name):
    """Chan path traversal: chi cho phep ten file thuan."""
    name = unquote(name)
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    if os.path.basename(name) != name:
        return None
    return name


def page_count(path):
    if fitz is None:
        return None
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key in _PAGE_CACHE:
        return _PAGE_CACHE[key]
    try:
        with fitz.open(path) as d:
            n = len(d)
    except Exception:
        n = None
    _PAGE_CACHE[key] = n
    return n


def json_path_for(pdf_name):
    return os.path.join(OUT_DIR, os.path.splitext(pdf_name)[0] + ".json")


def ocr_path_for(pdf_name):
    return os.path.join(OCR_DIR, os.path.splitext(pdf_name)[0] + ".json")


def pdft_path_for(pdf_name):
    return os.path.join(PDFT_DIR, os.path.splitext(pdf_name)[0] + ".pdf")


_FLAG_CACHE = {}


def ocr_flags(pdf_name):
    """
    (co_cache, co_vietocr, co_gemini) doc tu cache OCR.
    Nho theo mtime vi /api/files bi goi lien tuc luc dang poll tien do.
    """
    p = ocr_path_for(pdf_name)
    try:
        key = os.path.getmtime(p)
    except OSError:
        return False, False, False
    hit = _FLAG_CACHE.get(p)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with open(p, "r", encoding="utf-8") as f:
            pages = json.load(f).get("pages") or []
    except Exception:
        return True, False, False
    val = (True,
           any(pg.get("text_vietocr") for pg in pages),
           any(pg.get("text_gemini") for pg in pages))
    _FLAG_CACHE[p] = (key, val)
    return val


_ANN_CACHE = {}


def ann_info(pdf_name):
    """
    (da_hoan_thanh, [cach_giai_quyet...]) doc tu JSON nhan.

    Mot ho so co the co nhieu don nen tra ve danh sach. Nho theo mtime giong
    ocr_flags: /api/files bi goi lien tuc luc poll tien do, doc lai vai chuc
    file JSON moi lan thi phi.
    """
    p = json_path_for(pdf_name)
    try:
        key = os.path.getmtime(p)
    except OSError:
        return False, []
    hit = _ANN_CACHE.get(p)
    if hit and hit[0] == key:
        return hit[1]
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False, []
    don = data.get("don_thu") or []
    if isinstance(don, dict):
        don = [don]
    cgq = []
    for d in don:
        v = d.get("cach_giai_quyet") if isinstance(d, dict) else None
        if v and v not in cgq:
            cgq.append(v)
    val = (bool(data.get("da_hoan_thanh")), cgq)
    _ANN_CACHE[p] = (key, val)
    return val


def list_files():
    out = []
    if not os.path.isdir(DATA_DIR):
        return out
    for fn in sorted(os.listdir(DATA_DIR), key=lambda s: s.lower()):
        if not fn.lower().endswith(".pdf"):
            continue
        full = os.path.join(DATA_DIR, fn)
        jp = json_path_for(fn)
        done, cach_giai_quyet = ann_info(fn)
        has_ocr, has_vocr, has_gem = ocr_flags(fn)
        out.append({
            "name": fn,
            "size": os.path.getsize(full),
            "pages": page_count(full),
            "has_json": os.path.exists(jp),
            "done": done,
            "cach_giai_quyet": cach_giai_quyet,
            "has_ocr": has_ocr,
            "has_vietocr": has_vocr,
            "has_gemini": has_gem,
            "has_pdf_text": os.path.exists(pdft_path_for(fn)),
        })
    return out


# ---------------------------------------------------------------------- OCR
# Khoa job theo (engine, name): truoc day chi khoa theo name nen chay
# Tesseract va VietOCR tren cung mot file thi tien do de len nhau.
_jobs = {}                      # (engine, name) -> {state, done, total, error}
_jobs_lock = threading.Lock()
_job_queue = queue.Queue()


def set_job(engine, name, **kw):
    with _jobs_lock:
        j = _jobs.setdefault((engine, name),
                             {"engine": engine, "name": name, "state": "queued",
                              "done": 0, "total": 0, "error": None})
        j.update(kw)
        return dict(j)


def get_job(engine, name):
    with _jobs_lock:
        j = _jobs.get((engine, name))
        return dict(j) if j else None


def jobs_for(name):
    """Tat ca job cua mot file, theo tung engine."""
    with _jobs_lock:
        return {e: dict(v) for (e, n), v in _jobs.items() if n == name}


def busy(engine, name):
    j = get_job(engine, name)
    return bool(j and j["state"] in ("queued", "running"))


def run_ocr(name, dpi=None):
    """OCR toan bo mot PDF + tao ban PDF co lop text copy duoc."""
    pdf = os.path.join(DATA_DIR, name)
    dpi = dpi or OCR_DEFAULT_DPI
    try:
        total = page_count(pdf) or 0
        set_job("tesseract", name, state="running", done=0, total=total, error=None)

        def on_progress(done, tot):
            set_job("tesseract", name, done=done, total=tot)

        pages, diag = ocrlib.process_pdf(
            pdf, TESS_EXE, TESSDATA_DIR, lang=OCR_LANG,
            searchable_out=pdft_path_for(name), progress=on_progress, dpi=dpi)

        # giu lai text_gemini / text_vietocr da doc truoc do cho khoi mat
        old = {}
        p = ocr_path_for(name)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    old = {pg["page"]: pg for pg in (json.load(f).get("pages") or [])}
            except Exception:
                old = {}
        for pg in pages:
            o = old.get(pg["page"]) or {}
            for k in ("text_vietocr", "text_gemini", "gemini_loi"):
                if o.get(k) is not None:
                    pg[k] = o[k]

        payload = {
            "file": name,
            "lang": OCR_LANG,
            "engine": "tesseract-lstm + anh goc + xoa muc do + scale theo chieu cao chu",
            "dpi_render": dpi,
            "cap_nhat": datetime.datetime.now().isoformat(timespec="seconds"),
            "chan_doan": diag,
            "pages": pages,
        }
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        set_job("tesseract", name, state="done")
    except Exception as e:
        set_job("tesseract", name, state="error", error=str(e))


# --------------------------------------------------------- VietOCR (bo thu 2)
VENV_PY = os.path.join(BASE_DIR, "ocr_env", "Scripts", "python.exe")
VOCR_WORKER = os.path.join(BASE_DIR, "vietocr_worker.py")
VOCR_WEIGHTS = os.path.join(BASE_DIR, "models", "vgg-transformer.pth")
VOCR_AVAILABLE = (os.path.exists(VENV_PY) and os.path.exists(VOCR_WORKER)
                  and os.path.exists(VOCR_WEIGHTS))


class VietOcrClient:
    """Giu mot tien trinh VietOCR song san de khoi phai nap model moi lan."""

    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()

    def _ensure(self):
        if self.proc and self.proc.poll() is None:
            return
        self.proc = subprocess.Popen(
            [VENV_PY, "-X", "utf8", VOCR_WORKER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        line = self.proc.stdout.readline()
        if not line or not json.loads(line).get("ready"):
            raise RuntimeError("khong khoi dong duoc VietOCR")

    def recognize(self, d, files):
        if not files:
            return []
        with self.lock:
            self._ensure()
            self.proc.stdin.write(json.dumps({"dir": d, "files": files}) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("VietOCR thoat bat thuong")
        r = json.loads(line)
        if not r.get("ok"):
            raise RuntimeError(r.get("error", "loi khong ro"))
        return r["texts"]


_vocr = VietOcrClient()


@atexit.register
def _stop_vocr():
    """Dung han tien trinh VietOCR khi server tat, tranh de lai process mo coi."""
    p = getattr(_vocr, "proc", None)
    if p and p.poll() is None:
        try:
            p.terminate()
        except Exception:
            pass
_vocr_queue = queue.Queue()


def run_vietocr(name):
    """Doc lai mot PDF bang VietOCR, ghi them truong text_vietocr vao cache OCR."""
    jp = ocr_path_for(name)
    if not os.path.exists(jp):
        set_job("vietocr", name, state="error", error="Chay OCR Tesseract truoc da")
        return
    try:
        total = page_count(os.path.join(DATA_DIR, name)) or 0
        set_job("vietocr", name, state="running", done=0, total=total, error=None)

        res = ocrlib.vietocr_pass(
            os.path.join(DATA_DIR, name), TESS_EXE, TESSDATA_DIR,
            _vocr.recognize, lang=OCR_LANG,
            progress=lambda d, t: set_job("vietocr", name, done=d, total=t))

        with open(jp, "r", encoding="utf-8") as f:
            data = json.load(f)
        by_page = {r["page"]: r for r in res}
        for pg in data.get("pages", []):
            r = by_page.get(pg["page"])
            if r:
                pg["text_vietocr"] = r["text_vietocr"]
        data["vietocr_cap_nhat"] = datetime.datetime.now().isoformat(timespec="seconds")
        tmp = jp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, jp)
        set_job("vietocr", name, state="done")
    except Exception as e:
        set_job("vietocr", name, state="error", error=str(e))


# --------------------------------------------------- Gemini VLM (bo chinh xac nhat)
_gem_queue = queue.Queue()
_gem_quota_het = [None]         # nho lai khi het quota ngay de chan ca hang doi


def run_gemini(name):
    """
    Doc ca PDF bang mo hinh thi giac, ghi truong text_gemini vao cache OCR.

    Chay doc lap duoc: khong can Tesseract chay truoc, neu chua co cache thi
    tao moi. Ket qua ghi them chu khong de len text cua Tesseract/VietOCR.
    """
    pdf = os.path.join(DATA_DIR, name)
    try:
        total = page_count(pdf) or 0
        set_job("gemini", name, state="running", done=0, total=total, error=None)

        res = gemini_ocr.process_pdf(
            pdf, model=GEMINI_MODEL,
            progress=lambda d, t: set_job("gemini", name, done=d, total=t))

        jp = ocr_path_for(name)
        data = None
        if os.path.exists(jp):
            try:
                with open(jp, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None
        if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
            data = {"file": name, "lang": OCR_LANG, "engine": "gemini-vlm", "pages": []}

        by = {pg["page"]: pg for pg in data["pages"] if isinstance(pg, dict)}
        for r in res:
            pg = by.get(r["page"])
            if pg is None:
                pg = {"page": r["page"], "text": "", "text_raw": ""}
                data["pages"].append(pg)
                by[r["page"]] = pg
            pg["text_gemini"] = r["text_gemini"]
            if r.get("gemini_model"):        # co the khac nhau giua cac trang
                pg["gemini_model"] = r["gemini_model"]
            if r.get("loi"):
                pg["gemini_loi"] = r["loi"]
            else:
                pg.pop("gemini_loi", None)
        data["pages"].sort(key=lambda pg: pg.get("page") or 0)
        dung = sorted({r["gemini_model"] for r in res if r.get("gemini_model")})
        data["gemini_model"] = ", ".join(dung) if dung else GEMINI_MODEL
        data["gemini_cap_nhat"] = datetime.datetime.now().isoformat(timespec="seconds")

        tmp = jp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, jp)

        # Trang loi thi van luu (de biet trang nao chua doc duoc), nhung phai
        # bao ra chu khong de nguoi dung tuong ca file da xong.
        quota = next((r["loi"] for r in res
                      if "quota theo ngay" in (r.get("loi") or "")), None)
        if quota:
            _gem_quota_het[0] = quota

        bad = [str(r["page"]) for r in res if r.get("loi")]
        if bad and len(bad) == len(res):
            set_job("gemini", name, state="error",
                    error=quota or ("tat ca %d trang deu loi: %s"
                                    % (len(bad), res[0]["loi"])))
        elif bad:
            set_job("gemini", name, state="done",
                    error="loi o trang %s (cac trang khac da xong)" % ", ".join(bad))
        else:
            set_job("gemini", name, state="done")
    except Exception as e:
        set_job("gemini", name, state="error", error=str(e))


def gem_worker():
    while True:
        name = _gem_queue.get()
        try:
            # Het quota theo ngay thi ca hang doi con lai cung se that bai het.
            # Xoa hang doi va bao ro thay vi de no chay het 40 file vo ich.
            if _gem_quota_het[0]:
                set_job("gemini", name, state="error", error=_gem_quota_het[0])
            else:
                run_gemini(name)
        finally:
            _gem_queue.task_done()


def vocr_worker():
    while True:
        name = _vocr_queue.get()
        try:
            run_vietocr(name)
        finally:
            _vocr_queue.task_done()


def worker():
    while True:
        name, dpi = _job_queue.get()
        try:
            run_ocr(name, dpi)
        finally:
            _job_queue.task_done()


def enqueue(name, dpi):
    set_job("tesseract", name, state="queued", done=0,
            total=page_count(os.path.join(DATA_DIR, name)) or 0, error=None)
    _job_queue.put((name, dpi))


def enqueue_gemini(name):
    set_job("gemini", name, state="queued", done=0,
            total=page_count(os.path.join(DATA_DIR, name)) or 0, error=None)
    _gem_queue.put(name)


# ------------------------------------------------------------------ handler
class Handler(BaseHTTPRequestHandler):
    server_version = "AnnotateTool/2.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype=None):
        if not os.path.exists(path):
            return self.send_error(404, "Not found")
        ctype = ctype or (mimetypes.guess_type(path)[0] or "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)

        if path in ("/", "/index.html"):
            return self.send_file(os.path.join(STATIC_DIR, "index.html"),
                                  "text/html; charset=utf-8")

        if path == "/api/files":
            return self.send_json({
                "data_dir": DATA_DIR,
                "out_dir": OUT_DIR,
                "ocr_available": OCR_AVAILABLE,
                "vietocr_available": VOCR_AVAILABLE,
                "gemini_available": GEMINI_AVAILABLE,
                "gemini_model": GEMINI_MODEL,
                "ocr_lang": OCR_LANG,
                "files": list_files(),
            })

        if path.startswith("/api/pdf/"):
            name = safe_name(path[len("/api/pdf/"):])
            if not name:
                return self.send_error(400, "Bad name")
            # mac dinh tra ban co lop text (boi den copy duoc); ?orig=1 -> ban goc
            want_orig = (qs.get("orig") or ["0"])[0] == "1"
            pt = pdft_path_for(name)
            if not want_orig and os.path.exists(pt):
                return self.send_file(pt, "application/pdf")
            return self.send_file(os.path.join(DATA_DIR, name), "application/pdf")

        if path.startswith("/api/annotation/"):
            name = safe_name(path[len("/api/annotation/"):])
            if not name:
                return self.send_error(400, "Bad name")
            jp = json_path_for(name)
            if not os.path.exists(jp):
                return self.send_json({"exists": False, "data": None})
            try:
                with open(jp, "r", encoding="utf-8") as f:
                    return self.send_json({"exists": True, "data": json.load(f)})
            except Exception as e:
                return self.send_json({"exists": False, "data": None, "error": str(e)})

        if path.startswith("/api/ocr/"):
            name = safe_name(path[len("/api/ocr/"):])
            if not name:
                return self.send_error(400, "Bad name")
            p = ocr_path_for(name)
            jobs = jobs_for(name)
            job = jobs.get("tesseract")
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return self.send_json({"cached": True, "job": job, "jobs": jobs,
                                               "data": json.load(f)})
                except Exception as e:
                    return self.send_json({"cached": False, "job": job, "jobs": jobs,
                                           "error": str(e)})
            return self.send_json({"cached": False, "job": job, "jobs": jobs, "data": None})

        if path == "/api/ocr_status":
            with _jobs_lock:
                jobs = {"%s|%s" % (e, n): dict(v) for (e, n), v in _jobs.items()}
            pending = sum(1 for v in jobs.values() if v["state"] in ("queued", "running"))
            return self.send_json({"jobs": jobs, "pending": pending})

        return self.send_error(404, "Not found")

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)

        if path.startswith("/api/annotation/"):
            name = safe_name(path[len("/api/annotation/"):])
            if not name:
                return self.send_error(400, "Bad name")
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception as e:
                return self.send_json({"ok": False, "error": "JSON khong hop le: %s" % e}, 400)

            full = os.path.join(DATA_DIR, name)
            head = {
                "file": name,
                "so_trang": page_count(full) if os.path.exists(full) else None,
                "cap_nhat": datetime.datetime.now().isoformat(timespec="seconds"),
            }
            for k in head:
                data.pop(k, None)
            head.update(data)

            jp = json_path_for(name)
            tmp = jp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(head, f, ensure_ascii=False, indent=2)
            os.replace(tmp, jp)
            return self.send_json({"ok": True, "path": jp})

        if path.startswith("/api/ocr/"):
            if not OCR_AVAILABLE:
                return self.send_json({"ok": False, "error": "Chua co Tesseract hoac PyMuPDF"}, 400)
            name = safe_name(path[len("/api/ocr/"):])
            if not name or not os.path.exists(os.path.join(DATA_DIR, name)):
                return self.send_error(400, "Bad name")
            dpi = int((qs.get("dpi") or [OCR_DEFAULT_DPI])[0])
            dpi = max(150, min(600, dpi))
            force = (qs.get("force") or ["0"])[0] == "1"
            if os.path.exists(ocr_path_for(name)) and not force:
                return self.send_json({"ok": True, "cached": True})
            if busy("tesseract", name):
                return self.send_json({"ok": True, "job": get_job("tesseract", name)})
            enqueue(name, dpi)
            return self.send_json({"ok": True, "job": get_job("tesseract", name)})

        if path.startswith("/api/vietocr/"):
            if not VOCR_AVAILABLE:
                return self.send_json({"ok": False, "error": "Chua cai VietOCR"}, 400)
            name = safe_name(path[len("/api/vietocr/"):])
            if not name or not os.path.exists(os.path.join(DATA_DIR, name)):
                return self.send_error(400, "Bad name")
            if busy("vietocr", name):
                return self.send_json({"ok": True, "job": get_job("vietocr", name)})
            set_job("vietocr", name, state="queued", done=0,
                    total=page_count(os.path.join(DATA_DIR, name)) or 0, error=None)
            _vocr_queue.put(name)
            return self.send_json({"ok": True, "job": get_job("vietocr", name)})

        if path.startswith("/api/gemini/"):
            if not GEMINI_AVAILABLE:
                return self.send_json({"ok": False, "error": "Chua co GEMINI_API_KEY"}, 400)
            name = safe_name(path[len("/api/gemini/"):])
            if not name or not os.path.exists(os.path.join(DATA_DIR, name)):
                return self.send_error(400, "Bad name")
            if busy("gemini", name):
                return self.send_json({"ok": True, "job": get_job("gemini", name)})
            enqueue_gemini(name)
            return self.send_json({"ok": True, "job": get_job("gemini", name)})

        if path == "/api/ocr_all":
            if not OCR_AVAILABLE:
                return self.send_json({"ok": False, "error": "Chua co Tesseract hoac PyMuPDF"}, 400)
            dpi = int((qs.get("dpi") or [OCR_DEFAULT_DPI])[0])
            dpi = max(150, min(600, dpi))
            n = 0
            for f in list_files():
                if f["has_ocr"] or busy("tesseract", f["name"]):
                    continue
                enqueue(f["name"], dpi)
                n += 1
            return self.send_json({"ok": True, "queued": n})

        if path == "/api/gemini_all":
            if not GEMINI_AVAILABLE:
                return self.send_json({"ok": False, "error": "Chua co GEMINI_API_KEY"}, 400)
            force = (qs.get("force") or ["0"])[0] == "1"
            n = 0
            for f in list_files():
                if (f["has_gemini"] and not force) or busy("gemini", f["name"]):
                    continue
                enqueue_gemini(f["name"])
                n += 1
            return self.send_json({"ok": True, "queued": n})

        if path == "/api/export_all":
            merged = []
            for fn in sorted(os.listdir(OUT_DIR)):
                if fn.lower().endswith(".json") and fn != "_all.json":
                    try:
                        with open(os.path.join(OUT_DIR, fn), "r", encoding="utf-8") as f:
                            merged.append(json.load(f))
                    except Exception:
                        pass
            out = os.path.join(OUT_DIR, "_all.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            return self.send_json({"ok": True, "path": out, "count": len(merged)})

        return self.send_error(404, "Not found")


def main():
    if not os.path.isdir(DATA_DIR):
        print("KHONG TIM THAY thu muc du lieu:", DATA_DIR)
        sys.exit(1)

    for i in range(OCR_WORKERS):
        threading.Thread(target=worker, daemon=True, name="ocr-%d" % i).start()
    threading.Thread(target=vocr_worker, daemon=True, name="vietocr").start()
    for i in range(GEMINI_WORKERS):
        threading.Thread(target=gem_worker, daemon=True, name="gemini-%d" % i).start()

    print("Du lieu PDF :", DATA_DIR)
    print("Luu JSON    :", OUT_DIR)
    print("Cache OCR   :", OCR_DIR)
    print("Tesseract   :", TESS_EXE or "KHONG TIM THAY - chuc nang OCR bi tat")
    print("VietOCR     :", "san sang" if VOCR_AVAILABLE else "chua cai")
    print("Gemini VLM  :", ("%s (%d trang song song/file)"
                            % (GEMINI_MODEL, gemini_ocr.WORKERS))
                           if GEMINI_AVAILABLE else "chua co GEMINI_API_KEY")
    print("Dang chay   : http://127.0.0.1:%d" % PORT)
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nDa dung.")


if __name__ == "__main__":
    main()
