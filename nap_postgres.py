# -*- coding: utf-8 -*-
"""
Nạp dataset hỏi - đáp (JSON) vào PostgreSQL theo schema.sql.

3 chế độ:
  --dry-run                 : chỉ đọc JSON, in thống kê sẽ nạp (KHÔNG cần DB).
  --emit-sql nap.sql        : sinh file SQL (INSERT) để chạy trong DataGrip (không cần driver/mật khẩu).
  (mặc định / --load)       : kết nối và nạp trực tiếp (idempotent, chạy lại không trùng).

KẾT NỐI (khi nạp trực tiếp) — KHÔNG ghi mật khẩu trong code, lấy từ biến môi trường:
  PGHOST=172.16.10.71 PGPORT=5432 PGDATABASE=questions PGUSER=... PGPASSWORD=...
hoặc:  --dsn "postgresql://user:pass@172.16.10.71:5432/questions"

Ví dụ:
  python nap_postgres.py --dry-run
  python nap_postgres.py --emit-sql nap_du_lieu.sql --with-schema
  PGPASSWORD=xxx python nap_postgres.py --schema-file schema.sql plo_hoidap_dataset.json

Mặc định nạp file: plo_hoidap_dataset.json (truyền thêm file để nạp nhiều nguồn).
"""

import argparse, hashlib, json, os, re, sys, unicodedata
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

# nguon (chuỗi trong dữ liệu) -> (ma, tên đầy đủ, website)
SRC_MAP = {
    "tuoitre.vn/plo": ("plo", "Báo Pháp Luật TP.HCM (PLO)", "https://tuoitre.vn/plo"),
    "chinhsachonline.chinhphu.vn": ("chinhsachonline", "Giải đáp chính sách Online - Cổng TTĐT Chính phủ", "https://chinhsachonline.chinhphu.vn"),
    "luatvietnam.vn": ("luatvietnam", "LuatVietnam", "https://luatvietnam.vn"),
    "hethongphapluat.com": ("htpl", "Hệ Thống Pháp Luật Việt Nam", "https://hethongphapluat.com"),
}
_LOAI = ["Bộ luật", "Luật", "Thông tư liên tịch", "Thông tư", "Nghị định",
         "Nghị quyết", "Quyết định", "Pháp lệnh", "Văn bản hợp nhất", "Hiến pháp"]


