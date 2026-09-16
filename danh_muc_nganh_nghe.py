# -*- coding: utf-8 -*-
"""Trích DANH MỤC NGÀNH, NGHỀ ĐẦU TƯ KINH DOANH CÓ ĐIỀU KIỆN ra Excel.

Danh mục này đang trong giai đoạn thay đổi liên tiếp, phải giữ cả hai bản:

  * **198 ngành nghề** - Phụ lục IV Luật Đầu tư số 143/2025/QH15 (thông qua
    11/12/2025). Luật hiệu lực 01/3/2026 nhưng riêng Điều 7 + Phụ lục IV chỉ
    hiệu lực từ 01/7/2026; trước đó vẫn áp danh mục 227 ngành của Luật Đầu tư
    61/2020/QH14.
  * **142 ngành nghề** - Nghị quyết 66.17/2026/NQ-CP ngày 15/5/2026 cắt giảm 56
    ngành, **hiệu lực 01/7/2026 đến hết 28/02/2027** (có thời hạn). Đây mới là
    con số THỰC THI hiện nay, dù Phụ lục IV của Luật vẫn ghi 198.

Không tải được file gốc: Công báo không tra được theo số hiệu, trang /van-ban/
của thuvienphapluat chặn 403. Nên bóc từ trang bài viết đăng nguyên bảng.

Chạy:  venv\\Scripts\\python.exe danh_muc_nganh_nghe.py
"""
from __future__ import annotations

import os
import re

import pandas as pd

from danh_muc_common import bo_dau, cac_bang_html, ghi_excel, tai_html

# Bảng 198 ngành (Phụ lục IV Luật Đầu tư 143/2025/QH15)
URL_198 = ('https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/'
           'chinh-sach-moi/101784/danh-muc-198-nganh-nghe-dau-tu-kinh-doanh-co-dieu-'
           'kien-tu-01-7-2026')
# Bảng 142 ngành (Phụ lục Nghị quyết 66.17/2026/NQ-CP)
URL_142 = ('https://luatvietnam.vn/linh-vuc-khac/danh-sach-cac-nganh-nghe-kinh-doanh-'
           'co-dieu-kien-moi-nhat-tu-01-7-2026-883-109489-article.html')
# Bảng CŨ - Phụ lục IV Luật Đầu tư 61/2020/QH14 đã hợp nhất các luật sửa đổi
# (Luật 03/2022, Điện ảnh 2022, Kinh doanh bảo hiểm 2022, Tần số VTĐ 2022, Giao
# dịch điện tử 2023, Căn cước 2023, Tài nguyên nước 2023, Lưu trữ 2024, Luật
# 57/2024, Luật 90/2025). Áp dụng đến hết 30/6/2026 - giữ lại để làm BẪY LUẬT CŨ
# cho bộ test: AI học dữ liệu cũ sẽ trả lời theo bản này.
URL_CU = ('https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/'
          'chinh-sach-moi/29831/227-nganh-nghe-kinh-doanh-co-dieu-kien-theo-luat-'
          'dau-tu-2020')

THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_EXCEL = os.path.join(THU_MUC, 'data', 'danh_muc_nganh_nghe_kdcdk.xlsx')

DO_RONG = {'stt': 6, 'nganh_nghe': 92, 'con_trong_142': 13, 'stt_142': 8,
           'trang_thai': 20, 'nguon': 30}


def _bang_nganh_nghe(html: str, so_dong_mong_doi: int) -> list[dict]:
    """Lấy bảng 2 cột STT | Ngành, nghề trong trang."""
    for bang in cac_bang_html(html, it_nhat=20):
        if not bang or len(bang[0]) < 2:
            continue
        if bo_dau(bang[0][0]) != 'stt':
            continue
        dong = []
        for o in bang[1:]:
            if len(o) < 2 or not o[1]:
                continue
            stt = re.sub(r'\D', '', o[0])
            dong.append({'stt': stt or str(len(dong) + 1), 'nganh_nghe': o[1]})
        if dong:
            if so_dong_mong_doi and len(dong) != so_dong_mong_doi:
                print(f'   ! bảng có {len(dong)} dòng, mong đợi {so_dong_mong_doi}')
            return dong
    raise RuntimeError('Không tìm thấy bảng "STT | Ngành, nghề" trong trang')


def _khoa(ten: str) -> str:
    """Khoá so khớp giữa hai bản danh mục: bỏ dấu, bỏ dấu câu, gom khoảng trắng."""
    return re.sub(r'[^a-z0-9 ]+', ' ', bo_dau(ten)).strip()


