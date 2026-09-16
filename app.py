# -*- coding: utf-8 -*-
"""
Backend + Frontend cho kho hỏi - đáp pháp luật.
  - Phục vụ giao diện public/index.html tại "/".
  - API đọc dữ liệu từ PostgreSQL (bảng theo schema.sql).

CHẠY 1 DÒNG (tự mở trình duyệt):
    python app.py
    # hoặc chỉ định DB / cổng:
    #   set DATABASE_URL=postgresql://user:pass@host:5433/questions   (Windows cmd)
    #   set PORT=8000

Cần: fastapi, uvicorn, psycopg2 (đã có trong venv).
"""
import os
import json
import threading
import webbrowser
from datetime import datetime

from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

# DB: ưu tiên biến môi trường DATABASE_URL; nếu không có, dùng mặc định dưới đây
# (sửa cho khớp DB của bạn nếu cần).
DSN = os.environ.get("DATABASE_URL") or "postgresql://questions:questions@172.16.10.71:5433/questions"
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(HERE, "public", "index.html")
DANH_MUC_HTML = os.path.join(HERE, "public", "danh_muc.html")

app = FastAPI(title="Hỏi đáp pháp luật API", version="1.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)

_pool = None
def pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 8, dsn=DSN, connect_timeout=8)
    return _pool

def query(sql, params=None):
    p = pool(); conn = p.getconn()
    try:
        cur = conn.cursor(); cur.execute(sql, params or []); rows = cur.fetchall(); cur.close()
        return rows
    finally:
        p.putconn(conn)


def execute(sql, params=None):
    """Chạy lệnh ghi (DELETE/UPDATE...) có commit; trả số dòng bị tác động."""
    p = pool(); conn = p.getconn()
    try:
        cur = conn.cursor(); cur.execute(sql, params or []); n = cur.rowcount
        conn.commit(); cur.close()
        return n
    except Exception:
        conn.rollback(); raise
    finally:
        p.putconn(conn)


def trang_html(duong_dan: str) -> HTMLResponse:
    """Đọc một file HTML trong public/ và trả về, CẤM trình duyệt cache.

    Trước đây trả thẳng HTMLResponse(f.read()) — không kèm Cache-Control, ETag
    hay Last-Modified nào cả. Không có gì để revalidate, trình duyệt được phép
    tự đoán thời hạn và giữ lại bản cũ; hậu quả là sửa file rồi, khởi động lại
    server rồi, mà trang vẫn chạy JS cũ. Đây là app nội bộ, HTML lại nằm cùng
    máy nên đọc lại mỗi lần chẳng tốn gì -> cấm cache cho dứt điểm.

    X-Trang-Sua-Luc để đối chiếu nhanh: curl -sI <url> | grep Trang-Sua-Luc
    cho biết server đang phục vụ bản sửa lúc nào.
    """
    with open(duong_dan, encoding="utf-8") as f:
        noi_dung = f.read()
    return HTMLResponse(noi_dung, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Trang-Sua-Luc": datetime.fromtimestamp(
            os.path.getmtime(duong_dan)).isoformat(timespec="seconds"),
    })


@app.get("/", response_class=HTMLResponse)
def index():
    return trang_html(INDEX_HTML)


@app.get("/api/health")
def health():
    try:
        n = query("SELECT count(*) FROM cau_hoi")[0][0]
        return {"status": "ok", "db": "connected", "cau_hoi": n}
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)[:200]}, status_code=500)