def strip_dia(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def src_of(nguon):
    if nguon in SRC_MAP: return SRC_MAP[nguon]
    ma = re.sub(r"[^a-z0-9]+", "_", strip_dia((nguon or "khac").lower())).strip("_")[:24] or "khac"
    return (ma, nguon or "Khác", "")


def doc_key(ten, so_hieu):
    if so_hieu and so_hieu.strip():
        return "sh:" + re.sub(r"\s+", "", so_hieu.lower())
    return "tn:" + re.sub(r"\s+", " ", strip_dia((ten or "").lower())).strip()


def doc_loai(ten):
    t = (ten or "").strip()
    for k in _LOAI:
        if t.startswith(k): return k
    if "Hiến pháp" in t: return "Hiến pháp"
    return None


def parse_date(s):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", s or "")
    if not m: return None
    d, mo, y, hh, mm = int(m[1]), int(m[2]), int(m[3]), int(m[4] or 0), int(m[5] or 0)
    try: return datetime(y, mo, d, hh, mm)
    except ValueError: return None


def content_hash(nguon, tieu_de, cau_hoi):
    return hashlib.md5(("|".join([nguon or "", tieu_de or "", cau_hoi or ""])).encode("utf-8")).hexdigest()


class Model:
    """Gom dữ liệu đã chuẩn hóa từ các file JSON."""
    def __init__(self):
        self.sources = {}   # ma -> (ten, website)
        self.topics = set()
        self.docs = {}      # khoa -> {so_hieu, ten, loai, link}
        self.questions = [] # dict đã chuẩn hóa

    def add_doc(self, ten, so_hieu, link):
        if not ten: return None
        k = doc_key(ten, so_hieu)
        d = self.docs.get(k)
        if not d:
            self.docs[k] = {"so_hieu": so_hieu or None, "ten": ten,
                            "loai": doc_loai(ten), "link": link or None}
        else:
            if not d["so_hieu"] and so_hieu: d["so_hieu"] = so_hieu
            if not d["link"] and link: d["link"] = link
        return k

    def add_record(self, r):
        nguon = r.get("nguon", "")
        ma, ten, web = src_of(nguon)
        self.sources[ma] = (ten, web)
        topic = (r.get("linh_vuc") or "Khác").strip() or "Khác"
        self.topics.add(topic)

        doc_links, cites = [], []
        for v in r.get("van_ban_dan_chieu", []) or []:
            k = self.add_doc(v.get("ten"), v.get("so_hieu"), v.get("link"))
            if k: doc_links.append(k)
        for c in r.get("trich_dan", []) or []:
            k = self.add_doc(c.get("van_ban"), c.get("so_hieu"), c.get("link"))
            cites.append({"khoa": k, "dieu": c.get("dieu") or None, "khoan": c.get("khoan") or None,
                          "diem": c.get("diem") or None, "goc": c.get("trich_dan_goc") or None,
                          "link": c.get("link") or None})

        self.questions.append({
            "src": ma, "topic": topic, "chuyen_muc": r.get("chuyen_muc") or None,
            "tieu_de": r.get("tieu_de") or "", "cau_hoi": r.get("cau_hoi") or None,
            "dap_an": r.get("dap_an") or None, "ngay_text": r.get("ngay") or None,
            "ngay_dang": parse_date(r.get("ngay")), "url": r.get("url") or None,
            "hash": content_hash(nguon, r.get("tieu_de"), r.get("cau_hoi")),
            "doc_links": sorted(set(doc_links)), "cites": cites, "raw": r,
        })


def build(files):
    m = Model()
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            print(f"! Bỏ qua {fp}: không phải mảng JSON.", file=sys.stderr); continue
        for r in data: m.add_record(r)
        print(f"  đọc {fp}: {len(data)} bản ghi")
    return m


def stats(m):
    print(f"\n=== SẼ NẠP ===")
    print(f"  Nguồn      : {len(m.sources)}  -> {', '.join(sorted(m.sources))}")
    print(f"  Chủ đề     : {len(m.topics)}")
    print(f"  Câu hỏi    : {len(m.questions)}  (hash duy nhất: {len({q['hash'] for q in m.questions})})")
    print(f"  Văn bản    : {len(m.docs)}")
    print(f"  Liên kết văn bản (cau_hoi_van_ban): {sum(len(q['doc_links']) for q in m.questions)}")
    print(f"  Trích dẫn  (trich_dan)            : {sum(len(q['cites']) for q in m.questions)}")
    nd = sum(1 for q in m.questions if q['ngay_dang'] is None)
    if nd: print(f"  (cảnh báo) {nd} câu không parse được ngày")


# --------------------------- NẠP TRỰC TIẾP (psycopg2) ---------------------------
def load_db(m, args):
    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(args.dsn) if args.dsn else psycopg2.connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        if args.schema_file:
            with open(args.schema_file, encoding="utf-8") as f:
                cur.execute(f.read())
            print(f"  đã áp dụng {args.schema_file}")

        if getattr(args, "reset", False):
            cur.execute("TRUNCATE cau_hoi, van_ban, chu_de, nguon, cau_hoi_van_ban, trich_dan "
                        "RESTART IDENTITY CASCADE")
            print("  ⟳ đã TRUNCATE toàn bộ bảng (nạp lại từ đầu)")

        # nguon
        src_id = {}
        for ma, (ten, web) in m.sources.items():
            cur.execute("""INSERT INTO nguon(ma,ten,website) VALUES(%s,%s,%s)
                           ON CONFLICT(ma) DO UPDATE SET ten=EXCLUDED.ten
                           RETURNING nguon_id""", (ma, ten, web or None))
            src_id[ma] = cur.fetchone()[0]

        # chu_de
        execute_values(cur, "INSERT INTO chu_de(ten) VALUES %s ON CONFLICT(ten) DO NOTHING",
                       [(t,) for t in sorted(m.topics)])
        cur.execute("SELECT ten,chu_de_id FROM chu_de")
        topic_id = dict(cur.fetchall())

        # van_ban
        execute_values(cur, """INSERT INTO van_ban(khoa,so_hieu,ten,loai,link) VALUES %s
                               ON CONFLICT(khoa) DO UPDATE SET
                                 so_hieu=COALESCE(van_ban.so_hieu,EXCLUDED.so_hieu),
                                 link=COALESCE(van_ban.link,EXCLUDED.link)""",
                       [(k, d["so_hieu"], d["ten"], d["loai"], d["link"]) for k, d in m.docs.items()])
        cur.execute("SELECT khoa,van_ban_id FROM van_ban")
        doc_id = dict(cur.fetchall())

        # cau_hoi + liên kết
        ins = 0
        for q in m.questions:
            cur.execute("""INSERT INTO cau_hoi(nguon_id,chu_de_id,chuyen_muc,tieu_de,cau_hoi,dap_an,
                               ngay_dang,ngay_text,url,content_hash,raw)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT(content_hash) DO UPDATE SET tieu_de=EXCLUDED.tieu_de
                           RETURNING cau_hoi_id""",
                        (src_id[q["src"]], topic_id.get(q["topic"]), q["chuyen_muc"], q["tieu_de"],
                         q["cau_hoi"], q["dap_an"], q["ngay_dang"], q["ngay_text"], q["url"],
                         q["hash"], json.dumps(q["raw"], ensure_ascii=False)))
            cid = cur.fetchone()[0]
            # idempotent: xóa liên kết cũ của câu này rồi nạp lại
            cur.execute("DELETE FROM cau_hoi_van_ban WHERE cau_hoi_id=%s", (cid,))
            cur.execute("DELETE FROM trich_dan WHERE cau_hoi_id=%s", (cid,))
            if q["doc_links"]:
                execute_values(cur, "INSERT INTO cau_hoi_van_ban(cau_hoi_id,van_ban_id) VALUES %s",
                               [(cid, doc_id[k]) for k in q["doc_links"] if k in doc_id])
            if q["cites"]:
                execute_values(cur, """INSERT INTO trich_dan(cau_hoi_id,van_ban_id,dieu,khoan,diem,trich_dan_goc,link)
                                       VALUES %s""",
                               [(cid, doc_id.get(c["khoa"]), c["dieu"], c["khoan"], c["diem"], c["goc"], c["link"])
                                for c in q["cites"]])
            ins += 1
            if ins % 200 == 0: print(f"    ... {ins}/{len(m.questions)}")
        conn.commit()
        print(f"\n✓ Đã nạp {ins} câu hỏi vào PostgreSQL.")
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


# --------------------------- SINH FILE SQL ---------------------------
def q(s):
    return "NULL" if s is None else "'" + str(s).replace("'", "''") + "'"

def emit_sql(m, out, with_schema):
    src_id = {ma: i for i, ma in enumerate(sorted(m.sources), 1)}
    topic_id = {t: i for i, t in enumerate(sorted(m.topics), 1)}
    doc_id = {k: i for i, k in enumerate(m.docs, 1)}
    L = []
    if with_schema and os.path.exists("schema.sql"):
        L.append(open("schema.sql", encoding="utf-8").read())
    L.append("BEGIN;")
    for ma, i in src_id.items():
        ten, web = m.sources[ma]
        L.append(f"INSERT INTO nguon(nguon_id,ma,ten,website) VALUES({i},{q(ma)},{q(ten)},{q(web or None)}) ON CONFLICT(ma) DO NOTHING;")
    for t, i in topic_id.items():
        L.append(f"INSERT INTO chu_de(chu_de_id,ten) VALUES({i},{q(t)}) ON CONFLICT(ten) DO NOTHING;")
    for k, i in doc_id.items():
        d = m.docs[k]
        L.append(f"INSERT INTO van_ban(van_ban_id,khoa,so_hieu,ten,loai,link) VALUES({i},{q(k)},{q(d['so_hieu'])},{q(d['ten'])},{q(d['loai'])},{q(d['link'])}) ON CONFLICT(khoa) DO NOTHING;")
    for i, qq in enumerate(m.questions, 1):
        raw = json.dumps(qq["raw"], ensure_ascii=False)
        nd = q(qq["ngay_dang"].strftime("%Y-%m-%d %H:%M:%S")) if qq["ngay_dang"] else "NULL"
        L.append("INSERT INTO cau_hoi(cau_hoi_id,nguon_id,chu_de_id,chuyen_muc,tieu_de,cau_hoi,dap_an,ngay_dang,ngay_text,url,content_hash,raw) "
                 f"VALUES({i},{src_id[qq['src']]},{topic_id.get(qq['topic'],'NULL')},{q(qq['chuyen_muc'])},{q(qq['tieu_de'])},{q(qq['cau_hoi'])},{q(qq['dap_an'])},{nd},{q(qq['ngay_text'])},{q(qq['url'])},{q(qq['hash'])},{q(raw)}::jsonb) ON CONFLICT(content_hash) DO NOTHING;")
        for k in qq["doc_links"]:
            if k in doc_id:
                L.append(f"INSERT INTO cau_hoi_van_ban(cau_hoi_id,van_ban_id) VALUES({i},{doc_id[k]}) ON CONFLICT DO NOTHING;")
        for c in qq["cites"]:
            L.append("INSERT INTO trich_dan(cau_hoi_id,van_ban_id,dieu,khoan,diem,trich_dan_goc,link) "
                     f"VALUES({i},{doc_id.get(c['khoa'],'NULL')},{q(c['dieu'])},{q(c['khoan'])},{q(c['diem'])},{q(c['goc'])},{q(c['link'])});")
    # đồng bộ lại sequence identity
    for tbl, col in [("nguon","nguon_id"),("chu_de","chu_de_id"),("van_ban","van_ban_id"),
                     ("cau_hoi","cau_hoi_id"),("trich_dan","trich_dan_id")]:
        L.append(f"SELECT setval(pg_get_serial_sequence('{tbl}','{col}'), COALESCE((SELECT max({col}) FROM {tbl}),1));")
    L.append("COMMIT;")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"✓ Đã ghi SQL -> {out} ({len(L)} câu lệnh). Mở trong DataGrip và Run.")


