# -*- coding: utf-8 -*-
"""
OCR bang mo hinh thi giac (Gemini) - doc anh CA TRANG thay vi cat tung dong.

Vi sao can bo nay: Tesseract va VietOCR deu duoc huan luyen tren CHU IN, nen
voi cac trang don thu VIET TAY chung khong "sai mot it" ma sai han ve ban chat
(Tesseract ra ky tu rac; VietOCR bia ra cau tieng Viet muot nhung sai noi dung,
kieu sai nay lot qua moi bo loc heuristic nen doc hon). Mo hinh thi giac doc
duoc ca chu viet tay, con dau va bo cuc trang.

Khac voi ocrlib: KHONG lam xam, KHONG xoa muc do, KHONG scale theo chieu cao
chu. Mo hinh can anh mau nguyen ban - con dau do va bo cuc la thong tin co ich
chu khong phai nhieu can loc.

Bien moi truong:
    GEMINI_API_KEY      key, doc tu file .env o thu muc goc du an (xem
                        .env.example) hoac dat san trong moi truong
    GEMINI_OCR_MODELS   danh sach model xep theo chat luong giam dan, cach nhau
                        bang dau phay; het quota model nay thi tu tut xuong
                        model ke tiep (xem LADDER)
    GEMINI_OCR_MODEL    ep dung DUY NHAT mot model, tat co che tut bac
    GEMINI_OCR_WORKERS  so trang goi song song trong 1 file (mac dinh 4)
"""
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import cv2
import fitz
import numpy as np

# .env nam o thu muc goc, con file nay o tool_annotate/ -> phai them goc
# vao sys.path moi import duoc env_config.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import env_config  # noqa: F401  nap .env truoc khi doc os.environ
import ocrlib

API_KEY = os.environ.get("GEMINI_API_KEY", "")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Free tier chan 20 request/NGAY/MODEL, va bucket cua tung model la RIENG BIET.
# Nen thay vi chet dung khi model dau tien het quota, ta tu tut xuong model ke
# tiep: 7 model x 20 = ~140 trang/ngay thay vi 20.
#
# gemma-4-31b-it dat dau theo yeu cau. Luu y do thu tay tren cung 1 trang viet
# tay (Document 08-09-2026 09.54 trang 1): gemma BO SOT han dong con dau
# "CUC CANH SAT QLHC VE TTXH", doc so den 1691 (3.5-flash: 1621) va ngay 20/5
# (3.5-flash: 20/3) - tuc kem hon o dung may truong quan trong nhat cua don thu.
# Gemma cung cham ~126s/trang so voi ~5s cua flash. Muon uu tien chat luong thi
# dat lai GEMINI_OCR_MODELS cho gemini-3.5-flash len dau.
LADDER = [m.strip() for m in os.environ.get(
    "GEMINI_OCR_MODELS",
    "gemma-4-31b-it,"
    "gemini-3.5-flash,gemini-3.8-flash,gemini-3.7-flash,"
    "gemini-2.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite"
).split(",") if m.strip()]
# GEMINI_OCR_MODEL: ep dung DUY NHAT mot model (tat co che tut bac)
MODEL = os.environ.get("GEMINI_OCR_MODEL") or (LADDER[0] if LADDER else "gemini-2.5-flash")
_het_quota = set()          # model da het quota hom nay -> khoi goi lai
_het_lock = threading.Lock()

MAX_SIDE = 2048             # canh dai cua anh gui len (du de doc chu nho)
JPEG_QUALITY = 92
WORKERS = int(os.environ.get("GEMINI_OCR_WORKERS", "4"))    # so trang goi song song
RETRY_STATUS = (429, 500, 502, 503, 504)

# Chep chu la viec khong can suy luan, ma cac model dong 3.x lai BAT thinking
# mac dinh va thinking TINH VAO maxOutputTokens. Da gap that: thinking an 2561
# token, model het budget roi roi vao vong lap sinh khoang trang - tra ve "02"
# kem 174.000 ky tu trang, finishReason=MAX_TOKENS. Sau khi strip chi con "02"
# va no se duoc ghi vao du lieu nhu the la noi dung that cua trang.
# => Voi model nao tat duoc thinking thi luon tat.
MAX_OUT = 16384
_khong_thinking = set()     # model tu choi thinkingConfig (nho de khoi thu lai)
_kt_lock = threading.Lock()