@app.get("/api/data")
def api_data(
    nguon: str = Query(None, description="lọc theo mã nguồn (plo, chinhsachonline, luatvietnam, htpl)"),
    chu_de: str = Query(None, description="lọc theo tên chủ đề"),
    q: str = Query(None, description="tìm trong tiêu đề / câu hỏi / đáp án"),
    limit: int = Query(0, description="0 = tất cả"),
):
    """Trả danh sách bản ghi (nguyên shape JSON như FE đang dùng) từ cột raw."""
    # `ai_tra_loi` là cột THẬT, không nằm trong raw: nó do người dùng dán vào ô
    # "AI trả lời & đối chiếu căn cứ" chứ không phải dữ liệu crawl về. Trả kèm
    # ở đây để mở trang lên là ô đó tự có nội dung, không phụ thuộc localStorage
    # (localStorage tính theo origin nên đổi localhost <-> IP là mất).
    sql = ["SELECT c.cau_hoi_id, c.raw, c.ai_tra_loi, c.ai_cham FROM cau_hoi c",
           "JOIN nguon n ON n.nguon_id=c.nguon_id",
           "LEFT JOIN chu_de d ON d.chu_de_id=c.chu_de_id"]
    where, params = [], []
    if nguon:  where.append("n.ma=%s");  params.append(nguon)
    if chu_de: where.append("d.ten=%s"); params.append(chu_de)
    if q:
        where.append("(c.tieu_de ILIKE %s OR c.cau_hoi ILIKE %s OR c.dap_an ILIKE %s)")
        params += ["%%%s%%" % q] * 3
    if where: sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY c.ngay_dang DESC NULLS LAST, c.cau_hoi_id")
    if limit and limit > 0: sql.append("LIMIT %s"); params.append(limit)

    rows = query(" ".join(sql), params)
    out = []
    for (cid, raw, ai, cham) in rows:
        rec = raw if isinstance(raw, (dict, list)) else json.loads(raw)
        if isinstance(rec, dict):
            rec["cau_hoi_id"] = cid   # gắn id DB để FE hiển thị cột id
            rec["ai_tra_loi"] = ai    # '' nếu chưa dán, FE dùng để đổ vào ô
            rec["ai_cham"] = cham     # kết quả chấm LLM đã lưu, None nếu chưa chấm
        out.append(rec)
    return JSONResponse(out)


@app.get("/api/stats")
def api_stats():
    total = query("SELECT count(*) FROM cau_hoi")[0][0]
    topics = query("""SELECT d.ten, count(*) FROM cau_hoi c JOIN chu_de d ON d.chu_de_id=c.chu_de_id
                      GROUP BY 1 ORDER BY 2 DESC""")
    sources = query("""SELECT n.ten, count(*) FROM cau_hoi c JOIN nguon n ON n.nguon_id=c.nguon_id
                       GROUP BY 1 ORDER BY 2 DESC""")
    docs = query("SELECT so_hieu, ten, so_luot_trich_dan, so_cau_hoi FROM v_van_ban_pho_bien LIMIT 25")
    return {
        "total": total,
        "topics": [{"ten": t, "n": n} for t, n in topics],
        "sources": [{"ten": s, "n": n} for s, n in sources],
        "top_van_ban": [{"so_hieu": sh, "ten": tn, "luot": lt, "so_cau": sc} for sh, tn, lt, sc in docs],
    }


# --------------------------------------------------------------------------
#  DANH MỤC trong văn bản pháp luật (bảng danh_muc — xem DANH_MUC_README.md)
# --------------------------------------------------------------------------

def _chua_co_bang(e: Exception) -> bool:
    return "danh_muc" in str(e) and "does not exist" in str(e)


_THIEU_BANG = {"ok": False, "detail": "Chưa có bảng danh_muc. Chạy: "
                                      "python nap_danh_muc_v3.py --load "
                                      "--schema-file schema_danh_muc_v3.sql"}


@app.get("/danh-muc", response_class=HTMLResponse)
def trang_danh_muc():
    return trang_html(DANH_MUC_HTML)


