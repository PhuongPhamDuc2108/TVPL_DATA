# -*- coding: utf-8 -*-
"""Trích DANH MỤC BÍ MẬT NHÀ NƯỚC ra Excel.

Đây không phải một văn bản mà là **một HỌ quyết định của Thủ tướng, mỗi lĩnh vực
một quyết định**. Nền pháp lý mới: Luật Bảo vệ bí mật nhà nước số 117/2025/QH15
(thông qua 10/12/2025, **hiệu lực 01/3/2026**, thay Luật 2018, gom còn 13 lĩnh
vực) - nên cả họ đang được ban hành lại trong 2025-2026.

Hai thứ script này lấy được:
  1. **Chỉ mục 31 quyết định** đang hiệu lực và công khai (số hiệu, lĩnh vực,
     ngày ban hành, ngày hiệu lực) - ĐẦY ĐỦ.
  2. **Các khoản** bên trong, với những quyết định tìm được trang toàn văn.

GIỚI HẠN, không phải thiếu sót tra cứu:
  * Ba lĩnh vực **quốc phòng, an ninh quốc gia - TTATXH, cơ yếu** có quyết định
    riêng nhưng **bản thân quyết định không đăng công khai** -> không có nguồn.
  * Các site đều chặn tìm kiếm theo số hiệu (Công báo trả kết quả không lọc,
    thuvienphapluat /van-ban/ 403, luatvietnam /tim-van-ban 403), nên link toàn
    văn phải tìm thủ công từng văn bản rồi điền vào TOAN_VAN dưới đây. Thêm được
    link nào thì script tự bóc thêm khoản của văn bản đó.

Cấu trúc bản gốc (văn xuôi, KHÔNG có bảng): mỗi độ mật là một Điều -
"Điều 1. Bí mật nhà nước độ Tối mật gồm:" - bên dưới là các khoản đánh số
1., 2., 3. …; hết phần độ mật là tới "Điều N. Hiệu lực thi hành".

Chạy:  venv\\Scripts\\python.exe danh_muc_bi_mat_nha_nuoc.py
"""
from __future__ import annotations

import os
import re

import pandas as pd

from danh_muc_common import (cac_bang_html, cac_dong_text, chuan_hoa, ghi_excel,
                             tai_html)

URL_CHI_MUC = ('https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-'
               'luat/tu-van-phap-luat/30388/tong-hop-danh-muc-bi-mat-nha-nuoc-trong-'
               'cac-linh-vuc')

# số hiệu -> trang toàn văn. Bổ sung dần khi tìm được link.
TOAN_VAN = {
    '19/QĐ-TTg': 'https://luatvietnam.vn/van-hoa/quyet-dinh-19-qd-ttg-2026-ban-hanh-'
                 'danh-muc-bi-mat-nha-nuoc-linh-vuc-van-hoa-thong-tin-423322-d1.html',
    '562/QĐ-TTg': 'https://luatvietnam.vn/an-ninh-quoc-gia/quyet-dinh-562-qd-ttg-2025-'
                  'danh-muc-bi-mat-nha-nuoc-linh-vuc-tai-nguyen-va-moi-truong-393233-'
                  'd1.html',
    '774/QĐ-TTg': 'https://luatvietnam.vn/tiet-kiem/quyet-dinh-774-qd-ttg-danh-muc-bi-'
                  'mat-nha-nuoc-linh-vuc-thanh-tra-khieu-nai-184396-d1.html',
    '970/QĐ-TTg': 'https://luatvietnam.vn/tu-phap/quyet-dinh-970-qd-ttg-2020-danh-muc-'
                  'bi-mat-nha-nuoc-thuoc-toa-an-186181-d1.html',
}

THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_EXCEL = os.path.join(THU_MUC, 'data', 'danh_muc_bi_mat_nha_nuoc.xlsx')

# Cách trình bày không đồng nhất giữa các quyết định:
#   - "Điều 1. Bí mật nhà nước độ Tối mật gồm:"  (một dòng)
#   - "Điều 1" / "." / "Bí mật nhà nước độ Tối mật gồm:"  (tách ba dòng - QĐ 970)
#   - khoản: "1. Nội dung…"  hoặc  "1." rồi nội dung ở dòng sau
RE_DO_MAT = re.compile(r'Bí mật nhà nước độ\s+(Tuyệt mật|Tối mật|Mật)\b')
RE_DIEU = re.compile(r'^Điều\s+\d+\b')
RE_KHOAN = re.compile(r'^(\d+)\.\s+(\S.*)$')
RE_KHOAN_TRONG = re.compile(r'^(\d+)\.$')
RE_DIEM = re.compile(r'^([a-zđ])\)\s*(\S.*)$')     # điểm a), b), c) trong khoản
DO_RONG = {'so_hieu': 15, 'linh_vuc': 56, 'ngay_ban_hanh': 14, 'ngay_hieu_luc': 14,
           'co_toan_van': 12, 'do_mat': 11, 'so_khoan': 8, 'noi_dung': 110,
           'nguon': 40}


