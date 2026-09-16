# -*- coding: utf-8 -*-
"""
Bổ sung 2 trường trích dẫn cấu trúc (van_ban_dan_chieu, trich_dan) cho các dataset
CŨ chỉ có text đáp án (vd data/cau_hoi_con_hieu_luc_FINAL.json từ luatvietnam.vn /
hethongphapluat.com). Tái dùng bộ tách trích dẫn trong collect_chinhsachonline.py.

Dùng:
  python them_trich_dan.py data/cau_hoi_con_hieu_luc_FINAL.json           # ghi đè
  python them_trich_dan.py in.json --out out.json
  python them_trich_dan.py in.json --force     # bóc lại kể cả đã có
"""
import argparse, json, os, sys
from collect_chinhsachonline import extract_citations

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true", help="Bóc lại kể cả khi đã có trích dẫn")
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8") as f:
        data = json.load(f)

    done = 0
    for r in data:
        if not args.force and r.get("van_ban_dan_chieu") is not None and r.get("trich_dan") is not None:
            continue
        docs, cites = extract_citations(None, r.get("dap_an", ""))
        r["van_ban_dan_chieu"] = docs
        r["trich_dan"] = cites
        done += 1

    out = args.out or args.inp
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out)

    nvb = sum(len(r.get("van_ban_dan_chieu", [])) for r in data)
    ntd = sum(len(r.get("trich_dan", [])) for r in data)
    print(f"✓ Bóc trích dẫn cho {done}/{len(data)} câu -> {out}")
    print(f"  Tổng: {nvb} liên kết văn bản, {ntd} trích dẫn điều/khoản")


if __name__ == "__main__":
    main()