# Gioi han rieng cua tung model, khop theo chuoi con trong ten model.
# gemma-4-31b-it (do thu that ngay 2026-09-10):
#   - thinkingConfig -> HTTP 400 "Thinking budget is not supported for this model",
#     va thinking KHONG TAT DUOC: no an ~4200 token moi trang. Voi maxOutputTokens
#     8192 thi het budget truoc khi kip chep chu -> tra ve 0 ky tu. Phai de >= 16384.
#   - anh canh dai > 768px -> HTTP 500 "Internal error encountered" (thu 1024,
#     1536, 2048 deu 500). Nen phai thu nho anh rieng cho gemma.
GIOI_HAN = {
    "gemma": {"max_side": 768, "tat_thinking": False},
}


def _gioi_han(model):
    for k, v in GIOI_HAN.items():
        if k in (model or "").lower():
            return v
    return {"max_side": None, "tat_thinking": True}


def _config(model):
    """Config gui kem, tuy theo model co tat duoc thinking hay khong."""
    gc: dict = {"temperature": 0, "maxOutputTokens": MAX_OUT}
    with _kt_lock:
        da_biet_khong_nhan = model in _khong_thinking
    if _gioi_han(model)["tat_thinking"] and not da_biet_khong_nhan:
        gc["thinkingConfig"] = {"thinkingBudget": 0}
    return gc

PROMPT = """Bạn là bộ nhận dạng chữ (OCR) tiếng Việt, đọc ảnh một trang hồ sơ đơn thư.

Nhiệm vụ: chép lại TOÀN BỘ chữ có trong ảnh.

QUY TẮC BẮT BUỘC:
1. Chép TRUNG THÀNH từng chữ đúng như trong ảnh. Giữ nguyên lỗi chính tả, cách viết hoa/thường và dấu câu của bản gốc. KHÔNG sửa lỗi, KHÔNG chuẩn hoá, KHÔNG diễn đạt lại cho mượt.
2. Giữ đúng thứ tự đọc và cách ngắt dòng của trang: một dòng trên ảnh là một dòng trong kết quả.
3. Chép cả chữ VIẾT TAY, chữ trong con dấu, dấu "ĐẾN" của văn thư, số đến, số hiệu, ngày tháng, và tên ghi ở chỗ chữ ký.
4. Với các con số (số CCCD, số điện thoại, ngày tháng, số nhà) phải đọc thật cẩn thận từng chữ số. Nếu không chắc một chữ số nào thì ghi [?] ngay tại vị trí chữ số đó.
5. Chỗ nào mờ, mất nét hoặc không đọc được thì ghi [?]. TUYỆT ĐỐI KHÔNG được đoán và KHÔNG được bịa thêm từ để câu nghe hợp lý. Thà để [?] còn hơn ghi sai.
6. Nếu có bảng thì giữ theo từng hàng, các ô trên cùng một hàng cách nhau bằng " | ".
7. Nếu trang không có chữ nào thì chỉ trả về đúng: [TRANG TRONG]

Chỉ trả về nguyên văn bản đã chép. Không thêm lời dẫn, không giải thích, không dùng markdown, không bọc trong dấu ```."""


# --------------------------------------------------------------- anh gui len
def page_jpeg(doc, pageno, max_side=MAX_SIDE, quality=JPEG_QUALITY):
    """Lay anh trang o dang JPEG bytes: giu mau, chi ha kich thuoc neu qua to."""
    rgb, _ = ocrlib.native_rgb(doc, pageno)
    h, w = rgb.shape[:2]
    m = max(h, w)
    if m > max_side:
        f = max_side / float(m)
        rgb = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("khong ma hoa duoc anh trang %d" % (pageno + 1))
    return buf.tobytes()


