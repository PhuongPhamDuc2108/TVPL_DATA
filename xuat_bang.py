# -*- coding: utf-8 -*-
"""
Xuất 1 bảng (hoặc câu SELECT) trong Postgres ra file JSON.

Dùng:
  python xuat_bang.py                         # mặc định: bảng van_ban -> van_ban.json
  python xuat_bang.py van_ban van_ban.json
  python xuat_bang.py chu_de chu_de.json
  python xuat_bang.py "SELECT * FROM van_ban ORDER BY length(ten) DESC" van_ban_dai.json

DB lấy từ biến môi trường DATABASE_URL, nếu không có dùng mặc định dưới đây.
"""
import sys, os, json
import psycopg2

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

DSN = os.environ.get("DATABASE_URL") or "postgresql://questions:questions@172.16.10.71:5433/questions"
arg = sys.argv[1] if len(sys.argv) > 1 else "van_ban"
out = sys.argv[2] if len(sys.argv) > 2 else (arg if arg.lower().startswith("select") else arg) + ".json"
if arg.lower().startswith("select"):
    sql, out = arg, (sys.argv[2] if len(sys.argv) > 2 else "ket_qua.json")
else:
    sql = f'SELECT * FROM {arg}'

conn = psycopg2.connect(DSN, connect_timeout=8)
cur = conn.cursor()
cur.execute(sql)
cols = [d[0] for d in cur.description]
rows = [dict(zip(cols, r)) for r in cur.fetchall()]
cur.close(); conn.close()

with open(out, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2, default=str)  # default=str: xử lý ngày/Decimal
print(f"✓ Đã lưu {len(rows)} dòng -> {out}")