def trich_chi_muc() -> list[dict]:
    """Bảng 'Văn bản | Lĩnh vực | Ngày ban hành | Ngày có hiệu lực'."""
    for bang in cac_bang_html(tai_html(URL_CHI_MUC), it_nhat=10):
        if not bang or len(bang[0]) < 3 or 'Văn bản' not in bang[0][0]:
            continue
        dong = []
        for o in bang[1:]:
            if len(o) < 4 or not o[0]:
                continue
            dong.append({
                'so_hieu': chuan_hoa(o[0]).replace('Quyết định ', ''),
                'linh_vuc': o[1],
                'ngay_ban_hanh': o[2],
                'ngay_hieu_luc': o[3],
            })
        if dong:
            return dong
    raise RuntimeError('Không tìm thấy bảng chỉ mục quyết định BMNN')


def trich_khoan(so_hieu: str, url: str, linh_vuc: str) -> list[dict]:
    """Tách các khoản theo từng độ mật trong một quyết định (văn xuôi)."""
    dong, do_mat, dang_gom, cho_so = [], None, False, None
    khoan_hien_tai, cho_dieu = '', False

    def them(so_khoan: str, noi_dung: str, diem: str = '') -> None:
        dong.append({'so_hieu': so_hieu, 'linh_vuc': linh_vuc, 'do_mat': do_mat,
                     'so_khoan': so_khoan, 'diem': diem, 'noi_dung': noi_dung,
                     'nguon': url})

    for text in cac_dong_text(tai_html(url)):
        if text == '.':
            continue
        m = RE_DO_MAT.search(text)
        # Chỉ nhận tiêu đề độ mật khi nó nằm ngay sau "Điều N", để (a) không khớp
        # nhầm cụm "…bí mật nhà nước độ Mật…" giữa câu, và (b) không nuốt phải
        # đoạn TÓM TẮT do trang web tự viết ở đầu bài.
        if m and (text.startswith('Điều') or cho_dieu):
            do_mat, dang_gom, cho_so = m.group(1), True, None
            khoan_hien_tai, cho_dieu = '', False
            continue
        if RE_DIEU.match(text):     # Điều khác (hiệu lực, trách nhiệm…) -> ngừng gom
            dang_gom = False
            cho_dieu = bool(re.fullmatch(r'Điều\s+\d+\.?', text))
            continue
        cho_dieu = False
        if not dang_gom:
            continue

        k = RE_KHOAN.match(text)
        if k:
            khoan_hien_tai = k.group(1)
            them(khoan_hien_tai, k.group(2))
            cho_so = None
            continue
        kt = RE_KHOAN_TRONG.match(text)
        if kt:                      # số khoản đứng riêng một dòng, nội dung ở dòng sau
            cho_so = kt.group(1)
            continue
        d = RE_DIEM.match(text)
        if d and khoan_hien_tai:    # điểm a), b), c) thuộc khoản đang xét
            them(khoan_hien_tai, d.group(2), d.group(1))
            continue
        if cho_so:
            khoan_hien_tai = cho_so
            them(cho_so, text)
            cho_so = None
        elif dong and dong[-1]['do_mat'] == do_mat:
            noi = dong[-1]['noi_dung']          # dòng nối tiếp của khoản/điểm trước
            dong[-1]['noi_dung'] = chuan_hoa(noi + ' ' + text)
        else:                       # khoản duy nhất, không đánh số (QĐ 970 Điều 1)
            khoan_hien_tai = '1'
            them('1', text)
    return dong


def main() -> None:
    print('1. Chỉ mục các quyết định')
    chi_muc = trich_chi_muc()
    print(f'   {len(chi_muc)} quyết định đang hiệu lực & công khai')

    print('2. Tách khoản ở những quyết định có trang toàn văn')
    khoan = []
    for d in chi_muc:
        url = TOAN_VAN.get(d['so_hieu'])
        d['co_toan_van'] = 'x' if url else ''
        d['nguon_toan_van'] = url or ''
        if not url:
            continue
        try:
            k = trich_khoan(d['so_hieu'], url, d['linh_vuc'])
        except Exception as e:
            print(f'   ! {d["so_hieu"]}: {type(e).__name__} {e}')
            continue
        khoan += k
        dem = {}
        for x in k:
            dem[x['do_mat']] = dem.get(x['do_mat'], 0) + 1
        print(f'   {d["so_hieu"]:14} {d["linh_vuc"][:34]:34} {len(k):3} khoản  {dem}')

    co = sum(1 for d in chi_muc if d['co_toan_van'])
    print(f'   -> có toàn văn: {co}/{len(chi_muc)} quyết định, tổng {len(khoan)} khoản')
    print('   (3 lĩnh vực quốc phòng / an ninh / cơ yếu KHÔNG công khai, '
          'không có trong chỉ mục)')

    print('3. Ghi Excel')
    ghi_excel(FILE_EXCEL, {
        'Văn bản': pd.DataFrame(chi_muc)[
            ['so_hieu', 'linh_vuc', 'ngay_ban_hanh', 'ngay_hieu_luc', 'co_toan_van',
             'nguon_toan_van']],
        'Khoản': pd.DataFrame(khoan)[
            ['so_hieu', 'linh_vuc', 'do_mat', 'so_khoan', 'diem', 'noi_dung',
             'nguon']],
    }, DO_RONG)


if __name__ == '__main__':
    main()
