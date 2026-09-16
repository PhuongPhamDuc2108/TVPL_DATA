# -*- coding: utf-8 -*-
"""
Xoá 1 (hoặc vài) câu hỏi khỏi DB PostgreSQL.

Bảng con trich_dan / cau_hoi_van_ban có ON DELETE CASCADE nên chỉ cần
DELETE ở bảng cau_hoi -> con tự xoá theo.

Cách dùng (chạy trong venv):
    venv\\Scripts\\python.exe xoa_cau_hoi.py --url  "https://plo.vn/..."
    venv\\Scripts\\python.exe xoa_cau_hoi.py --id   1234
    venv\\Scripts\\python.exe xoa_cau_hoi.py --hash "abcdef..."
    venv\\Scripts\\python.exe xoa_cau_hoi.py --tieu-de "một phần tiêu đề"   # tìm gần đúng

Mặc định chỉ XEM TRƯỚC. Thêm --yes để thực sự xoá.
"""
import os
import argparse
import psycopg2

DSN = os.environ.get("DATABASE_URL") or \
    "postgresql://questions:questions@172.16.10.71:5433/questions"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", type=int, help="cau_hoi_id")
    g.add_argument("--url", help="url chính xác")
    g.add_argument("--hash", help="content_hash chính xác")
    g.add_argument("--tieu-de", dest="tieu_de", help="tìm theo tiêu đề (ILIKE, gần đúng)")
    ap.add_argument("--yes", action="store_true", help="xác nhận xoá thật")
    a = ap.parse_args()

    if a.id is not None:
        where, params = "cau_hoi_id = %s", [a.id]
    elif a.url:
        where, params = "url = %s", [a.url]
    elif a.hash:
        where, params = "content_hash = %s", [a.hash]
    else:
        where, params = "tieu_de ILIKE %s", ["%" + a.tieu_de + "%"]

    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    # Xem trước
    cur.execute(
        "SELECT cau_hoi_id, ngay_dang, left(tieu_de, 90), url "
        "FROM cau_hoi WHERE " + where + " ORDER BY cau_hoi_id", params)
    rows = cur.fetchall()
    if not rows:
        print("Không khớp câu nào.")
        return
    print(f"Khớp {len(rows)} câu:")
    for cid, ngay, td, url in rows:
        print(f"  #{cid} | {ngay} | {td} | {url}")

    if not a.yes:
        print("\n(Đây mới chỉ là XEM TRƯỚC. Thêm --yes để xoá thật.)")
        return

    cur.execute("DELETE FROM cau_hoi WHERE " + where, params)
    conn.commit()
    print(f"\nĐã xoá {cur.rowcount} câu (trích dẫn/liên kết văn bản đã cascade theo).")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
