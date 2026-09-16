# -*- coding: utf-8 -*-
"""Trích DANH MỤC NGHỀ, CÔNG VIỆC NẶNG NHỌC, ĐỘC HẠI, NGUY HIỂM ra Excel.

Nguồn (bản Công báo chính thức):
  * TT 11/2020/TT-BLĐTBXH - 12/11/2020, hiệu lực 01/3/2021 - danh mục gốc.
  * TT 19/2023/TT-BLĐTBXH - 29/12/2023, hiệu lực 15/02/2024 - bổ sung.

Cấu trúc bản gốc: mỗi lĩnh vực (số La Mã) là một bảng 3 cột
    TT | Tên nghề hoặc công việc | Đặc điểm điều kiện lao động
bên trong bảng có các hàng gộp ô ghi "Điều kiện lao động loại IV/V/VI" đóng vai
trò phân nhóm, và số TT được đánh lại từ 1 ở mỗi nhóm.

Hai chỗ dễ sai khi bóc tách, đã xử lý ở đây:
  1. Bản Công báo TT 11/2020 bị cắt làm 2 số (301+302 và 303+304).
  2. Hai tiêu đề lĩnh vực (XXXVII. GIÁO DỤC - ĐÀO TẠO và XXXXI. TÀI NGUYÊN MÔI
     TRƯỜNG) nằm LỌT vào trong bảng của lĩnh vực trước chứ không phải là đoạn
     văn riêng - nếu chỉ đọc đoạn văn sẽ gán nhầm nghề sang lĩnh vực khác.

Chạy:  venv\\Scripts\\python.exe danh_muc_nghe.py
"""
from __future__ import annotations

import os
import re

import pandas as pd
from docx import Document

from danh_muc_common import (cac_bang_html, chuan_hoa, chuyen_sang_docx, duyet_khoi,
                             ghi_excel, gom_trung_lien_tiep, o_hang, tai_html,
                             tai_tat_ca_van_ban, tai_van_ban)

TT11 = 'https://congbao.chinhphu.vn/van-ban/thong-tu-so-11-2020-tt-bldtbxh-33183.htm'
TT19 = 'https://congbao.chinhphu.vn/van-ban/thong-tu-so-19-2023-tt-bldtbxh-41242/48815.htm'
# Danh mục RIÊNG cho Quân đội - TT 28/2025/TT-BNV (31/12/2025, hiệu lực
# 01/3/2026, bãi bỏ QĐ 1085/LĐTBXH-QĐ 1996). Công báo chưa đăng nên lấy bản web.
TT28 = ('https://luatvietnam.vn/lao-dong/thong-tu-28-2025-tt-bnv-danh-muc-nghe-nang-'
        'nhoc-doc-hai-trong-quan-doi-430915-d1.html')

THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_EXCEL = os.path.join(THU_MUC, 'data', 'danh_muc_nghe_nndhnh.xlsx')

RE_LINH_VUC = re.compile(r'^([IVX]+)\.\s*(.+)$')
RE_LOAI = re.compile(r'Điều kiện lao động loại\s*([IVX]+)', re.IGNORECASE)

COT = ['id', 'van_ban', 'so_linh_vuc', 'linh_vuc', 'dieu_kien_lao_dong',
       'phan_loai', 'stt', 'ten_nghe_cong_viec', 'dac_diem_dieu_kien_lao_dong']
DO_RONG = {'id': 6, 'van_ban': 22, 'so_linh_vuc': 11, 'linh_vuc': 34,
           'dieu_kien_lao_dong': 15, 'phan_loai': 34, 'stt': 6,
           'ten_nghe_cong_viec': 52, 'dac_diem_dieu_kien_lao_dong': 68}


def _phan_loai(loai: str) -> str:
    if loai == 'IV':
        return 'Nặng nhọc, độc hại, nguy hiểm'
    if loai in ('V', 'VI'):
        return 'Đặc biệt nặng nhọc, độc hại, nguy hiểm'
    return ''


def _la_tieu_de_linh_vuc(text: str):
    """'XV. Y TẾ VÀ DƯỢC' -> ('XV', 'Y TẾ VÀ DƯỢC'). Tiêu đề luôn viết HOA."""
    m = RE_LINH_VUC.match(text)
    if m and text == text.upper() and len(m.group(2)) > 2:
        return m.group(1), m.group(2)
    return None


def _doc_bang(cac_hang: list[list[str]], trang_thai: dict, ket_qua: list,
              van_ban: str) -> dict:
    """Đọc một bảng danh mục. Nhận danh sách hàng đã tách ô, nên dùng được cho
    cả bảng .docx (Công báo) lẫn bảng HTML (TT 28/2025 chỉ có bản web)."""
    loai = None
    thong_ke = {'tieu_de': 0, 'nhom': 0, 'du_lieu': 0, 'trong': 0}
    for chi_so, hang in enumerate(cac_hang):
        o = gom_trung_lien_tiep([x for x in hang if x])
        if not o:
            thong_ke['trong'] += 1
            continue
        gop = ' '.join(o)

        if chi_so == 0 and gop.startswith('TT'):        # hàng tiêu đề cột
            thong_ke['tieu_de'] += 1
            continue
        if len(o) == 1 and (td := _la_tieu_de_linh_vuc(gop)):   # tiêu đề lọt vào bảng
            trang_thai['so'], trang_thai['ten'] = td
            loai = None
            thong_ke['nhom'] += 1
            continue
        if (m := RE_LOAI.search(gop)) and len(o) <= 2 and not o[0].isdigit():
            loai = m.group(1)                           # hàng gộp phân nhóm
            thong_ke['nhom'] += 1
            continue
        if gop == 'TT' or o[0] == 'TT':                 # tiêu đề lặp khi sang trang
            thong_ke['tieu_de'] += 1
            continue

        if o[0].isdigit():
            stt, ten = o[0], o[1] if len(o) > 1 else ''
            dac_diem = o[2] if len(o) > 2 else ''
        else:
            stt, ten, dac_diem = '', o[0], o[1] if len(o) > 1 else ''
        if not ten:
            thong_ke['trong'] += 1
            continue

        thong_ke['du_lieu'] += 1
        ket_qua.append({
            'van_ban': van_ban,
            'so_linh_vuc': trang_thai['so'],
            'linh_vuc': trang_thai['ten'],
            'dieu_kien_lao_dong': f'Loại {loai}' if loai else '',
            'phan_loai': _phan_loai(loai or ''),
            'stt': stt,
            'ten_nghe_cong_viec': ten,
            'dac_diem_dieu_kien_lao_dong': dac_diem,
        })
    return thong_ke


