# -*- coding: utf-8 -*-
"""Tiện ích dùng chung cho việc trích các DANH MỤC trong văn bản pháp luật.

Nguồn dùng ở đây là Công báo Chính phủ (congbao.chinhphu.vn) vì đây là bản
CHÍNH THỨC, tải được file .doc/.docx (thuvienphapluat.vn chặn crawl 403 và
giấu nội dung sau đăng nhập).

Luồng chuẩn:  trang Công báo  ->  tải .docx/.doc  ->  (Word COM: .doc -> .docx)
              ->  python-docx đọc bảng  ->  pandas  ->  Excel.
"""
from __future__ import annotations

import html
import os
import re
import urllib.parse

import sys

import requests
from docx.oxml.ns import qn

# Tiếng Việt in ra được ở cả PowerShell lẫn bash (bash mặc định cp1252 -> vỡ).
for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# CDN của Chính phủ (g7.cdnchinhphu.vn) không gửi kèm chứng chỉ trung gian nên
# bộ CA của certifi không dựng được chuỗi -> dùng kho chứng chỉ của Windows,
# vốn tự tải chứng chỉ trung gian theo AIA. Tuyệt đối không tắt verify.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - chỉ cảnh báo, vẫn chạy được nếu certifi đủ
    print('[danh_muc] thiếu truststore -> pip install truststore nếu gặp lỗi SSL')
from docx.table import Table
from docx.text.paragraph import Paragraph

CDN_CHINHPHU = 'https://g7.cdnchinhphu.vn/api/'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'}

THU_MUC_TAI = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'vanban_goc')


# ----------------------------------------------------------------- tải file

def _ten_file_an_toan(ten: str) -> str:
    ten = urllib.parse.unquote_plus(ten)
    return re.sub(r'[\\/:*?"<>|]+', '_', ten).strip() or 'vanban'


def tim_file_dinh_kem(url_trang: str) -> list[tuple[str, str]]:
    """Trả về [(url_tai, ten_file)] của các file đính kèm trên 1 trang Công báo."""
    r = requests.get(url_trang, headers=UA, timeout=90)
    r.raise_for_status()
    ket_qua, da_co = [], set()
    for m in re.finditer(r'download/stream\?[^"\'<>\s]+', r.text):
        duong_dan = html.unescape(m.group(0))
        url = CDN_CHINHPHU + duong_dan
        if url in da_co:
            continue
        da_co.add(url)
        ten = re.search(r'file_name=([^&]+)', duong_dan)
        ket_qua.append((url, _ten_file_an_toan(ten.group(1) if ten else 'vanban')))
    return ket_qua


def tai_van_ban(url_trang: str, ten_luu: str, uu_tien=('docx', 'doc'),
                thu_muc: str | None = None, tai_lai: bool = False) -> str:
    """Tải file đính kèm (ưu tiên .docx rồi .doc) của một trang Công báo về đĩa."""
    thu_muc = thu_muc or THU_MUC_TAI
    os.makedirs(thu_muc, exist_ok=True)

    dinh_kem = tim_file_dinh_kem(url_trang)
    if not dinh_kem:
        raise RuntimeError(f'Không tìm thấy file đính kèm trên {url_trang}')

    for duoi in uu_tien:
        for url, ten in dinh_kem:
            if not ten.lower().endswith('.' + duoi):
                continue
            dich = os.path.join(thu_muc, f'{ten_luu}.{duoi}')
            if os.path.exists(dich) and not tai_lai:
                print(f'  đã có sẵn: {dich}')
                return dich
            print(f'  tải {ten} -> {dich}')
            r = requests.get(url, headers=UA, timeout=300)
            r.raise_for_status()
            with open(dich, 'wb') as f:
                f.write(r.content)
            return dich
    raise RuntimeError(f'Trang {url_trang} không có file thuộc {uu_tien}: '
                       f'{[t for _, t in dinh_kem]}')


def tai_tat_ca_van_ban(url_trang: str, ten_luu: str, duoi: str = 'doc',
                       thu_muc: str | None = None, tai_lai: bool = False) -> list[str]:
    """Tải MỌI file cùng phần mở rộng trên một trang Công báo.

    Cần cho các văn bản dài bị Công báo cắt làm nhiều số (ví dụ TT 11/2020 nằm ở
    Công báo 301+302 và 303+304).
    """
    thu_muc = thu_muc or THU_MUC_TAI
    os.makedirs(thu_muc, exist_ok=True)
    ket_qua = []
    for i, (url, ten) in enumerate([x for x in tim_file_dinh_kem(url_trang)
                                    if x[1].lower().endswith('.' + duoi)], start=1):
        dich = os.path.join(thu_muc, f'{ten_luu}_p{i}.{duoi}')
        if os.path.exists(dich) and not tai_lai:
            print(f'  đã có sẵn: {dich}')
        else:
            print(f'  tải {ten} -> {dich}')
            r = requests.get(url, headers=UA, timeout=300)
            r.raise_for_status()
            with open(dich, 'wb') as f:
                f.write(r.content)
        ket_qua.append(dich)
    if not ket_qua:
        raise RuntimeError(f'Trang {url_trang} không có file .{duoi}')
    return ket_qua


def chuyen_sang_docx(duong_dan: str) -> str:
    """.doc (OLE, Công báo cũ) -> .docx bằng Microsoft Word COM. .docx thì giữ nguyên."""
    if duong_dan.lower().endswith('.docx'):
        return duong_dan
    dich = os.path.splitext(duong_dan)[0] + '.docx'
    if os.path.exists(dich):
        return dich

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(os.path.abspath(duong_dan), False, True)
        doc.SaveAs2(os.path.abspath(dich), 16)  # 16 = wdFormatXMLDocument
        doc.Close(False)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()
    print(f'  chuyển {os.path.basename(duong_dan)} -> {os.path.basename(dich)}')
    return dich


