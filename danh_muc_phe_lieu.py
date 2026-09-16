# -*- coding: utf-8 -*-
"""Trích hai DANH MỤC PHẾ LIỆU ra Excel. Đây là HAI danh mục khác nhau:

  * **Được phép nhập khẩu làm nguyên liệu sản xuất** - Quyết định 13/2023/QĐ-TTg
    (22/5/2023, hiệu lực 01/6/2023, thay QĐ 28/2020/QĐ-TTg). 5 nhóm: sắt/thép/
    gang, nhựa, giấy, thủy tinh, kim loại màu.
  * **Tạm ngừng kinh doanh tạm nhập, tái xuất, chuyển khẩu** - Thông tư
    41/2026/TT-BCT (22/7/2026, hiệu lực **05/9/2026 đến 31/12/2029**, bãi bỏ TT
    18/2024/TT-BCT). Phụ lục I: phế liệu; Phụ lục II: hàng hóa đã qua sử dụng.

Vì sao không lấy từ Công báo như các danh mục khác:
  * QĐ 13/2023: bản Công báo là **PDF SCAN, không có lớp text** (đã tải thử:
    5 trang, chỉ 153 ký tự) -> muốn dùng file gốc thì phải OCR.
  * TT 41/2026/TT-BCT: Công báo chưa index, moit.gov.vn đăng tin nhưng không
    đính kèm file.
Nên cả hai đều bóc từ trang đăng toàn văn của luatvietnam.vn.

LƯU Ý khi dùng: cả hai phụ lục của TT 41/2026 áp dụng quy tắc "liệt kê mã 2, 4
hoặc 6 số thì mọi mã 8 số thuộc nhóm đó đều áp dụng" - quy tắc nằm ở phần lời,
KHÔNG nằm trong bảng, nên tra theo bảng thôi là chưa đủ.

Chạy:  venv\\Scripts\\python.exe danh_muc_phe_lieu.py
"""
from __future__ import annotations

import os
import re

import pandas as pd

from danh_muc_common import bo_dau, cac_bang_html, ghi_excel, tai_html

URL_QD13 = ('https://luatvietnam.vn/xuat-nhap-khau/quyet-dinh-13-2023-qd-ttg-phe-lieu-'
            'duoc-phep-nhap-khau-lam-nguyen-lieu-san-xuat-253214-d1.html')
URL_TT41 = ('https://luatvietnam.vn/xuat-nhap-khau/thong-tu-41-2026-tt-bct-danh-muc-'
            'phe-lieu-va-hang-hoa-tam-ngung-kinh-doanh-441401-d1.html')

THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_EXCEL = os.path.join(THU_MUC, 'data', 'danh_muc_phe_lieu.xlsx')

DO_RONG = {'stt': 8, 'nhom': 30, 'mo_ta': 86, 'ma_hs': 14, 'van_ban': 22,
           'phu_luc': 26}
RE_STT_NHOM = re.compile(r'^\d+$')
RE_STT_MUC = re.compile(r'^\d+\.\d+$')


def _la_bang_thong_tin(bang: list[list[str]]) -> bool:
    """Bảng metadata của luatvietnam (Cơ quan ban hành / Số hiệu / …), bỏ qua."""
    return any('Cơ quan ban hành' in o for h in bang[:2] for o in h)