def trich(duong_dan_docx: list[str], van_ban: str) -> list[dict]:
    ket_qua: list[dict] = []
    trang_thai = {'so': None, 'ten': None}
    for duong_dan in duong_dan_docx:
        doc = Document(duong_dan)
        cho_tieu_de, dang_trong_danh_muc = [], False
        tieu_de_moi = None
        for khoi in duyet_khoi(doc):
            if hasattr(khoi, 'rows'):                   # bảng
                if not (dang_trong_danh_muc or trang_thai['ten']):
                    continue
                if tieu_de_moi:
                    trang_thai['so'], trang_thai['ten'] = tieu_de_moi[0], (
                        ' '.join([tieu_de_moi[1]] + cho_tieu_de))
                    tieu_de_moi, cho_tieu_de = None, []
                cac_hang = [o_hang(h) for h in khoi.rows]
                thong_ke = _doc_bang(cac_hang, trang_thai, ket_qua, van_ban)
                tong = sum(thong_ke.values())
                if tong != len(cac_hang):       # không hàng nào bị bỏ sót lặng lẽ
                    raise AssertionError(
                        f'{van_ban} - {trang_thai["so"]}. {trang_thai["ten"]}: '
                        f'đọc {tong}/{len(cac_hang)} hàng ({thong_ke})')
                continue

            text = chuan_hoa(khoi.text)
            if not text:
                continue
            if (td := _la_tieu_de_linh_vuc(text)):
                tieu_de_moi, cho_tieu_de = td, []
                dang_trong_danh_muc = True
            elif tieu_de_moi and text == text.upper() and not text.startswith('('):
                cho_tieu_de.append(text)                # tiêu đề lĩnh vực xuống 2 dòng
    return ket_qua


def trich_html(url: str, van_ban: str) -> list[dict]:
    """TT 28/2025 chỉ có bản web: cả danh mục nằm trong MỘT bảng HTML, tiêu đề
    lĩnh vực và dòng "ĐIỀU KIỆN LAO ĐỘNG LOẠI …" nằm lọt trong bảng đó."""
    ket_qua: list[dict] = []
    trang_thai = {'so': None, 'ten': None}
    for bang in cac_bang_html(tai_html(url), it_nhat=20):
        if not bang or 'TT' not in (bang[0][0] if bang[0] else ''):
            continue
        thong_ke = _doc_bang(bang, trang_thai, ket_qua, van_ban)
        tong = sum(thong_ke.values())
        if tong != len(bang):
            raise AssertionError(f'{van_ban}: đọc {tong}/{len(bang)} hàng ({thong_ke})')
        break
    if not ket_qua:
        raise RuntimeError(f'Không tìm thấy bảng danh mục trong {url}')
    return ket_qua


def main() -> None:
    print('1. Tải bản Công báo')
    tep11 = [chuyen_sang_docx(p) for p in tai_tat_ca_van_ban(TT11, 'TT_11_2020', 'doc')]
    tep19 = [chuyen_sang_docx(tai_van_ban(TT19, 'TT_19_2023', uu_tien=('doc',)))]

    print('2. Trích danh mục')
    dong = (trich(tep11, 'TT 11/2020/TT-BLĐTBXH')
            + trich(tep19, 'TT 19/2023/TT-BLĐTBXH')
            + trich_html(TT28, 'TT 28/2025/TT-BNV'))
    for i, d in enumerate(dong, start=1):
        d['id'] = i

    df = pd.DataFrame(dong)[COT]
    tong_hop = (df.groupby(['van_ban', 'so_linh_vuc', 'linh_vuc'], sort=False)
                  .agg(so_nghe=('id', 'size'),
                       loai_IV=('dieu_kien_lao_dong', lambda s: (s == 'Loại IV').sum()),
                       loai_V=('dieu_kien_lao_dong', lambda s: (s == 'Loại V').sum()),
                       loai_VI=('dieu_kien_lao_dong', lambda s: (s == 'Loại VI').sum()))
                  .reset_index())

    print(f'   tổng: {len(df)} nghề / {tong_hop.shape[0]} lĩnh vực')
    print('  ', df['dieu_kien_lao_dong'].value_counts().to_dict())

    print('3. Ghi Excel')
    ghi_excel(FILE_EXCEL, {'Danh mục nghề': df, 'Tổng hợp theo lĩnh vực': tong_hop},
              DO_RONG)
    df.to_csv(os.path.join(THU_MUC, 'data', 'danh_muc_nghe_nndhnh.csv'),
              index=False, encoding='utf-8-sig')
    df.to_json(os.path.join(THU_MUC, 'data', 'danh_muc_nghe_nndhnh.json'),
               orient='records', force_ascii=False, indent=1)


if __name__ == '__main__':
    main()