@app.get("/api/danh-muc/bo-loc")
def api_danh_muc_bo_loc():
    """Các giá trị để dựng bộ lọc: mã danh mục, văn bản, phần mục (kèm số lượng)."""
    try:
        # so_dong = tổng dòng (bằng số hàng bảng vẽ ra); so_muc = mục THẬT,
        # không tính dòng nhóm / ghi chú / nối tiếp. Trả cả hai để con số trên
        # chip khớp với bảng, mà chân trang vẫn nói được số mục thật.
        dm = query("""SELECT ma, coalesce(ten_ngan, ten), so_dong, ten, luu_y,
                             nhan_cap, nhan_ten, nhan_ten_khac, nhan_ma,
                             nhan_mo_ta, so_muc, nhan_ten_nhom
                      FROM danh_muc ORDER BY ma""")
        vb = query("""SELECT dm.ma, ct.van_ban, max(dm.ten), count(*)
                      FROM danh_muc_chi_tiet ct JOIN danh_muc dm USING (danh_muc_id)
                      GROUP BY 1,2 ORDER BY 1,2""")
        pm = query("""SELECT dm.ma, ct.duong_dan[1], count(*)
                      FROM danh_muc_chi_tiet ct JOIN danh_muc dm USING (danh_muc_id)
                      GROUP BY 1,2 ORDER BY 1, min(ct.muc_id)""")
    except Exception as e:
        if _chua_co_bang(e):
            return JSONResponse(_THIEU_BANG, status_code=503)
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)
    return {
        # `nhan` là nhãn của các cột dùng chung ở bảng chi tiết — mỗi danh mục
        # đặt tên khác nhau, giao diện lấy từ đây thay vì hiển thị cứng.
        # `nhan_cap` là nhãn TỪNG TẦNG của duong_dan, ghép theo chỉ số.
        "danh_muc": [{"ma": m, "ten": t, "n": n, "n_muc": nm,
                      "ten_day_du": td, "luu_y": ly,
                      "nhan_cap": nc or [],
                      "nhan": {"ten": nt, "ten_khac": ntk, "ma_cas": nma,
                               "mo_ta": nmt, "ten_nhom": ntn}}
                     for m, t, n, td, ly, nc, nt, ntk, nma, nmt, nm, ntn in dm],
        "van_ban": [{"ma_danh_muc": m, "so_hieu": sh, "ten": tn, "n": n}
                    for m, sh, tn, n in vb],
        "phan_muc": [{"ma_danh_muc": m, "phan_muc": p, "n": n} for m, p, n in pm],
        "tong": sum(r[2] for r in dm),
    }


@app.get("/api/danh-muc")
def api_danh_muc(
    ma_danh_muc: str = Query(None, description="nghe_nndhnh | hoa_chat_nd24"),
    so_hieu: str = Query(None, description="lọc theo số hiệu văn bản"),
    phan_muc: str = Query(None, description="lĩnh vực / phụ lục"),
    cas: str = Query(None, description="tra CHÍNH XÁC một mã CAS"),
    q: str = Query(None, description="tìm trong tên / tên khoa học / mô tả"),
    limit: int = Query(0, description="0 = tất cả"),
):
    # Đọc từ VIEW chứ không từ bảng: `loai_muc` và `nhan_ten` là hai cột tính
    # tại chỗ ở đó (nhãn cột `ten` phụ thuộc TỪNG DÒNG — Bảng B của Phụ lục IV
    # liệt kê nhóm nguy hại nên nhãn là 'Nhóm hóa chất', không phải 'Tên chất').
    # Viết lại luật ở đây thì sẽ có hai bản dễ lệch nhau.
    sql = ["SELECT ct.muc_id, ct.ma_danh_muc, dm.ten, ct.van_ban, ct.van_ban_id,",
           # vb.ten là tên đầy đủ ('Thông tư 19/2023/TT-BLĐTBXH ban hành bổ
           # sung…'), vb.link là URL nguồn chính thức — cả hai lấy từ bảng
           # `van_ban` qua khóa ngoại ct.van_ban_id
           "       vb.ten AS ten_van_ban, vb.link,",
           "       ct.duong_dan, ct.loai_muc, ct.nhan_ten,",
           "       ct.stt, ct.ten, ct.ten_khac, ct.ma_cas,",
           "       ct.cong_thuc_hoa_hoc, ct.nguong_khoi_luong_kg, ct.mo_ta",
           "FROM v_danh_muc_chi_tiet ct",
           "JOIN danh_muc dm ON dm.ma = ct.ma_danh_muc",
           "LEFT JOIN van_ban vb ON vb.van_ban_id = ct.van_ban_id"]
    where, params = [], []
    if ma_danh_muc: where.append("ct.ma_danh_muc = %s"); params.append(ma_danh_muc)
    if so_hieu:     where.append("ct.van_ban = %s"); params.append(so_hieu)
    # `phan_muc` giữ tên tham số cũ nhưng giờ lọc theo TẦNG 1 của đường dẫn
    if phan_muc:    where.append("ct.duong_dan[1] = %s"); params.append(phan_muc)
    # ma_cas là text ngăn bởi '; ' -> tách ra rồi so khớp NGUYÊN mã, tránh
    # '43-2' khớp nhầm vào giữa '71-43-2'
    if cas:
        where.append("%s = ANY(string_to_array(ct.ma_cas, '; '))")
        params.append(cas.strip())
    if q:
        where.append("(ct.ten ILIKE %s OR ct.ten_khac ILIKE %s "
                     "OR ct.mo_ta ILIKE %s)")
        params += ["%%%s%%" % q] * 3
    if where: sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY ct.muc_id")
    if limit and limit > 0: sql.append("LIMIT %s"); params.append(limit)

    try:
        rows = query(" ".join(sql), params)
    except Exception as e:
        if _chua_co_bang(e):
            return JSONResponse(_THIEU_BANG, status_code=503)
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    cot = ["muc_id", "ma_danh_muc", "ten_danh_muc", "van_ban", "van_ban_id",
           "ten_van_ban", "link", "duong_dan", "loai_muc", "nhan_ten",
           "stt", "ten", "ten_khac", "ma_cas",
           "cong_thuc_hoa_hoc", "nguong_khoi_luong_kg", "mo_ta"]
    return JSONResponse([dict(zip(cot, r)) for r in rows])