# ------------------------------------------------------------- đọc nội dung

def duyet_khoi(doc):
    """Duyệt đoạn văn và bảng THEO ĐÚNG THỨ TỰ xuất hiện trong tài liệu.

    python-docx không có sẵn hàm này: doc.paragraphs và doc.tables là hai danh
    sách rời, mất thứ tự tương đối - trong khi tiêu đề lĩnh vực/phụ lục nằm ở
    đoạn văn ngay trước bảng của nó.
    """
    for con in doc.element.body.iterchildren():
        if con.tag == qn('w:p'):
            yield Paragraph(con, doc)
        elif con.tag == qn('w:tbl'):
            yield Table(con, doc)


def chuan_hoa(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').replace('\n', ' ')).strip()


def o_hang(hang) -> list[str]:
    """Text từng ô của một hàng (ô gộp sẽ lặp lại text ở mọi cột nó phủ)."""
    return [chuan_hoa(o.text) for o in hang.cells]


def gom_trung_lien_tiep(gia_tri: list[str]) -> list[str]:
    out: list[str] = []
    for v in gia_tri:
        if not out or out[-1] != v:
            out.append(v)
    return out


# ------------------------------------------------- đọc danh mục từ trang web

# Có những danh mục KHÔNG tải được file gốc: Công báo chưa đăng, hoặc bản Công
# báo là PDF scan (ví dụ QĐ 13/2023/QĐ-TTg). Với các danh mục đó phải bóc từ
# trang web đăng toàn văn. curl_cffi giả lập Chrome vì các site này chặn
# requests thường (403).
UA_TRINH_DUYET = 'chrome'


def tai_html(url: str, tai_lai: bool = False, thu_muc: str | None = None) -> str:
    """Tải HTML, có cache ra đĩa để chạy lại không phải gọi mạng."""
    from curl_cffi import requests as creq

    thu_muc = thu_muc or os.path.join(os.path.dirname(THU_MUC_TAI), 'html_goc')
    os.makedirs(thu_muc, exist_ok=True)
    ten = re.sub(r'[^A-Za-z0-9]+', '_', url)[-120:] + '.html'
    dich = os.path.join(thu_muc, ten)
    if os.path.exists(dich) and not tai_lai:
        return open(dich, encoding='utf-8').read()
    r = creq.get(url, impersonate=UA_TRINH_DUYET, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code} khi tải {url}')
    open(dich, 'w', encoding='utf-8').write(r.text)
    print(f'  tải {url[:78]}… -> {len(r.text)} byte')
    return r.text


def cac_bang_html(html: str, it_nhat: int = 4) -> list[list[list[str]]]:
    """Rút mọi <table> có >= `it_nhat` hàng thành list[hàng][ô] đã chuẩn hoá."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'lxml')
    for t in soup(['script', 'style']):
        t.decompose()
    ket_qua = []
    for b in soup.find_all('table'):
        hang = b.find_all('tr')
        if len(hang) < it_nhat:
            continue
        ket_qua.append([[chuan_hoa(o.get_text(' ', strip=True))
                         for o in h.find_all(['td', 'th'])] for h in hang])
    return ket_qua


def cac_dong_text(html: str) -> list[str]:
    """Text của trang, tách dòng, đã bỏ dòng rác của giao diện LuatVietnam."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'lxml')
    for t in soup(['script', 'style']):
        t.decompose()
    bo = {'Đang theo dõi', 'Đã biết'}
    return [d for d in (chuan_hoa(x) for x in soup.get_text('\n', strip=True).split('\n'))
            if d and d not in bo]


def bo_dau(s: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp tên cột / tìm kiếm."""
    import unicodedata
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.replace('đ', 'd').replace('Đ', 'D').lower()


# ------------------------------------------------------------------- Excel

def ghi_excel(duong_dan: str, cac_bang: dict, do_rong: dict | None = None) -> None:
    """Ghi nhiều DataFrame ra 1 file Excel: cố định dòng tiêu đề, xuống dòng, autofilter."""
    import pandas as pd
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    os.makedirs(os.path.dirname(os.path.abspath(duong_dan)), exist_ok=True)
    with pd.ExcelWriter(duong_dan, engine='openpyxl') as writer:
        for ten_sheet, df in cac_bang.items():
            df.to_excel(writer, sheet_name=ten_sheet[:31], index=False)
            ws = writer.sheets[ten_sheet[:31]]
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for i, cot in enumerate(df.columns, start=1):
                chu = get_column_letter(i)
                rong = (do_rong or {}).get(cot)
                if rong is None:
                    dai = max([len(str(cot))] +
                              [len(str(v)) for v in df[cot].head(400).tolist()] or [10])
                    rong = min(max(dai + 2, 9), 60)
                ws.column_dimensions[chu].width = rong
                ws.cell(row=1, column=i).font = Font(bold=True, color='FFFFFF')
                ws.cell(row=1, column=i).fill = PatternFill('solid', fgColor='1F5E6E')
                ws.cell(row=1, column=i).alignment = Alignment(
                    vertical='center', wrap_text=True)
            for hang in ws.iter_rows(min_row=2):
                for o in hang:
                    o.alignment = Alignment(vertical='top', wrap_text=True)
    print(f'  -> {duong_dan}')