def trich_qd13() -> list[dict]:
    """QĐ 13/2023: bảng bị cắt thành nhiều <table>, cột HS tách làm 3 mảnh."""
    dong, nhom, muc_cha = [], '', ''
    for bang in cac_bang_html(tai_html(URL_QD13), it_nhat=1):
        if _la_bang_thong_tin(bang):
            continue
        for o in bang:
            if len(o) == 5:
                stt, mo_ta, hs = o[0], o[1], [o[2], o[3], o[4]]
            elif len(o) == 4:                 # dòng con, không có số thứ tự
                stt, mo_ta, hs = '', o[0], [o[1], o[2], o[3]]
            else:                             # khối chữ ký, hàng tiêu đề 3 ô…
                continue
            ma_hs = ''.join(x for x in hs if x)
            if not mo_ta:
                continue
            if not ma_hs:
                if RE_STT_NHOM.match(stt):        # nhóm lớn: 1., 2., 3.…
                    nhom, muc_cha = f'{stt}. {mo_ta}', ''
                elif RE_STT_MUC.match(stt):       # mục cha của các dòng con:
                    muc_cha = f'{stt}. {mo_ta}'   # "2.5 Từ plastic khác:"
                continue
            dong.append({'van_ban': 'QĐ 13/2023/QĐ-TTg',
                         'phu_luc': 'Danh mục phế liệu được phép nhập khẩu',
                         'nhom': nhom, 'muc_cha': muc_cha if not stt else '',
                         'stt': stt, 'mo_ta': mo_ta, 'ma_hs': ma_hs})
            if stt:
                muc_cha = ''
    return dong


def trich_tt41() -> tuple[list[dict], list[dict]]:
    """TT 41/2026/TT-BCT: 2 bảng 'Mã hàng | Mô tả mặt hàng' (Phụ lục I và II)."""
    ket_qua = []
    for bang in cac_bang_html(tai_html(URL_TT41), it_nhat=4):
        if _la_bang_thong_tin(bang):
            continue
        if 'ma hang' not in bo_dau(bang[0][0] if bang[0] else ''):
            continue
        dong = []
        for o in bang[1:]:
            if len(o) < 2 or not o[1]:
                continue
            dong.append({'van_ban': 'TT 41/2026/TT-BCT', 'nhom': '', 'muc_cha': '',
                         'stt': '', 'ma_hs': o[0], 'mo_ta': o[1]})
        if dong:
            ket_qua.append(dong)
    if len(ket_qua) < 2:
        raise RuntimeError(f'Chỉ thấy {len(ket_qua)} bảng phụ lục trong TT 41/2026')
    pl1, pl2 = ket_qua[0], ket_qua[1]
    for d in pl1:
        d['phu_luc'] = 'Phụ lục I - Phế liệu tạm ngừng KD tạm nhập, tái xuất'
    for d in pl2:
        d['phu_luc'] = 'Phụ lục II - Hàng hóa đã qua sử dụng tạm ngừng KD'
    for i, d in enumerate(pl1, 1):
        d['stt'] = str(i)
    for i, d in enumerate(pl2, 1):
        d['stt'] = str(i)
    return pl1, pl2


def main() -> None:
    print('1. Quyết định 13/2023/QĐ-TTg - phế liệu ĐƯỢC PHÉP nhập khẩu')
    qd13 = trich_qd13()
    print(f'   {len(qd13)} dòng / {len({d["nhom"] for d in qd13})} nhóm')

    print('2. Thông tư 41/2026/TT-BCT - TẠM NGỪNG tạm nhập, tái xuất, chuyển khẩu')
    pl1, pl2 = trich_tt41()
    print(f'   Phụ lục I: {len(pl1)} dòng | Phụ lục II: {len(pl2)} dòng')

    cot = ['van_ban', 'phu_luc', 'nhom', 'muc_cha', 'stt', 'ma_hs', 'mo_ta']
    tat_ca = pd.DataFrame(qd13 + pl1 + pl2)[cot]

    print('3. Ghi Excel')
    ghi_excel(FILE_EXCEL, {
        'Được phép NK - QĐ 13.2023': pd.DataFrame(qd13)[
            ['nhom', 'muc_cha', 'stt', 'ma_hs', 'mo_ta']],
        'Tạm ngừng - PL I phế liệu': pd.DataFrame(pl1)[['stt', 'ma_hs', 'mo_ta']],
        'Tạm ngừng - PL II đã sử dụng': pd.DataFrame(pl2)[['stt', 'ma_hs', 'mo_ta']],
        'Tất cả': tat_ca,
    }, DO_RONG)
    tat_ca.to_csv(os.path.join(THU_MUC, 'data', 'danh_muc_phe_lieu.csv'),
                  index=False, encoding='utf-8-sig')


if __name__ == '__main__':
    main()