def thu_nho(jpeg, max_side, quality=JPEG_QUALITY):
    """
    Thu nho anh JPEG da ma hoa (chi dung cv2 nen an toan da luong, khong can fitz).
    Dung cho model co tran kich thuoc rieng - vd gemma 500 neu anh > 768px.
    """
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jpeg
    m = max(img.shape[:2])
    if m <= max_side:
        return jpeg
    f = max_side / float(m)
    img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else jpeg


# ------------------------------------------------------------------- goi API
def _clean(s):
    """Bo lop ```...``` neu mo hinh van boc, va khoang trang thua."""
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


class Truncated(RuntimeError):
    """Model bi cat giua duong -> KHONG duoc coi phan da nhan la ket qua."""


class QuotaHet(RuntimeError):
    """Het quota theo NGAY -> thu lai bao nhieu lan cung vo nghia."""


def _doc_loi_429(raw):
    """
    Boc chi tiet 429 -> (thong_diep_ngan, het_quota_ngay, so_giay_cho).

    Free tier chan theo NGAY (20 request/ngay/model), khac han chan theo phut:
    het quota ngay thi phai doi sang hom sau hoac nang plan, retry chi lang phi.
    """
    try:
        err = json.loads(raw)["error"]
    except Exception:
        return raw[:200], False, None
    theo_ngay, cho, mo_ta = False, None, []
    for d in err.get("details", []) or []:
        t = d.get("@type", "")
        if "QuotaFailure" in t:
            for v in d.get("violations", []) or []:
                qid = v.get("quotaId") or ""
                if "PerDay" in qid:
                    theo_ngay = True
                mo_ta.append("%s = %s" % (qid, v.get("quotaValue")))
        elif "RetryInfo" in t:
            s = str(d.get("retryDelay") or "").rstrip("s")
            try:
                cho = float(s)
            except ValueError:
                cho = None
    msg = "; ".join(mo_ta) or (err.get("message") or "")[:150]
    return msg, theo_ngay, cho


def ocr_image(jpeg, model=None, api_key=None, timeout=300, retries=4):
    """
    Gui 1 anh trang, tra ve van ban da chep.

    Nem loi thay vi tra ve van ban thieu: mot trang OCR sai am tham con te hon
    mot trang bao loi, vi khong ai soat lai no.
    """
    key = api_key or API_KEY
    if not key:
        raise RuntimeError("Chua co GEMINI_API_KEY - dien vao file .env o thu muc goc du an (copy tu .env.example)")
    m = model or MODEL
    url = ENDPOINT.format(model=m) + "?key=" + key

    tran = _gioi_han(m)["max_side"]
    if tran:                        # model co tran kich thuoc rieng (vd gemma)
        jpeg = thu_nho(jpeg, tran)
    parts_in = [
        {"text": PROMPT},
        {"inline_data": {"mime_type": "image/jpeg",
                         "data": base64.b64encode(jpeg).decode("ascii")}},
    ]
    last = None
    for attempt in range(retries + 1):
        payload = json.dumps({"contents": [{"parts": parts_in}],
                              "generationConfig": _config(m)}).encode("utf-8")
        try:
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            cands = resp.get("candidates") or []
            if not cands:                       # thuong la bi safety filter chan
                raise RuntimeError("khong co ket qua: %s"
                                   % json.dumps(resp.get("promptFeedback", {}))[:200])
            fin = cands[0].get("finishReason") or "STOP"
            parts = cands[0].get("content", {}).get("parts", []) or []
            txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            if fin not in ("STOP", "FINISH_REASON_STOP", None):
                raise Truncated("mo hinh dung giua duong (finishReason=%s, "
                                "da nhan %d ky tu) - bo ket qua nay" % (fin, len(txt)))
            out = _clean(txt)
            if not out:
                raise RuntimeError("mo hinh tra ve rong")
            return out
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            last = "HTTP %d: %s" % (e.code, raw[:200])
            # Model khong nhan thinkingConfig -> nho lai RIENG cho model nay roi
            # thu lai. Truoc day co che nay dung mot bien toan cuc dinh, nen mot
            # model gemma tu choi la ca cac model flash cung mat thinking-off va
            # quay lai loi truncation.
            if e.code == 400 and "hinking" in raw:
                with _kt_lock:
                    moi = m not in _khong_thinking
                    _khong_thinking.add(m)
                if moi:
                    continue
            if e.code == 429:
                msg, theo_ngay, cho = _doc_loi_429(raw)
                if theo_ngay:
                    raise QuotaHet("het quota theo ngay cua model %s (%s) - phai doi "
                                   "sang hom sau hoac nang plan tra phi"
                                   % (model or MODEL, msg))
                last = "HTTP 429: %s" % msg
                if attempt == retries:
                    raise RuntimeError(last)
                time.sleep(cho if cho else min(2 ** attempt, 20))
                continue
            if e.code not in RETRY_STATUS or attempt == retries:
                raise RuntimeError(last)
        except Exception as e:
            last = str(e)
            if attempt == retries:
                raise
        time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(str(last))


