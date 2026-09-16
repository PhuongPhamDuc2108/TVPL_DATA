# -*- coding: utf-8 -*-
"""
Pipeline OCR tieng Viet cho ho so scan.

Cac buoc:
  1. Lay ANH GOC nhung trong PDF (khong render lai o dpi tuy y -> tranh
     phong to bang noi suy lam nhoe net chu).
  2. Xoa muc do (con dau, dau "DEN") nhung van giu chu den mo.
  3. Do chieu cao chu that roi scale ve tam ngam cua Tesseract (~32 px).
  4. Tesseract vie / LSTM, xuat dong thoi text va lop text-only PDF.
  5. Loc bo cac dong rac.
  6. Dan lop text len ban PDF goc -> PDF boi den copy duoc.
"""
import os
import re
import subprocess
import tempfile

import cv2
import fitz
import numpy as np

TARGET_TEXT_H = 32.0        # chieu cao chu muc tieu (px)
RED_THRESHOLD = 38          # nguong nhan dien muc do
FALLBACK_DPI = 300          # dung khi trang khong co anh nhung


# ---------------------------------------------------------------- lay anh
def native_rgb(doc, pageno, dpi=FALLBACK_DPI):
    """Tra ve (anh RGB, co_phai_anh_goc). `dpi` chi dung khi phai render lai."""
    page = doc[pageno]
    imgs = page.get_images(full=True)
    if len(imgs) == 1:
        try:
            info = doc.extract_image(imgs[0][0])
            img = cv2.imdecode(np.frombuffer(info["image"], np.uint8), cv2.IMREAD_COLOR)
            if img is not None and img.size:
                if img.ndim == 2:
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                return cv2.cvtColor(img, cv2.COLOR_BGR2RGB), True
        except Exception:
            pass
    pm = page.get_pixmap(dpi=dpi)
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)
    return a[:, :, :3].copy(), False


