# -*- coding: utf-8 -*-
"""
CHẤM câu trả lời của AI bằng LLM (Google Gemini API), lấy ĐÁP ÁN GỐC làm chuẩn.

Vì sao cần: phần "độ tương đồng" trong public/index.html chỉ đo TRÙNG LẶP TỪ
NGỮ. Đã đo trên ca đối kháng: câu trả lời ĐÚNG nhưng diễn đạt khác chỉ được
20%, câu đúng mà ngắn gọn được 39% — nên điểm thấp ở đó KHÔNG có nghĩa là sai.
Muốn chấm theo Ý thì phải nhờ mô hình. Module này làm đúng việc đó.

Dùng chung hạ tầng với trich_dan_llm.py (API key, model, endpoint, bóc JSON)
để chỉ có MỘT chỗ cấu hình:
    set GEMINI_API_KEY=xxxxx
    set GEMINI_MODEL=gemini-2.5-flash      (tuỳ chọn)

DÙNG:
    # chấm thử một câu trong DB
    venv\\Scripts\\python.exe cham_llm.py --id 3848

    # chấm nội dung tự nhập
    venv\\Scripts\\python.exe cham_llm.py --dap-an "..." --ai "..."

App gọi qua endpoint POST /api/cau_hoi/<id>/cham-llm (xem app.py).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Dùng lại cấu hình + hàm bóc JSON của bộ tách trích dẫn: cùng key, cùng model,
# cùng cách xử lý model bọc ```json. Không chép lại để khỏi lệch nhau về sau.
from trich_dan_llm import API_KEY, ENDPOINT, MODEL, _RETRY_STATUS, _parse_json

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Schema ép đầu ra (định dạng REST của Gemini: type VIẾT HOA).
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        # khớp | một phần | trái ngược | không trả lời
        "ket_luan": {"type": "STRING"},
        "diem_noi_dung": {"type": "INTEGER"},
        "diem_can_cu": {"type": "INTEGER"},
        "y_dung": {"type": "ARRAY", "items": {"type": "STRING"}},
        "y_thieu": {"type": "ARRAY", "items": {"type": "STRING"}},
        "y_sai": {"type": "ARRAY", "items": {"type": "STRING"}},
        "can_cu_sai": {"type": "ARRAY", "items": {"type": "STRING"}},
        # lập luận có chặt không — KHÁC với kết luận có khớp không:
        # trả lời đúng kết quả nhưng suy luận sai vẫn là bài kém
        "lap_luan": {"type": "STRING"},
        "nhan_xet": {"type": "STRING"},
        # soi TỪNG ĐOẠN của câu trả lời: trích nguyên văn + phán đúng/sai + lý do
        "doan": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "trich": {"type": "STRING"},
            "loai": {"type": "STRING"},
            "ly_do": {"type": "STRING"}}}},
    },
    "required": ["ket_luan", "diem_noi_dung", "diem_can_cu",
                 "y_dung", "y_thieu", "y_sai", "can_cu_sai", "lap_luan",
                 "nhan_xet", "doan"],
}

PROMPT = """Bạn là người chấm bài cho một bộ kiểm thử AI pháp luật Việt Nam.

Bạn được cho: CÂU HỎI, ĐÁP ÁN GỐC (đã được biên tập, coi là CHUẨN), và CÂU TRẢ LỜI CỦA AI.
Nhiệm vụ: chấm CÂU TRẢ LỜI CỦA AI so với ĐÁP ÁN GỐC.

QUY TẮC CHẤM:
1) ĐÁP ÁN GỐC là chuẩn. Đừng tự phán xử pháp luật theo hiểu biết riêng của bạn.
   Nếu bạn cho rằng đáp án gốc có chỗ đáng ngờ, ghi vào `nhan_xet`, KHÔNG vì thế
   mà trừ điểm AI.
2) Chấm theo Ý, KHÔNG theo câu chữ. Diễn đạt khác mà cùng nội dung thì vẫn ĐÚNG.
   Trả lời ngắn gọn mà đủ ý chính thì KHÔNG bị trừ điểm vì ngắn.
