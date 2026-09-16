# -*- coding: utf-8 -*-
"""
Worker VietOCR chay trong ocr_env. Nhan tung dong JSON qua stdin,
moi request la mot thu muc chua cac anh dong chu da cat san.

  vao : {"dir": "<thu muc>", "files": ["l000.png", ...]}
  ra  : {"ok": true, "texts": [...]}

Chay thu:  python vietocr_worker.py <thu_muc_crop>
"""
import json
import os
import sys

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
_pred = None


def get_predictor():
    global _pred
    if _pred is None:
        import yaml
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor
        cfg_path = os.path.join(MODEL_DIR, "vgg_transformer.yml")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = Cfg(yaml.safe_load(f))
        cfg["weights"] = os.path.join(MODEL_DIR, "vgg-transformer.pth")
        cfg["device"] = "cpu"
        cfg["cnn"]["pretrained"] = False
        cfg["predictor"]["beamsearch"] = False
        _pred = Predictor(cfg)
    return _pred


def recognize_dir(d, files):
    from PIL import Image
    p = get_predictor()
    imgs = [Image.open(os.path.join(d, fn)).convert("RGB") for fn in files]
    if not imgs:
        return []
    try:                                    # batch cho nhanh
        return p.predict_batch(imgs)
    except Exception:
        return [p.predict(im) for im in imgs]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1:
        d = sys.argv[1]
        files = sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))
        for t in recognize_dir(d, files):
            print(t)
        return

    get_predictor()
    print(json.dumps({"ready": True}), flush=True)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
            texts = recognize_dir(req["dir"], req["files"])
            print(json.dumps({"ok": True, "texts": texts}, ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
