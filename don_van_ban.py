# -*- coding: utf-8 -*-
"""
Dọn tên văn bản bị "bắt lố" trong bảng van_ban:
  - Cắt phần thừa (mệnh đề dính sau tên: "(...)", ", đã được sửa đổi...", " với...",
    " tại Nghị định...", " và Thông tư..."), giữ đúng phần TÊN văn bản.
  - Gộp các bản trùng sau khi cắt (vd nhiều biến thể "Luật BHYT ..." -> "Luật BHYT"),
    trỏ lại trich_dan + cau_hoi_van_ban về bản canonical, xóa bản dư.

Chạy:
  python don_van_ban.py            # DRY-RUN: chỉ phân tích, in thống kê + ví dụ
  python don_van_ban.py --apply    # thực thi (trong 1 transaction)

DB: biến môi trường DATABASE_URL, mặc định như dưới.
"""
import os, re, sys, argparse, unicodedata
import psycopg2

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

DSN = os.environ.get("DATABASE_URL") or "postgresql://questions:questions@172.16.10.71:5433/questions"
_LOAI = ["Bộ luật", "Luật", "Thông tư liên tịch", "Thông tư", "Nghị định",
         "Nghị quyết", "Quyết định", "Pháp lệnh", "Văn bản hợp nhất", "Hiến pháp"]