def _ghep_gan_dung(con_198: list[dict], con_142: list[dict],
                   nguong: float = 0.55) -> list[tuple]:
    """Ghép cặp ngành đổi tên giữa hai bản, theo độ giống chuỗi, ưu tiên cặp giống nhất."""
    from difflib import SequenceMatcher

    cap = []
    for b in con_142:
        for a in con_198:
            ty_le = SequenceMatcher(None, _khoa(a['nganh_nghe']),
                                    _khoa(b['nganh_nghe'])).ratio()
            if ty_le >= nguong:
                cap.append((ty_le, a, b))
    cap.sort(key=lambda x: -x[0])
    da_dung_a, da_dung_b, ket_qua = set(), set(), []
    for ty_le, a, b in cap:
        if id(a) in da_dung_a or id(b) in da_dung_b:
            continue
        da_dung_a.add(id(a))
        da_dung_b.add(id(b))
        ket_qua.append((a, b, ty_le))
    return ket_qua


def main() -> None:
    print('1. Tải ba bản danh mục')
    dcu = _bang_nganh_nghe(tai_html(URL_CU), 0)
    d198 = _bang_nganh_nghe(tai_html(URL_198), 198)
    d142 = _bang_nganh_nghe(tai_html(URL_142), 142)
    print(f'   bản cũ: {len(dcu)} dòng | 198 ngành: {len(d198)} dòng | '
          f'142 ngành: {len(d142)} dòng')

    for d in dcu:
        d['nguon'] = 'Phụ lục IV Luật Đầu tư 61/2020/QH14 (đã hợp nhất sửa đổi)'
    for d in d198:
        d['nguon'] = 'Phụ lục IV Luật Đầu tư 143/2025/QH15'
    for d in d142:
        d['nguon'] = 'Phụ lục Nghị quyết 66.17/2026/NQ-CP'

    print('2. Đối chiếu 198 -> 142 để tìm ngành bị cắt giảm')
    map142 = {}
    for d in d142:
        map142.setdefault(_khoa(d['nganh_nghe']), d)

    for d in d198:
        khop = map142.get(_khoa(d['nganh_nghe']))
        d['con_trong_142'] = 'x' if khop else ''
        d['stt_142'] = khop['stt'] if khop else ''
        d['trang_thai'] = 'Còn điều kiện' if khop else 'ĐÃ CẮT GIẢM'

    khop_nguoc = {_khoa(d['nganh_nghe']) for d in d198}
    moi_trong_142 = [d for d in d142 if _khoa(d['nganh_nghe']) not in khop_nguoc]
    chua_khop = [d for d in d198 if not d['con_trong_142']]
    print(f'   khớp tên nguyên văn: {len(d198) - len(chua_khop)} | '
          f'lệch ở bản 198: {len(chua_khop)} | chỉ có ở bản 142: {len(moi_trong_142)}')

    # Nghị quyết vừa CẮT ngành, vừa SỬA tên một số ngành giữ lại. Ghép gần đúng
    # để tách hai nhóm đó ra, nếu không sẽ đếm nhầm ngành đổi tên thành bị cắt.
    doi_ten = _ghep_gan_dung(chua_khop, moi_trong_142)
    for a, b, ty_le in doi_ten:
        a['con_trong_142'] = '~'
        a['stt_142'] = b['stt']
        a['trang_thai'] = 'Giữ lại nhưng ĐỔI TÊN'
        a['ten_moi_142'] = b['nganh_nghe']
        a['do_giong'] = f'{ty_le:.0%}'

    bi_cat = [d for d in d198 if d['trang_thai'] == 'ĐÃ CẮT GIẢM']
    print(f'   -> đổi tên: {len(doi_ten)} | thật sự bị cắt: {len(bi_cat)}')
    if len(bi_cat) != 56:
        print(f'   ! ra {len(bi_cat)} chứ không phải 56 như văn bản nói — '
              f'kiểm sheet "Đổi tên" và "Đã cắt giảm" bằng mắt')

    print('3. Ghi Excel')
    cot = ['stt', 'nganh_nghe', 'trang_thai', 'stt_142', 'ten_moi_142', 'do_giong',
           'nguon']
    df198 = pd.DataFrame(d198)
    for c in ('ten_moi_142', 'do_giong'):
        if c not in df198.columns:
            df198[c] = ''
    df198 = df198[cot].fillna('')

    ghi_excel(FILE_EXCEL, {
        f'{len(dcu)} - Luật ĐT 2020 (cũ)': pd.DataFrame(dcu)[
            ['stt', 'nganh_nghe', 'nguon']],
        '198 - Luật 143.2025': df198,
        '142 - NQ 66.17.2026': pd.DataFrame(d142)[['stt', 'nganh_nghe', 'nguon']],
        'Đã cắt giảm': df198[df198.trang_thai == 'ĐÃ CẮT GIẢM'][
            ['stt', 'nganh_nghe']],
        'Đổi tên': df198[df198.trang_thai == 'Giữ lại nhưng ĐỔI TÊN'][
            ['stt', 'nganh_nghe', 'stt_142', 'ten_moi_142', 'do_giong']],
    }, DO_RONG)


if __name__ == '__main__':
    main()
