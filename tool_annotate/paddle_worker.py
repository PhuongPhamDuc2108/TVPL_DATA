# -*- coding: utf-8 -*-
"""
Worker chay trong ocr_env (PaddleOCR). Giao tiep voi server qua stdin/stdout
theo tung dong JSON de giu model nam san trong RAM.

  vao : {"img": "<duong dan anh>"}
  ra  : {"ok": true, "lines": [{"text": ..., "score": ..., "box": [x0,y0,x1,y1]}]}

Chay thu doc lap:  python paddle_worker.py <anh.png>
"""
import json
import os
import sys

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("FLAGS_call_stack_level", "0")

_ocr = None


def get_ocr(lang="vi"):
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    return _ocr


def read_image(path):
    """Doc anh chiu duoc duong dan tieng Viet tren Windows."""
    import numpy as np
    import cv2
    with open(path, "rb") as f:
        buf = np.frombuffer(f.read(), np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def recognize(path, lang="vi"):
    ocr = get_ocr(lang)
    img = read_image(path)
    if img is None:
        raise RuntimeError("khong doc duoc anh: %s" % path)
    res = ocr.predict(img)
    lines = []
    for page in res:
        d = page if isinstance(page, dict) else getattr(page, "json", {}).get("res", {})
        texts = d.get("rec_texts") or []
        scores = d.get("rec_scores") or []
        polys = d.get("rec_polys") or d.get("dt_polys") or []
        for i, t in enumerate(texts):
            poly = polys[i] if i < len(polys) else None
            box = None
            if poly is not None:
                xs = [float(p[0]) for p in poly]
                ys = [float(p[1]) for p in poly]
                box = [min(xs), min(ys), max(xs), max(ys)]
            lines.append({
                "text": t,
                "score": float(scores[i]) if i < len(scores) else None,
                "box": box,
            })
    return lines


def layout_text(lines, y_tol_ratio=0.6):
    """Ghep cac dong theo toa do -> van ban co thu tu doc dung."""
    items = [l for l in lines if l.get("box")]
    if not items:
        return "\n".join(l["text"] for l in lines)
    heights = sorted((l["box"][3] - l["box"][1]) for l in items)
    h = heights[len(heights) // 2] or 10
    items.sort(key=lambda l: (l["box"][1], l["box"][0]))
    rows, cur, cur_y = [], [], None
    for l in items:
        y = l["box"][1]
        if cur_y is None or abs(y - cur_y) <= h * y_tol_ratio:
            cur.append(l)
            cur_y = y if cur_y is None else (cur_y + y) / 2
        else:
            rows.append(cur)
            cur, cur_y = [l], y
    if cur:
        rows.append(cur)
    out = []
    prev_bottom = None
    for row in rows:
        row.sort(key=lambda l: l["box"][0])
        top = min(l["box"][1] for l in row)
        if prev_bottom is not None and top - prev_bottom > h * 0.9:
            out.append("")
        out.append(" ".join(l["text"] for l in row).strip())
        prev_bottom = max(l["box"][3] for l in row)
    return "\n".join(out).strip()


def main():
    if len(sys.argv) > 1:                       # che do chay thu
        lines = recognize(sys.argv[1])
        sys.stdout.reconfigure(encoding="utf-8")
        print(layout_text(lines))
        return

    sys.stdout.reconfigure(encoding="utf-8")
    get_ocr()                                   # nap model truoc
    print(json.dumps({"ready": True}), flush=True)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
            lines = recognize(req["img"], req.get("lang", "vi"))
            print(json.dumps({"ok": True, "text": layout_text(lines),
                              "lines": lines}, ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