def strip_dia(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def doc_loai(ten):
    t = (ten or "").strip()
    for k in _LOAI:
        if t.startswith(k): return k
    if "Hiến pháp" in t: return "Hiến pháp"
    return None


# Loại văn bản (để nhận "và/tại <văn bản khác>")
_VBT = r"(?:Bộ luật|Luật|Nghị định|Thông tư(?:\s+liên tịch)?|Nghị quyết|Quyết định|Pháp lệnh|Hiến pháp|Văn bản hợp nhất)"


# Từ mở đầu MỆNH ĐỀ nối (không nằm trong tên luật) -> cắt tại đây.
_CLAUSE = (r"(?:đã|đang|được|hiện|nếu|khi|người|việc|những|các|trong|mà|do|để|thì|cụ thể|"
           r"theo|tại|quy định|nay|sau đây|sau đó|gồm|bao gồm|trừ|từ|thực hiện|thuộc|khám|"
           r"thẻ|có|không|nhằm|vẫn|chỉ|phải|sẽ|nêu|dùng để|áp dụng|giấy tờ|thời điểm|"
           r"trường hợp|mua|bán|quá trình|đối với|ngoài ra|đồng thời|thể hiện|nhưng|"
           r"đảm bảo|bảo đảm|kể từ|hành vi)")


def clean_name(ten):
    """Cắt tên văn bản về phần lõi (giữ năm/số hiệu)."""
    s = (ten or "").strip()
    s = re.sub(r"\s*\([^)]*\)", "", s)                               # bỏ (…) đóng ngoặc, GIỮ phần sau (vd năm)
    s = re.sub(r"\s*\([^)]*$", "", s, flags=re.S)                    # bỏ "(…" không đóng ngoặc tới hết
    # dính 2 văn bản: "... và/hoặc/cùng/, <loại văn bản> ..."
    s = re.split(r"\s+(?:và|hoặc|cùng)\s+" + _VBT + r"\b", s)[0]
    s = re.split(r"\s*,\s*" + _VBT + r"\b", s)[0]
    # "và/hoặc + mệnh đề" (vd "và thuộc trường hợp") — nhưng giữ "và <danh từ ghép tên>"
    s = re.split(r"\s+(?:và|hoặc)\s+" + _CLAUSE + r"\b", s)[0]
    # mệnh đề nối SAU DẤU PHẨY
    s = re.split(r"\s*,\s*" + _CLAUSE + r"\b", s)[0]
    # mệnh đề nối KHÔNG cần phẩy (các từ gần như không có trong tên luật)
    s = re.split(r"\s+(?:với|nếu|thì|nhằm|đã được|quy định tại|trong quá trình|sau đó|không có|"
                 r"có hiệu lực|nhưng|đối với|và thời điểm|ngoài ra|đồng thời|kể từ)\b", s)[0]
    # "tại/theo + tham chiếu pháp lý"
    s = re.split(r"\s+(?:tại|theo)\s+(?:Điều|khoản|điểm|Chương|Mục|Phụ lục|" + _VBT + r")\b", s)[0]
    # dọn đuôi: bỏ dấu/ngoặc/nháy thừa + lặp bỏ TỪ LẺ vô nghĩa ở cuối
    s = re.sub(r"[\s,;:.\-–\"'’)(]+$", "", s).strip()
    while True:
        s2 = re.sub(r"\s+(?:và|của|hoặc|cùng|tại|theo|thì|là|do|khi|mà|đã|đang|được|có|không|"
                    r"sau|đó|nếu|các|những|người|việc|với|thuộc|nay|vẫn|chỉ|phải|sẽ|quy|định|"
                    r"hiện|hành|nêu|gồm|từ)$", "", s).strip()
        s2 = re.sub(r"[\s,;:.\-–\"'’)(]+$", "", s2).strip()
        if s2 == s:
            break
        s = s2
    return s or (ten or "").strip()


def new_key(so_hieu, clean_ten):
    if so_hieu and so_hieu.strip():
        return "sh:" + re.sub(r"\s+", "", so_hieu.lower())
    return "tn:" + re.sub(r"\s+", " ", strip_dia((clean_ten or "").lower())).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Thực thi (mặc định chỉ dry-run)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN, connect_timeout=8)
    cur = conn.cursor()
    cur.execute("SELECT van_ban_id, khoa, so_hieu, ten, loai, link FROM van_ban")
    rows = cur.fetchall()

    groups = {}
    for vid, khoa, sh, ten, loai, link in rows:
        ct = clean_name(ten)
        groups.setdefault(new_key(sh, ct), []).append(
            {"id": vid, "sh": sh, "ten": ten, "clean": ct, "loai": loai, "link": link})

    updates, remap, deletes = [], {}, []
    trimmed_examples, merge_examples = [], []
    n_trim = 0
    for k, g in groups.items():
        g.sort(key=lambda r: r["id"])
        canon = g[0]
        cname = min((r["clean"] for r in g if r["clean"]), key=len, default=canon["ten"]) or canon["ten"]
        sh = next((r["sh"] for r in g if r["sh"]), None)
        link = next((r["link"] for r in g if r["link"]), None)
        loai = doc_loai(cname) or canon["loai"]
        updates.append((canon["id"], cname, k, sh, link, loai))
        for r in g:
            if r["clean"] != r["ten"]:
                n_trim += 1
                if len(trimmed_examples) < 8 and len(r["ten"]) - len(r["clean"]) > 5:
                    trimmed_examples.append((r["ten"], cname))
        for r in g[1:]:
            remap[r["id"]] = canon["id"]; deletes.append(r["id"])
        if len(g) > 1 and len(merge_examples) < 8:
            merge_examples.append((cname, len(g), [r["ten"][:45] for r in g[:3]]))

    print("=== PHÂN TÍCH ===")
    print(f"  van_ban hiện tại : {len(rows)}")
    print(f"  tên bị cắt bớt   : {n_trim}")
    print(f"  nhóm bị gộp      : {sum(1 for g in groups.values() if len(g) > 1)}  (xóa {len(deletes)} bản dư)")
    print(f"  van_ban sau dọn  : {len(groups)}")
    print("\n--- ví dụ CẮT ---")
    for a, b in trimmed_examples:
        print(f"    '{a[:70]}'\n      -> '{b}'")
    print("\n--- ví dụ GỘP ---")
    for name, n, sample in merge_examples:
        print(f"    [{n} bản] -> '{name}'  (vd: {sample})")

    if not args.apply:
        print("\n→ DRY-RUN. Thêm --apply để thực thi.")
        cur.close(); conn.close(); return

    try:
        for dup, canon in remap.items():
            cur.execute("""DELETE FROM cau_hoi_van_ban a WHERE a.van_ban_id=%s
                           AND EXISTS(SELECT 1 FROM cau_hoi_van_ban b
                                      WHERE b.cau_hoi_id=a.cau_hoi_id AND b.van_ban_id=%s)""", (dup, canon))
            cur.execute("UPDATE cau_hoi_van_ban SET van_ban_id=%s WHERE van_ban_id=%s", (canon, dup))
            cur.execute("UPDATE trich_dan SET van_ban_id=%s WHERE van_ban_id=%s", (canon, dup))
        if deletes:
            cur.execute("DELETE FROM van_ban WHERE van_ban_id = ANY(%s)", (deletes,))
        for vid, cname, k, sh, link, loai in updates:
            cur.execute("UPDATE van_ban SET ten=%s, khoa=%s, so_hieu=%s, link=%s, loai=%s WHERE van_ban_id=%s",
                        (cname, k, sh, link, loai, vid))
        conn.commit()
        cur.execute("SELECT count(*) FROM van_ban")
        print(f"\n✓ ĐÃ DỌN. van_ban còn {cur.fetchone()[0]} dòng.")
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