def main():
    ap = argparse.ArgumentParser(description="Nạp dataset hỏi-đáp JSON vào PostgreSQL.")
    ap.add_argument("files", nargs="*", default=["plo_hoidap_dataset.json"], help="Các file JSON cần nạp")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ in thống kê, không nạp")
    ap.add_argument("--emit-sql", metavar="FILE", help="Sinh file SQL (không cần DB)")
    ap.add_argument("--with-schema", action="store_true", help="Kèm schema.sql vào đầu file SQL sinh ra")
    ap.add_argument("--schema-file", metavar="FILE", help="Chạy file schema trước khi nạp trực tiếp")
    ap.add_argument("--reset", action="store_true", help="TRUNCATE toàn bộ bảng rồi nạp lại từ đầu")
    ap.add_argument("--dsn", help="Chuỗi kết nối; nếu bỏ trống dùng biến môi trường PG*")
    args = ap.parse_args()

    files = args.files if args.files else ["plo_hoidap_dataset.json"]
    print("Đang đọc dữ liệu...")
    m = build(files)
    stats(m)

    if args.dry_run:
        print("\n→ DRY-RUN (không nạp)."); return
    if args.emit_sql:
        emit_sql(m, args.emit_sql, args.with_schema); return
    load_db(m, args)


if __name__ == "__main__":
    main()
