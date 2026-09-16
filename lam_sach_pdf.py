# -*- coding: utf-8 -*-
"""
Lam sach PDF tai tu Studocu: (1) xoa trang bia Studocu, (2) xoa watermark
"Dit document is beschikbaar op studeersnel" (anh o day trang) + dong "messages.downloaded_by".
Giu nguyen noi dung don. Ban goc giu nguyen; ban sach ghi sang data_kn_clean/.
Yeu cau: PyMuPDF (fitz).
"""
import os
import glob
import fitz

SRC_DIR = r"D:\TVPL_data\data_khieunai\data_kn"
OUT_DIR = r"D:\TVPL_data\data_khieunai\data_kn_clean"

# dau hieu trang bia Studocu (chi xoa trang 0 khi co) - bat ca 2 bien the
COVER_MARK = ["pdf_cover_qr_code", "not sponsored or endorsed", "not_sponsored_or_endorsed",
              "studocu_not_sponsored", "scan to open", "studocu is not", "studeersnel"]
# tu khoa watermark can redact (text) - ca "downloaded by" (dau cach) lan "downloaded_by"
WM_TEXT = ["messages.", "studeersnel", "studocu", "beschikbaar", "dit document",
           "sponsored", "downloaded by", "downloaded_by", "scan to open"]


def page_text(p):
    return p.get_text().lower()


def clean(path, out):
    doc = fitz.open(path)
    orig = doc.page_count
    removed_cover = False
    # 1) xoa trang bia neu dung la bia Studocu
    if doc.page_count > 1:
        t0 = page_text(doc[0])
        if any(m in t0 for m in COVER_MARK):
            doc.delete_page(0)
            removed_cover = True
    img_rm = txt_rm = 0
    for p in doc:
        H = p.rect.height
        # 2) xoa anh watermark o day trang (footer band, y0 >= 70% chieu cao)
        for img in p.get_images(full=True):
            xref = img[0]
            rects = p.get_image_rects(xref)
            if rects and any(r.y0 >= 0.75 * H for r in rects):
                try:
                    p.delete_image(xref); img_rm += 1
                except Exception:
                    pass
        # 3) redact text watermark
        for b in p.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    t = s["text"].strip().lower()
                    if t and any(k in t for k in WM_TEXT):
                        p.add_redact_annot(fitz.Rect(s["bbox"])); txt_rm += 1
        p.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    doc.save(out, garbage=4, deflate=True)
    n = doc.page_count
    doc.close()
    return orig, n, removed_cover, img_rm, txt_rm


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC_DIR, "*.pdf")))
    if not files:
        print("Khong thay PDF trong", SRC_DIR); return
    for f in files:
        name = os.path.basename(f)
        out = os.path.join(OUT_DIR, name)
        try:
            orig, n, cov, ir, tr = clean(f, out)
            print(f"OK  {name[:52]:<52} {orig}->{n}tr  bia={'x' if cov else '-'}  anh_wm={ir}  text_wm={tr}")
        except Exception as e:
            print(f"FAIL {name}  ({e})")
    print(f"\n==> Ban sach o: {OUT_DIR}")


if __name__ == "__main__":
    main()
