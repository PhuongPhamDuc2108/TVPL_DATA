# -*- coding: utf-8 -*-
"""
Làm sạch TÊN văn bản trong các file dataset JSON (van_ban_dan_chieu + trich_dan):
cắt phần thừa bằng clean_name, GIỮ link/điều/khoản/điểm, gộp trùng trong từng câu.

Dùng:
  python don_ten_json.py plo_hoidap_dataset.json chinhsachonline_dataset.json data/cau_hoi_con_hieu_luc_FINAL.json
"""
import argparse, json, os, sys
from lam_sach_ten import clean_name, doc_key, so_hieu, ten_score

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


def clean_file(fp):
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    n_ten, n_merge = 0, 0
    for r in data:
        # --- van_ban_dan_chieu: làm sạch tên + gộp trùng, giữ link/so_hieu ---
        seen, new = {}, []
        for v in (r.get("van_ban_dan_chieu") or []):
            old = v.get("ten", "")
            v["ten"] = clean_name(old)
            if v["ten"] != old: n_ten += 1
            v["so_hieu"] = v.get("so_hieu") or so_hieu(v["ten"]) or None
            k = doc_key(v["ten"], v.get("so_hieu"))
            if k in seen:
                n_merge += 1
                e = seen[k]
                if not e.get("link") and v.get("link"): e["link"] = v["link"]
                if not e.get("so_hieu") and v.get("so_hieu"): e["so_hieu"] = v["so_hieu"]
                if ten_score(v["ten"]) > ten_score(e["ten"]): e["ten"] = v["ten"]  # giữ tên tốt hơn
            else:
                seen[k] = v; new.append(v)
        if "van_ban_dan_chieu" in r: r["van_ban_dan_chieu"] = new

        # --- trich_dan: làm sạch tên + gộp theo (văn bản[số hiệu], điều, khoản, điểm) ---
        seen2, new2 = {}, []
        for c in (r.get("trich_dan") or []):
            old = c.get("van_ban", "")
            c["van_ban"] = clean_name(old)
            if c["van_ban"] != old: n_ten += 1
            c["so_hieu"] = c.get("so_hieu") or so_hieu(c["van_ban"]) or None
            key = (doc_key(c["van_ban"], c.get("so_hieu")), c.get("dieu"), c.get("khoan"), c.get("diem"))
            if key in seen2:
                n_merge += 1
                e = seen2[key]
                if not e.get("link") and c.get("link"): e["link"] = c["link"]
                if ten_score(c["van_ban"]) > ten_score(e["van_ban"]):
                    e["van_ban"] = c["van_ban"]; e["so_hieu"] = c.get("so_hieu") or e.get("so_hieu")
            else:
                seen2[key] = c; new2.append(c)
        if "trich_dan" in r: r["trich_dan"] = new2

    tmp = fp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, fp)
    print(f"✓ {fp}: {len(data)} câu — làm sạch {n_ten} tên, gộp {n_merge} mục trùng")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    for fp in args.files:
        clean_file(fp)


if __name__ == "__main__":
    main()