def ocr_image_ladder(jpeg, model=None, **kw):
    """
    Nhu ocr_image nhung tu tut xuong model ke tiep khi het quota ngay.
    Tra ve (van_ban, model_da_dung) de biet trang nao doc bang model nao.

    Neu goi voi `model` cu the (hoac dat GEMINI_OCR_MODEL) thi khong tut bac.
    """
    if model or os.environ.get("GEMINI_OCR_MODEL"):
        m = model or MODEL
        return ocr_image(jpeg, model=m, **kw), m

    loi_cuoi = None
    for m in LADDER:
        with _het_lock:
            if m in _het_quota:
                continue
        try:
            return ocr_image(jpeg, model=m, **kw), m
        except QuotaHet as e:
            with _het_lock:
                _het_quota.add(m)
            loi_cuoi = e
        except Exception as e:
            # loi rieng cua model nay (vd 400 khong nhan config) -> thu model sau
            loi_cuoi = e
    if loi_cuoi is None:
        raise RuntimeError("danh sach model rong (xem GEMINI_OCR_MODELS)")
    if isinstance(loi_cuoi, QuotaHet):
        raise QuotaHet("het quota ngay o TAT CA %d model (%s) - doi sang hom sau "
                       "hoac bat thanh toan cho project"
                       % (len(LADDER), ", ".join(LADDER)))
    raise RuntimeError(str(loi_cuoi))


# --------------------------------------------------------------- toan bo file
def process_pdf(pdf_path, model=None, progress=None, max_side=MAX_SIDE,
                workers=WORKERS):
    """
    OCR ca PDF bang VLM. Tra ve [{"page": n, "text_gemini": ...}, ...] theo
    dung thu tu trang.

    Moi trang mat ~10-25s va la tac vu cho mang, nen goi song song nhieu trang.
    fitz.Document khong an toan da luong -> ma hoa het anh truoc (nhanh), roi
    moi goi API song song.
    """
    src = fitz.open(pdf_path)
    try:
        total = len(src)
        imgs: list = [page_jpeg(src, i, max_side=max_side) for i in range(total)]
    finally:
        src.close()

    out: list = [None] * total
    lock = threading.Lock()
    done = [0]
    het_quota: list = [None]    # het quota ngay -> ngung, dung goi tiep vo ich

    def one(i):
        if het_quota[0]:
            out[i] = {"page": i + 1, "text_gemini": "", "loi": het_quota[0]}
        else:
            dung = None
            try:
                txt, dung = ocr_image_ladder(imgs[i], model=model)
                err = None
            except QuotaHet as e:
                txt, err = "", str(e)
                het_quota[0] = err
            except Exception as e:              # 1 trang loi khong lam chet ca file
                txt, err = "", str(e)
            out[i] = {"page": i + 1, "text_gemini": txt}
            if dung:
                out[i]["gemini_model"] = dung
            if err:
                out[i]["loi"] = err
        imgs[i] = None                          # tra RAM lai som
        with lock:
            done[0] += 1
            if progress:
                progress(done[0], total)

    if total:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, total))) as ex:
            list(ex.map(one, range(total)))
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    model = sys.argv[2] if len(sys.argv) > 2 else None
    for r in process_pdf(sys.argv[1], model=model):
        print("=" * 20, "trang", r["page"], r.get("loi") or "")
        print(r["text_gemini"])