@app.put("/api/cau_hoi/{cau_hoi_id}")
def update_cau_hoi(cau_hoi_id: int, payload: dict = Body(...)):
    """Cập nhật câu hỏi & đáp án của ĐÚNG 1 câu.
    Ghi cả cột thật (cau_hoi/dap_an) LẪN cột raw (JSON app đang đọc) để đồng bộ."""
    cau_hoi = payload.get("cau_hoi")
    dap_an  = payload.get("dap_an")
    try:
        n = execute(
            "UPDATE cau_hoi SET cau_hoi = %s, dap_an = %s, "
            "raw = jsonb_set(jsonb_set(COALESCE(raw, '{}'::jsonb), "
            "'{cau_hoi}', to_jsonb(%s::text)), '{dap_an}', to_jsonb(%s::text)) "
            "WHERE cau_hoi_id = %s",
            [cau_hoi, dap_an, cau_hoi, dap_an, cau_hoi_id])
        if n == 0:
            return JSONResponse({"ok": False, "detail": "Không tìm thấy câu hỏi"}, status_code=404)
        return {"ok": True, "updated": n, "cau_hoi_id": cau_hoi_id}
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)


@app.api_route("/api/cau_hoi/{cau_hoi_id}/ai-tra-loi", methods=["PUT", "POST"])
def save_ai_tra_loi(cau_hoi_id: int, payload: dict = Body(...)):
    """Lưu câu trả lời của AI đã dán ở cột phải trang chủ.

    Gọi tự động mỗi lần gõ/dán (FE gộp lại rồi mới gửi), nên phải rẻ và im
    lặng: chỉ đụng 2 cột, không đụng `raw`, không đụng cau_hoi/dap_an.
    Ô rỗng -> ghi NULL, tức là 'chưa chấm câu này', chứ không phải chuỗi rỗng.

    Nhận cả POST vì lúc đóng tab, FE gửi nốt bằng navigator.sendBeacon() —
    hàm đó chỉ gửi được POST, và fetch() thường bị huỷ giữa chừng khi trang đóng.
    """
    van_ban = payload.get("ai_tra_loi")
    van_ban = van_ban.strip() if isinstance(van_ban, str) else None
    try:
        n = execute("UPDATE cau_hoi SET ai_tra_loi = %s, "
                    "ai_cap_nhat = CASE WHEN %s IS NULL THEN NULL ELSE now() END "
                    "WHERE cau_hoi_id = %s",
                    [van_ban or None, van_ban or None, cau_hoi_id])
        if n == 0:
            return JSONResponse({"ok": False, "detail": "Không tìm thấy câu hỏi"},
                                status_code=404)
        return {"ok": True, "cau_hoi_id": cau_hoi_id, "so_ky_tu": len(van_ban or "")}
    except Exception as e:
        loi = str(e)
        if 'ai_tra_loi' in loi and 'does not exist' in loi:
            return JSONResponse(
                {"ok": False, "detail": "Chưa có cột ai_tra_loi. Chạy file "
                                        "schema_ai_tra_loi.sql rồi thử lại."},
                status_code=503)
        return JSONResponse({"ok": False, "detail": loi[:200]}, status_code=500)