3) `ket_luan` — kết luận cuối cùng của AI so với đáp án gốc, chọn ĐÚNG MỘT:
   - "khop"        : cùng kết luận, không sai ý nào đáng kể
   - "mot_phan"    : đúng hướng nhưng thiếu ý quan trọng hoặc có chỗ sai nhỏ
   - "trai_nguoc"  : kết luận ngược hẳn với đáp án gốc (vd đáp án nói CÓ bị xử
                     lý, AI nói KHÔNG) — đây là lỗi nặng nhất, luôn chọn mục này
                     khi kết luận trái chiều dù phần còn lại chép đúng
   - "khong_tra_loi": né tránh, lạc đề, hoặc không đưa ra kết luận nào
4) `diem_noi_dung` 0-100: mức đúng về NỘI DUNG so với đáp án gốc.
   Nếu ket_luan = "trai_nguoc" thì diem_noi_dung phải <= 20.
5) `diem_can_cu` 0-100: mức đúng của CĂN CỨ PHÁP LÝ (tên văn bản, điều, khoản,
   điểm). Dẫn đúng văn bản nhưng sai điều/khoản thì trừ nặng. AI không dẫn căn
   cứ nào trong khi đáp án gốc có dẫn thì cho 0.
6) `y_dung` / `y_thieu` / `y_sai`: mỗi mục MỘT câu ngắn tiếng Việt, cụ thể.
   - y_thieu: ý có trong đáp án gốc mà AI không nói.
   - y_sai  : ý AI nói sai, hoặc bịa ra không có trong đáp án gốc.
   Không có thì để mảng rỗng. Tối đa 6 mục mỗi loại.
7) `can_cu_sai`: các căn cứ AI dẫn sai hoặc bịa (vd "dẫn khoản 2 Điều 321 nhưng
   nội dung thuộc khoản 1"). Không có thì mảng rỗng.
8) `lap_luan` — LẬP LUẬN có chặt chẽ không, đánh giá RIÊNG với kết luận (có bài
   ra đúng kết quả nhưng suy luận sai). Chọn ĐÚNG MỘT:
   - "chat_che"          : suy luận đúng, có căn cứ, không nhảy bước
   - "co_lo_hong"        : hướng đúng nhưng thiếu bước, thiếu điều kiện áp dụng
   - "sai_logic"         : suy luận sai (áp sai điều kiện, đảo nhân quả, tự mâu thuẫn)
   - "khong_co_lap_luan" : chỉ phán kết quả, không giải thích
9) `doan` — SOI TỪNG ĐOẠN của CÂU TRẢ LỜI CỦA AI. Đây là phần quan trọng nhất:
   - `trich`: TRÍCH NGUYÊN VĂN một đoạn LIÊN TỤC trong câu trả lời của AI,
     copy y hệt từng ký tự, KHÔNG viết lại, KHÔNG tóm tắt, KHÔNG thêm dấu.
     Mỗi đoạn nên là 1 câu hoặc 1 mệnh đề trọn ý.
   - `loai`: "dung" | "sai" | "can_cu_sai" | "khong_chac"
     * dung       : khớp đáp án gốc
     * sai        : trái đáp án gốc, hoặc bịa
     * can_cu_sai : dẫn sai tên văn bản / điều / khoản / điểm
     * khong_chac : đáp án gốc không nói tới nên không kết luận được
   - `ly_do`: MỘT câu ngắn nói vì sao.
   Bao phủ hết các ý chính, kể cả phần đúng. Tối đa 12 đoạn.
10) CHỈ trả về DUY NHẤT một JSON đúng cấu trúc sau, không markdown, không giải thích:
{"ket_luan":"","diem_noi_dung":0,"diem_can_cu":0,"y_dung":[],"y_thieu":[],"y_sai":[],"can_cu_sai":[],"lap_luan":"","nhan_xet":"","doan":[{"trich":"","loai":"","ly_do":""}]}

