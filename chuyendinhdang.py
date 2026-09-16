# -*- coding: utf-8 -*-
"""
Chuyen 19 PDF that (da tai bang taidonkhieunai.py) sang cac dinh dang khac de test boc tach:
  - ANH  : render tung trang PDF -> PNG (hoac JPG)  => file anh that, test OCR / vision
  - DOCX : bocx text tung file -> .docx             => dinh dang Word co noi dung that

Yeu cau (da co san trong env): PyMuPDF (fitz), python-docx.
Chay taidonkhieunai.py TRUOC de co PDF trong data_khieunai/.
"""
import os
import glob
import fitz  # PyMuPDF
from docx import Document

SRC_DIR = r"D:\TVPL_data\data_khieunai"
IMG_DIR = os.path.join(SRC_DIR, "anh")
DOCX_DIR = os.path.join(SRC_DIR, "docx")

DPI = 150          # do phan giai anh (200-300 neu muon net hon)
IMG_FMT = "png"    # "png" hoac "jpg"
MAKE_IMAGES = True
MAKE_DOCX = True


def pdf_to_images(pdf_path, stem):
    doc = fitz.open(pdf_path)
    n = 0
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(dpi=DPI)
        out = os.path.join(IMG_DIR, f"{stem}_p{i:02d}.{IMG_FMT}")
        if IMG_FMT == "jpg":
            pix.save(out, jpg_quality=85)
        else:
            pix.save(out)
        n += 1
    doc.close()
    return n


def pdf_to_docx(pdf_path, stem):
    doc = fitz.open(pdf_path)
    d = Document()
    for page in doc:
        text = page.get_text().strip()
        if text:
            for line in text.splitlines():
                d.add_paragraph(line)
        d.add_page_break()
    doc.close()
    out = os.path.join(DOCX_DIR, f"{stem}.docx")
    d.save(out)
    return out


def main():
    pdfs = sorted(glob.glob(os.path.join(SRC_DIR, "*.pdf")))
    if not pdfs:
        print(f"Khong thay PDF trong {SRC_DIR}. Chay 'python taidonkhieunai.py' truoc.")
        return
    if MAKE_IMAGES:
        os.makedirs(IMG_DIR, exist_ok=True)
    if MAKE_DOCX:
        os.makedirs(DOCX_DIR, exist_ok=True)

    total_img = 0
    for p in pdfs:
        stem = os.path.splitext(os.path.basename(p))[0]
        try:
            if MAKE_IMAGES:
                total_img += pdf_to_images(p, stem)
            if MAKE_DOCX:
                pdf_to_docx(p, stem)
            print(f"OK   {stem}")
        except Exception as e:
            print(f"FAIL {stem}  ({e})")

    print(f"\n==> Xong {len(pdfs)} PDF.")
    if MAKE_IMAGES:
        print(f"    Anh ({IMG_FMT}, {DPI}dpi): {total_img} file -> {IMG_DIR}")
    if MAKE_DOCX:
        print(f"    Docx: {len(pdfs)} file -> {DOCX_DIR}")


if __name__ == "__main__":
    main()