@app.post("/api/cau_hoi/{cau_hoi_id}/cham-llm")
def cham_llm_endpoint(cau_hoi_id: int, payload: dict = Body(default={})):
    """Chấm câu trả lời của AI bằng LLM, lấy đáp án gốc làm chuẩn.

    Khác hẳn phần "độ tương đồng" chạy trong trình duyệt: chỗ đó chỉ đo trùng
    lặp TỪ NGỮ (câu đúng mà diễn đạt khác chỉ được ~20%), còn đây chấm theo Ý.

    Gọi tốn tiền và tốn thời gian nên:
      * lưu kết quả vào cau_hoi.ai_cham -> mở lại trang không phải chấm lại;
      * có sẵn kết quả thì trả luôn, trừ khi truyền {"bat_buoc": true}.
    Nếu body có `ai_tra_loi` thì LƯU trước rồi mới chấm, để nội dung đang gõ dở
    trên màn hình và nội dung được chấm luôn là một.
    """
    van_ban = payload.get("ai_tra_loi")
    van_ban = van_ban.strip() if isinstance(van_ban, str) else None
    bat_buoc = bool(payload.get("bat_buoc"))

    try:
        if van_ban is not None:
            execute("UPDATE cau_hoi SET ai_tra_loi=%s, ai_cap_nhat=now() "
                    "WHERE cau_hoi_id=%s", [van_ban or None, cau_hoi_id])

        r = query("SELECT cau_hoi, dap_an, ai_tra_loi, ai_cham "
                  "FROM cau_hoi WHERE cau_hoi_id=%s", [cau_hoi_id])
        if not r:
            return JSONResponse({"ok": False, "detail": "Không tìm thấy câu hỏi"},
                                status_code=404)
        cau_hoi, dap_an, ai_tra_loi, ai_cham = r[0]

        if ai_cham and not bat_buoc:
            return {"ok": True, "cau_hoi_id": cau_hoi_id, "ket_qua": ai_cham,
                    "tu_bo_nho": True}
        if not (ai_tra_loi or "").strip():
            return JSONResponse({"ok": False, "detail":
                                 "Chưa có câu trả lời của AI để chấm."},
                                status_code=400)
        if not (dap_an or "").strip():
            return JSONResponse({"ok": False, "detail":
                                 "Câu này chưa có đáp án gốc — không có chuẩn để chấm."},
                                status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)

    # Import trong hàm: thiếu GEMINI_API_KEY hay thiếu file cham_llm.py thì chỉ
    # hỏng đúng endpoint này, cả app vẫn chạy bình thường.
    try:
        from cham_llm import cham_bang_llm
    except Exception as e:
        return JSONResponse({"ok": False, "detail":
                             f"Không nạp được cham_llm.py: {str(e)[:160]}"},
                            status_code=503)
    try:
        kq = cham_bang_llm(cau_hoi or "", dap_an, ai_tra_loi)
    except Exception as e:
        loi = str(e)
        ma = 503 if ("GEMINI_API_KEY" in loi or "HTTP 4" in loi or "HTTP 5" in loi) else 500
        return JSONResponse({"ok": False, "detail": loi[:300]}, status_code=ma)

    try:
        execute("UPDATE cau_hoi SET ai_cham=%s::jsonb, ai_cham_luc=now() "
                "WHERE cau_hoi_id=%s",
                [json.dumps(kq, ensure_ascii=False), cau_hoi_id])
    except Exception as e:
        # Chấm xong rồi thì phải trả kết quả cho người dùng, đừng vì lỗi ghi mà
        # vứt đi cả lần gọi API vừa tốn.
        return {"ok": True, "cau_hoi_id": cau_hoi_id, "ket_qua": kq,
                "canh_bao": f"Chấm xong nhưng chưa lưu được vào DB: {str(e)[:160]}"}
    return {"ok": True, "cau_hoi_id": cau_hoi_id, "ket_qua": kq, "tu_bo_nho": False}