=== CÂU HỎI ===
{cau_hoi}

=== ĐÁP ÁN GỐC (CHUẨN) ===
{dap_an}

=== CÂU TRẢ LỜI CỦA AI (CẦN CHẤM) ===
{ai}
"""

# Như trich_dan_llm: Gemma qua Gemini API thường không nhận responseSchema.
# Thử từ "xịn" -> "trơn", nhớ lại config chạy được cho các lần sau.
_CONFIGS = [
    {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0},
    {"responseMimeType": "application/json", "temperature": 0},
    {"temperature": 0},
]
_cfg = [2 if "gemma" in MODEL.lower() else 0]

KET_LUAN_HOP_LE = ("khop", "mot_phan", "trai_nguoc", "khong_tra_loi")


LOAI_DOAN_HOP_LE = ("dung", "sai", "can_cu_sai", "khong_chac")
LAP_LUAN_HOP_LE = ("chat_che", "co_lo_hong", "sai_logic", "khong_co_lap_luan")


def _chuan_khoang_trang(s: str):
    """Chuỗi đã gộp khoảng trắng + bảng tra ngược về vị trí trong chuỗi gốc.

    Model gần như không bao giờ trích lại đúng từng ký tự: nó hay bỏ xuống
    dòng, gộp hai dấu cách thành một, bỏ dấu * đầu dòng. Dò trên bản đã gộp
    khoảng trắng rồi ánh xạ ngược lại thì bắt được các trường hợp đó mà vẫn tô
    đúng vị trí trong văn bản gốc.
    """
    ra, viTri = [], []
    truoc_la_trang = False
    for i, c in enumerate(s):
        if c.isspace():
            if truoc_la_trang:
                continue
            ra.append(" ")
            viTri.append(i)
            truoc_la_trang = True
        else:
            ra.append(c)
            viTri.append(i)
            truoc_la_trang = False
    viTri.append(len(s))
    return "".join(ra), viTri


def _tim_doan(goc: str, chuan: str, tra: list, trich: str):
    """Tìm `trich` trong `goc`. Trả (bat_dau, ket_thuc, cach_tim) hoặc None."""
    trich = (trich or "").strip()
    if len(trich) < 8:          # quá ngắn thì tô nhầm nhiều hơn tô đúng
        return None
    i = goc.find(trich)
    if i >= 0:
        return i, i + len(trich), "nguyên văn"

    kim, _ = _chuan_khoang_trang(trich)
    kim = kim.strip()
    i = chuan.find(kim)
    if i >= 0:
        return tra[i], tra[min(i + len(kim), len(tra) - 1)], "gộp khoảng trắng"

    j = chuan.lower().find(kim.lower())
    if j >= 0:
        return tra[j], tra[min(j + len(kim), len(tra) - 1)], "bỏ qua hoa thường"

    # Model hay thêm/bớt vài chữ ở hai đầu -> neo bằng 30 ký tự đầu và cuối
    if len(kim) >= 40:
        dau, cuoi = kim[:30].lower(), kim[-30:].lower()
        cl = chuan.lower()
        a = cl.find(dau)
        b = cl.find(cuoi, a + 1) if a >= 0 else -1
        if a >= 0 and b > a:
            return tra[a], tra[min(b + 30, len(tra) - 1)], "khớp hai đầu"
    return None


def gan_vi_tri(doan: list, ai_tra_loi: str) -> list:
    """Gắn vị trí cho từng đoạn; bỏ đoạn chồng lấn; đánh dấu đoạn không tìm ra.

    Đoạn KHÔNG tìm thấy vẫn giữ lại (kèm cờ `khong_tim_thay`) chứ không vứt đi:
    đó thường là chỗ model tự diễn đạt lại thay vì trích, nội dung nhận xét vẫn
    dùng được, chỉ là không tô lên văn bản được thôi.
    """
    goc = ai_tra_loi or ""
    chuan, tra = _chuan_khoang_trang(goc)
    ra = []
    for d in doan:
        m = _tim_doan(goc, chuan, tra, d.get("trich", ""))
        if m:
            d["bat_dau"], d["ket_thuc"], d["cach_tim"] = m
        else:
            d["khong_tim_thay"] = True
        ra.append(d)

    # bỏ chồng lấn: giữ đoạn dài hơn, vì đoạn ngắn thường là một phần của nó
    co_vt = sorted([d for d in ra if "bat_dau" in d],
                   key=lambda d: (d["bat_dau"] - d["ket_thuc"]))
    giu, da_chiem = [], []
    for d in co_vt:
        if any(not (d["ket_thuc"] <= a or d["bat_dau"] >= b) for a, b in da_chiem):
            d.pop("bat_dau", None); d.pop("ket_thuc", None); d.pop("cach_tim", None)
            d["khong_tim_thay"] = True
            d["ly_do_bo"] = "chồng lấn đoạn khác"
            continue
        da_chiem.append((d["bat_dau"], d["ket_thuc"]))
        giu.append(d)
    return sorted(ra, key=lambda d: d.get("bat_dau", 10 ** 9))


def _cat(s: str, n: int) -> str:
    """Cắt bớt cho vừa ngữ cảnh. Đáp án gốc có câu dài hàng chục nghìn ký tự."""
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "\n…(đã cắt bớt)"


def cham_bang_llm(cau_hoi: str, dap_an: str, ai_tra_loi: str,
                  api_key: str | None = None, model: str | None = None,
                  timeout: int = 300, retries: int = 4) -> dict:
    """Chấm 1 câu. Trả dict theo SCHEMA, kèm `model` và `cham_luc`."""
    key = api_key or API_KEY
    if not key:
        raise RuntimeError("Chưa có GEMINI_API_KEY (đặt biến môi trường trước khi chạy).")
    if not (ai_tra_loi or "").strip():
        raise ValueError("Chưa có câu trả lời của AI để chấm.")
    if not (dap_an or "").strip():
        raise ValueError("Câu này chưa có đáp án gốc — không có chuẩn để chấm.")

    ten_model = model or MODEL
    prompt = (PROMPT
              .replace("{cau_hoi}", _cat(cau_hoi, 4000))
              .replace("{dap_an}", _cat(dap_an, 20000))
              .replace("{ai}", _cat(ai_tra_loi, 20000)))
    url = ENDPOINT.format(model=ten_model) + "?key=" + key
    last = None
    for lan in range(retries + 1):
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": _CONFIGS[_cfg[0]]}
        payload = json.dumps(body).encode("utf-8")
        try:
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            parts = resp["candidates"][0]["content"].get("parts", [])
            # bỏ part "thought" của model suy luận, chỉ lấy phần trả lời
            txt = "".join(p.get("text", "") for p in parts
                          if p.get("text") and not p.get("thought"))
            return _chuan_hoa(_parse_json(txt), ten_model, ai_tra_loi)
        except urllib.error.HTTPError as e:
            msg = e.read()[:400].decode("utf-8", "replace")
            last = f"HTTP {e.code}: {msg}"
            if e.code == 400 and _cfg[0] < len(_CONFIGS) - 1:
                _cfg[0] += 1          # model không nhận config này -> hạ cấp
                continue
            if e.code in _RETRY_STATUS and lan < retries:
                time.sleep(min(2 ** lan, 30))
                continue
            raise RuntimeError(last)
        except (urllib.error.URLError, KeyError, IndexError, ValueError) as e:
            last = repr(e)
            if lan < retries:
                time.sleep(min(2 ** lan, 30))
                continue
            raise RuntimeError(last)
    raise RuntimeError(last or "không rõ lỗi")


def _chuan_hoa(o: dict, ten_model: str, ai_tra_loi: str = "") -> dict:
    """Ép về đúng kiểu. Model có thể trả điểm dạng chuỗi, hoặc ket_luan lạ."""
    def _ds(x):
        if isinstance(x, list):
            return [str(i).strip() for i in x if str(i).strip()][:8]
        return []

    def _diem(x):
        try:
            return max(0, min(100, int(round(float(x)))))
        except Exception:
            return 0

    kl = str(o.get("ket_luan", "")).strip().lower().replace(" ", "_")
    if kl not in KET_LUAN_HOP_LE:
        kl = "mot_phan"
    kq = {
        "ket_luan": kl,
        "diem_noi_dung": _diem(o.get("diem_noi_dung")),
        "diem_can_cu": _diem(o.get("diem_can_cu")),
        "y_dung": _ds(o.get("y_dung")),
        "y_thieu": _ds(o.get("y_thieu")),
        "y_sai": _ds(o.get("y_sai")),
        "can_cu_sai": _ds(o.get("can_cu_sai")),
        "lap_luan": (str(o.get("lap_luan", "")).strip().lower().replace(" ", "_")
                     if str(o.get("lap_luan", "")).strip().lower().replace(" ", "_")
                     in LAP_LUAN_HOP_LE else "co_lo_hong"),
        "nhan_xet": str(o.get("nhan_xet", "")).strip(),
        "doan": _doan(o.get("doan"), ai_tra_loi),
        "model": ten_model,
        "cham_luc": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    # Quy tắc 4 trong prompt: model hay quên. Ép lại ở đây cho chắc.
    if kq["ket_luan"] == "trai_nguoc":
        kq["diem_noi_dung"] = min(kq["diem_noi_dung"], 20)
    # để giao diện nói thật: bao nhiêu đoạn tô được lên văn bản
    kq["so_doan"] = len(kq["doan"])
    kq["so_doan_to_duoc"] = sum(1 for d in kq["doan"] if "bat_dau" in d)
    return kq


def _doan(ds, ai_tra_loi: str) -> list:
    """Lọc, chuẩn hoá rồi định vị từng đoạn nhận xét trong câu trả lời của AI."""
    if not isinstance(ds, list):
        return []
    sach = []
    for d in ds[:14]:
        if not isinstance(d, dict):
            continue
        trich = str(d.get("trich", "")).strip()
        if not trich:
            continue
        loai = str(d.get("loai", "")).strip().lower().replace(" ", "_")
        if loai not in LOAI_DOAN_HOP_LE:
            loai = "khong_chac"
        sach.append({"trich": trich, "loai": loai,
                     "ly_do": str(d.get("ly_do", "")).strip()})
    return gan_vi_tri(sach, ai_tra_loi)


# ---------------------------------------------------------------- dòng lệnh

def _doc_tu_db(cau_hoi_id: int):
    import psycopg2
    dsn = (os.environ.get("DATABASE_URL")
           or "postgresql://questions:questions@172.16.10.71:5433/questions")
    with psycopg2.connect(dsn) as cn, cn.cursor() as cur:
        cur.execute("SELECT cau_hoi, dap_an, ai_tra_loi FROM cau_hoi WHERE cau_hoi_id=%s",
                    (cau_hoi_id,))
        r = cur.fetchone()
    if not r:
        raise SystemExit(f"Không có câu hỏi #{cau_hoi_id}")
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="Chấm câu trả lời AI bằng Gemini")
    ap.add_argument("--id", type=int, help="chấm câu hỏi này trong DB")
    ap.add_argument("--cau-hoi", default="")
    ap.add_argument("--dap-an", default="")
    ap.add_argument("--ai", default="")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()

    if a.id:
        cau_hoi, dap_an, ai = _doc_tu_db(a.id)
        if not (ai or "").strip():
            raise SystemExit(f"Câu #{a.id} chưa có ai_tra_loi trong DB "
                             "(dán câu trả lời AI ở trang chủ trước).")
    else:
        cau_hoi, dap_an, ai = a.cau_hoi, a.dap_an, a.ai
        if not dap_an or not ai:
            raise SystemExit("Cần --id, hoặc cả --dap-an lẫn --ai.")

    kq = cham_bang_llm(cau_hoi, dap_an, ai, model=a.model)
    print(json.dumps(kq, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