# ------------------------------------------------------------ xoa muc do
def strip_red(rgb, thr=RED_THRESHOLD):
    """Xoa con dau do; giu nguyen chu den ke ca khi mo."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)
    mask = ((r - np.maximum(g, b)) > thr).astype(np.uint8)
    n = int(mask.sum())
    if n < 200:
        return gray, 0
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=2)
    out = gray.copy()
    out[mask > 0] = int(np.percentile(gray, 88))
    return out, n


# --------------------------------------------------- chuan hoa kich thuoc
def text_height(gray):
    """Uoc luong chieu cao chu bang cac thanh phan lien thong giong chu."""
    s = 1.0
    small = gray
    if gray.shape[0] > 2000:
        s = 2000.0 / gray.shape[0]
        small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    bw = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 31, 15)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    hs = [stats[i][3] for i in range(1, n)
          if 6 <= stats[i][3] <= 60 and 2 <= stats[i][2] <= 60
          and stats[i][4] >= 12 and stats[i][3] >= stats[i][2] * 0.4]
    if len(hs) < 50:
        return None
    return float(np.median(hs)) / s


def scale_for_ocr(gray, target=TARGET_TEXT_H):
    th = text_height(gray)
    if not th:
        return gray, None, 1.0
    f = max(0.6, min(4.5, target / th))
    if abs(f - 1.0) < 0.1:
        return gray, round(th, 1), 1.0
    interp = cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA
    return cv2.resize(gray, None, fx=f, fy=f, interpolation=interp), round(th, 1), round(f, 2)


# ------------------------------------------------------------- loc van ban
def clean_text(text):
    """Bo cac dong chi toan ky tu rac (thuong sinh ra tu con dau, vet ban)."""
    keep = []
    for ln in text.splitlines():
        s = ln.rstrip()
        if not s.strip():
            keep.append("")
            continue
        core = s.strip()
        good = len(re.findall(r"[0-9A-Za-zÀ-ỹà-ỹ]", core))
        if good / max(1, len(core)) < 0.55:
            continue
        if not re.search(r"[A-Za-zÀ-ỹà-ỹ]{2,}", core) and not re.search(r"\d", core):
            continue
        keep.append(s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


# ----------------------------------------------------------------- tesseract
def run_tesseract(tess_exe, tessdata, img_path, out_base, lang="vie", psm=3, dpi=300):
    """Chay 1 lan, xuat ca .txt lan .pdf (lop text trong suot)."""
    env = dict(os.environ)
    env["TESSDATA_PREFIX"] = tessdata
    cmd = [tess_exe, img_path, out_base, "-l", lang, "--oem", "1",
           "--psm", str(psm), "--dpi", str(dpi), "-c", "textonly_pdf=1",
           "txt", "pdf"]
    p = subprocess.run(cmd, capture_output=True, env=env,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:500])
    txt_path, pdf_path = out_base + ".txt", out_base + ".pdf"
    text = ""
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    return text, (pdf_path if os.path.exists(pdf_path) else None)


# --------------------------------------------------------------- toan bo file
def process_pdf(pdf_path, tess_exe, tessdata, lang="vie",
                searchable_out=None, progress=None, dpi=FALLBACK_DPI):
    """
    OCR toan bo mot PDF.
    Tra ve (danh sach trang, thong tin chan doan).
    Neu searchable_out duoc dat -> ghi ban PDF co lop text copy duoc.
    `dpi` chi anh huong cac trang PHAI render lai (trang khong co anh nhung);
    trang co anh goc luon dung dung do phan giai that cua anh.
    """
    tmpdir = tempfile.mkdtemp(prefix="ocr_")
    pages, diag = [], []
    layers = []
    try:
        src = fitz.open(pdf_path)
        total = len(src)
        for i in range(total):
            rgb, is_native = native_rgb(src, i, dpi=dpi)
            gray, red_px = strip_red(rgb)
            img, th, f = scale_for_ocr(gray)

            img_path = os.path.join(tmpdir, "p%03d.png" % i)
            cv2.imwrite(img_path, img)
            base = os.path.join(tmpdir, "o%03d" % i)
            raw, layer_pdf = run_tesseract(tess_exe, tessdata, img_path, base,
                                           lang=lang, dpi=dpi)
            os.remove(img_path)

            pages.append({"page": i + 1, "text": clean_text(raw), "text_raw": raw.strip()})
            diag.append({"page": i + 1, "native": is_native,
                         "px": "%dx%d" % (rgb.shape[1], rgb.shape[0]),
                         "text_h": th, "scale": f, "red_px": red_px})
            layers.append(layer_pdf)
            if progress:
                progress(i + 1, total)

        if searchable_out:
            out = fitz.open()
            out.insert_pdf(src)
            for i, layer_pdf in enumerate(layers):
                if not layer_pdf:
                    continue
                page = out[i]
                # bo lop text cu bi loi font (neu co) truoc khi dan lop moi
                if page.get_text().strip():
                    try:
                        page.add_redact_annot(page.rect)
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
                    except Exception:
                        pass
                with fitz.open(layer_pdf) as ld:
                    page.show_pdf_page(page.rect, ld, 0, overlay=True)
            os.makedirs(os.path.dirname(searchable_out), exist_ok=True)
            tmp_out = searchable_out + ".tmp"
            out.save(tmp_out, garbage=3, deflate=True)
            out.close()
            os.replace(tmp_out, searchable_out)
        src.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    return pages, diag

# ------------------------------------------------- tach dong bang Tesseract
def tesseract_lines(tess_exe, tessdata, img_path, lang="vie", psm=3, min_conf=-5):
    """Tra ve danh sach hop bao dong chu [(x0,y0,x1,y1), ...] theo thu tu doc."""
    env = dict(os.environ)
    env["TESSDATA_PREFIX"] = tessdata
    p = subprocess.run(
        [tess_exe, img_path, "stdout", "-l", lang, "--oem", "1",
         "--psm", str(psm), "tsv"],
        capture_output=True, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:400])
    out = []
    for row in p.stdout.decode("utf-8", "replace").splitlines()[1:]:
        c = row.split("	")
        if len(c) < 12 or c[0] != "5":          # 5 = word
            continue
        try:
            conf = float(c[10])
        except ValueError:
            continue
        if conf < min_conf or not c[11].strip():
            continue
        key = (int(c[2]), int(c[3]), int(c[4]))  # block, par, line
        x, y, w, h = int(c[6]), int(c[7]), int(c[8]), int(c[9])
        if key in [k for k, _ in out]:
            i = [k for k, _ in out].index(key)
            b = out[i][1]
            out[i] = (key, [min(b[0], x), min(b[1], y),
                            max(b[2], x + w), max(b[3], y + h)])
        else:
            out.append((key, [x, y, x + w, y + h]))
    return [b for _, b in out]


def crop_lines(gray, boxes, out_dir, pad=4, min_h=8):
    """Cat tung dong ra file PNG de dua sang bo nhan dang khac."""
    os.makedirs(out_dir, exist_ok=True)
    H, W = gray.shape[:2]
    files, kept = [], []
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
        x1 = min(W, x1 + pad); y1 = min(H, y1 + pad)
        if y1 - y0 < min_h or x1 - x0 < min_h:
            continue
        fn = "l%04d.png" % i
        cv2.imwrite(os.path.join(out_dir, fn), gray[y0:y1, x0:x1])
        files.append(fn)
        kept.append([x0, y0, x1, y1])
    return files, kept


def lines_to_text(boxes, texts, gap_ratio=0.9):
    """Ghep cac dong da nhan dang thanh van ban, chen dong trong giua cac doan."""
    if not boxes:
        return ""
    hs = sorted(b[3] - b[1] for b in boxes)
    h = hs[len(hs) // 2] or 10
    out, prev_bottom = [], None
    for b, t in zip(boxes, texts):
        if prev_bottom is not None and b[1] - prev_bottom > h * gap_ratio:
            out.append("")
        out.append(t.strip())
        prev_bottom = b[3]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


# ------------------------------------------------- luot doc lai bang VietOCR
def vietocr_pass(pdf_path, tess_exe, tessdata, recognize, lang="vie", progress=None):
    """
    Doc lai toan bo PDF bang bo nhan dang thu hai (VietOCR).
    `recognize(dir, files) -> [text, ...]` do ben goi cung cap.
    Tra ve danh sach {"page": n, "text_vietocr": ...}.
    """
    tmpdir = tempfile.mkdtemp(prefix="vocr_")
    out = []
    try:
        src = fitz.open(pdf_path)
        total = len(src)
        for i in range(total):
            rgb, _ = native_rgb(src, i)
            gray, _ = strip_red(rgb)
            img, _, _ = scale_for_ocr(gray)

            ip = os.path.join(tmpdir, "p%03d.png" % i)
            cv2.imwrite(ip, img)
            boxes = tesseract_lines(tess_exe, tessdata, ip, lang=lang)
            ldir = os.path.join(tmpdir, "l%03d" % i)
            files, kept = crop_lines(img, boxes, ldir)
            texts = recognize(ldir, files) if files else []
            out.append({"page": i + 1,
                        "text_vietocr": lines_to_text(kept, texts),
                        "so_dong": len(files)})
            import shutil as _sh
            _sh.rmtree(ldir, ignore_errors=True)
            os.remove(ip)
            if progress:
                progress(i + 1, total)
        src.close()
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    return out