@app.delete("/api/cau_hoi/{cau_hoi_id}/cham-llm")
def xoa_cham_llm(cau_hoi_id: int):
    """Bỏ kết quả chấm đã lưu, để lần sau bấm là chấm lại từ đầu."""
    try:
        n = execute("UPDATE cau_hoi SET ai_cham=NULL, ai_cham_luc=NULL "
                    "WHERE cau_hoi_id=%s", [cau_hoi_id])
        return {"ok": True, "cleared": n}
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)


@app.delete("/api/cau_hoi/{cau_hoi_id}")
def delete_cau_hoi(cau_hoi_id: int):
    """Xóa ĐÚNG 1 câu hỏi theo cau_hoi_id.
    trich_dan & cau_hoi_van_ban tự xóa theo nhờ ON DELETE CASCADE."""
    try:
        n = execute("DELETE FROM cau_hoi WHERE cau_hoi_id = %s", [cau_hoi_id])
        if n == 0:
            return JSONResponse({"ok": False, "detail": "Không tìm thấy câu hỏi"}, status_code=404)
        return {"ok": True, "deleted": n, "cau_hoi_id": cau_hoi_id}
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)


@app.put("/api/cau_hoi/{cau_hoi_id}/raw")
def save_raw(cau_hoi_id: int, payload: dict = Body(...)):
    """Lưu TOÀN BỘ bản ghi JSON (kể cả van_ban_dan_chieu/trich_dan) vào cột raw,
    đồng bộ cột cau_hoi/dap_an. (Bảng chuẩn hoá van_ban/trich_dan giữ nguyên — nếu
    cần thống kê SQL chính xác thì nạp lại bằng nap_postgres.py)."""
    try:
        n = execute(
            "UPDATE cau_hoi SET raw = %s::jsonb, cau_hoi = %s, dap_an = %s WHERE cau_hoi_id = %s",
            [json.dumps(payload, ensure_ascii=False), payload.get("cau_hoi"), payload.get("dap_an"), cau_hoi_id])
        if n == 0:
            return JSONResponse({"ok": False, "detail": "Không tìm thấy câu hỏi"}, status_code=404)
        return {"ok": True, "cau_hoi_id": cau_hoi_id}
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)


@app.post("/api/cau_hoi/delete")
def delete_many(payload: dict = Body(...)):
    """Xóa NHIỀU câu hỏi cùng lúc theo danh sách id (trich_dan/cau_hoi_van_ban tự xóa theo CASCADE)."""
    try:
        ids = [int(x) for x in (payload.get("ids") or []) if x is not None]
        if not ids:
            return {"ok": True, "deleted": 0}
        n = execute("DELETE FROM cau_hoi WHERE cau_hoi_id = ANY(%s)", [ids])
        return {"ok": True, "deleted": n}
    except Exception as e:
        return JSONResponse({"ok": False, "detail": str(e)[:200]}, status_code=500)


def _open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8002"))
    try:
        print(f"→ Giao diện: http://127.0.0.1:{port}   (DB: {DSN.split('@')[-1]})")
    except UnicodeEncodeError:
        print(f"Giao dien: http://127.0.0.1:{port}   (DB: {DSN.split('@')[-1]})")
    threading.Timer(1.2, _open_browser, args=(port,)).start()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
