# -*- coding: utf-8 -*-
"""Trích các DANH MỤC HÓA CHẤT của Nghị định 24/2026/NĐ-CP ra Excel.

Nguồn: bản Công báo chính thức (file .docx) của
  Nghị định 24/2026/NĐ-CP ngày 17/01/2026 quy định các danh mục hoá chất thuộc
  phạm vi điều chỉnh của Luật Hoá chất số 69/2025/QH15 - hiệu lực từ 17/01/2026.

Bốn phụ lục:
  I   - Hoá chất cơ bản thuộc lĩnh vực công nghiệp hoá chất trọng điểm
  II  - Hoá chất sản xuất, kinh doanh có điều kiện
  III - Hoá chất cần kiểm soát đặc biệt (nhóm 1, nhóm 2)
  IV  - Hoá chất phải xây dựng Kế hoạch phòng ngừa, ứng phó sự cố
        (Bảng A: theo từng chất + ngưỡng khối lượng; Bảng B: theo nhóm nguy hại)

Lưu ý khi bóc tách:
  * Cột STT ở Phụ lục I và II là số tự động của Word -> đọc ra rỗng, phải tự
    đánh lại số theo thứ tự xuất hiện.
  * Trong Phụ lục III và Bảng B của Phụ lục IV có những hàng gộp ô đóng vai trò
    TIÊU ĐỀ NHÓM (A. Các tiền chất công nghiệp, Nhóm 1 (IVB)..., I. Nguy hại sức
    khoẻ...) chứ không phải một hoá chất - được tách sang cột "nhom".

Chạy:  venv\\Scripts\\python.exe danh_muc_hoa_chat.py
"""
from __future__ import annotations

import os
import re

import pandas as pd
from docx import Document
from docx.oxml.ns import qn

from danh_muc_common import (bo_dau, chuan_hoa, chuyen_sang_docx, duyet_khoi,
                             ghi_excel, gom_trung_lien_tiep, o_hang, tai_van_ban)

ND24 = 'https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-24-2026-nd-cp-468796.htm'

THU_MUC = os.path.dirname(os.path.abspath(__file__))
FILE_EXCEL = os.path.join(THU_MUC, 'data', 'danh_muc_hoa_chat_ND24_2026.xlsx')

RE_PHU_LUC = re.compile(r'^Phụ lục\s+([IVX]+)\b', re.IGNORECASE)
RE_MUC = re.compile(r'^((?:\d+(?:\.\d+)?)|(?:[IVX]+))\.\s*(\S.+)$')
RE_LA_MA = re.compile(r'^[IVX]+$')

# tên cột trong văn bản (đã bỏ dấu) -> tên cột chuẩn hoá của mình
NHAN_COT = [
    ('stt', 'stt'),
    # Bảng "Hóa chất Bảng 3" đổi tiêu đề cột giữa chừng thành
    # "Tên hóa chất theo tiếng Anh | Tên hóa chất theo tiếng Việt" -> phải phân
    # biệt hai cột này, nếu không cột tên tiếng Việt sẽ bị bỏ mất.
    ('tieng anh', 'ten_khoa_hoc'),
    ('tieng viet', 'ten_chat'),
    ('iupac', 'ten_khoa_hoc'),
    ('ten khoa hoc', 'ten_khoa_hoc'),
    ('ten chat', 'ten_chat'),
    ('ten hoa chat', 'ten_chat'),
    ('cas', 'ma_cas'),
    ('cong thuc', 'cong_thuc_hoa_hoc'),
    ('nguong', 'nguong_khoi_luong_tan'),
    ('nhom hoa chat', 'nhom_hoa_chat'),
]
COT_RA = ['stt', 'nguon_stt', 'ten_khoa_hoc', 'ten_chat', 'ma_cas', 'ma_cas_tach',
          'cas_bat_thuong', 'cong_thuc_hoa_hoc', 'nhom_hoa_chat',
          'nguong_khoi_luong_tan', 'nhom_lon', 'nhom', 'phu_luc', 'muc',
          'ten_danh_muc']
DO_RONG = {'stt': 6, 'nguon_stt': 11, 'ten_khoa_hoc': 40, 'ten_chat': 34,
           'ma_cas': 15, 'ma_cas_tach': 24, 'cas_bat_thuong': 13,
           'cong_thuc_hoa_hoc': 18, 'nhom_hoa_chat': 42,
           'nguong_khoi_luong_tan': 14, 'nhom_lon': 30, 'nhom': 46, 'phu_luc': 9,
           'muc': 26, 'ten_danh_muc': 46}

RE_CAS = re.compile(r'^\d{2,7}-\d{2}-\d$')
RE_NHOM_LON = re.compile(r'^[A-C]$')          # A, B, C
RE_NHOM_CON = re.compile(r'^\d+[A-Z]\*?$')    # 2A, 2A*, 2B, 3A, 3B (Công ước CWC)


def _ten_cot(text: str) -> str | None:
    t = bo_dau(text)
    for khoa, ten in NHAN_COT:
        if khoa in t:
            return ten
    return None


def _doc_tieu_de_cot(hang) -> dict[int, str] | None:
    """Nhận diện hàng tiêu đề cột và trả về {chỉ số cột: tên cột chuẩn}."""
    o = o_hang(hang)
    if not o or bo_dau(o[0]) not in ('stt', 'tt'):
        return None
    anh_xa = {}
    for i, text in enumerate(o):
        ten = _ten_cot(text)
        if ten and ten not in anh_xa.values():
            anh_xa[i] = ten
    return anh_xa if len(anh_xa) >= 2 else None


def _ghep_nhan(ma: str, ten: str) -> str:
    ma, ten = (ma or '').strip(' .'), (ten or '').strip()
    if not ma or ma == ten:
        return ten or ma
    return f'{ma}. {ten}'


def _la_hang_nhom(o_raw: list[str]) -> tuple[str, str] | None:
    """Hàng gộp ô làm tiêu đề nhóm -> (mã, nhãn nhóm); không phải thì None."""
    con_lai = list(o_raw[1:])
    if con_lai and con_lai[0] and all(x == con_lai[0] for x in con_lai):
        return o_raw[0], _ghep_nhan(o_raw[0], con_lai[0])
    if len(gom_trung_lien_tiep([x for x in o_raw if x])) == 1:
        nhan = chuan_hoa(' '.join(x for x in o_raw if x))
        return ('', nhan)
    # Bảng B: "I | Nguy hại sức khỏe | (trống)"
    if RE_LA_MA.match(o_raw[0] or '') and not (o_raw[-1] or ''):
        giua = [x for x in o_raw[1:] if x]
        if giua:
            return o_raw[0], _ghep_nhan(o_raw[0], giua[0])
    return None


def _tach_cas(ma_cas: str) -> tuple[str, str]:
    """Một ô CAS có thể chứa nhiều mã, hoặc '---' khi chất không có mã CAS.

    Trả về (danh sách mã ngăn bởi '; ', cờ đánh dấu mã sai định dạng).
    Ví dụ mã sai còn nguyên trong bản gốc: Formaldehyde ghi '50-00-00'.
    """
    tokens = [t for t in re.split(r'[\s,;]+', ma_cas or '') if t]
    ma = [t for t in tokens if RE_CAS.match(t)]
    khong_hop_le = [t for t in tokens if not RE_CAS.match(t) and t not in ('-', '--', '---')]
    return '; '.join(ma), ('x' if khong_hop_le else '')


def _so_tu_dong(hang, dem_numid: dict) -> str:
    """Số thứ tự do Word tự đánh trong ô STT.

    Phụ lục I, II, III để ô STT RỖNG vì dùng danh sách tự động của Word — đọc
    text ra là chuỗi trống. Số thật nằm ở `w:numPr` (numId + ilvl); Word hiển
    thị nó bằng cách đếm LIÊN TỤC theo numId, KHÔNG đánh lại ở mỗi nhóm. Mỗi
    bảng dùng một numId riêng (PL I: 1, PL II: 11, PL III: 13 và 17) nên đếm
    theo numId là ra đúng số in trên giấy.
    """
    npr = hang.cells[0]._tc.findall('.//' + qn('w:numPr'))
    if not npr:
        return ''
    nid = npr[0].find(qn('w:numId'))
    khoa = nid.get(qn('w:val')) if nid is not None else '?'
    dem_numid[khoa] = dem_numid.get(khoa, 0) + 1
    return str(dem_numid[khoa])


def _doc_bang(bang, boi_canh: dict, dem_numid: dict) -> tuple[list[dict], dict]:
    anh_xa: dict[int, str] = {}
    nhom_lon, nhom = '', ''
    dong: list[dict] = []
    thong_ke = {'tieu_de': 0, 'nhom': 0, 'du_lieu': 0, 'trong': 0}

    for hang in bang.rows:
        o_raw = o_hang(hang)
        if not any(o_raw):
            thong_ke['trong'] += 1
            continue
        if (td := _doc_tieu_de_cot(hang)) is not None:
            anh_xa = td                       # gặp lại tiêu đề khi bảng sang trang
            thong_ke['tieu_de'] += 1
            continue
        if not anh_xa:
            thong_ke['trong'] += 1
            continue
        if (nhan := _la_hang_nhom(o_raw)) is not None:
            ma, ten_nhom = nhan
            if RE_NHOM_LON.match(ma or ''):   # A / B / C: nhóm cấp trên
                nhom_lon, nhom = ten_nhom, ''
            else:
                nhom = ten_nhom
            thong_ke['nhom'] += 1
            continue

        ban_ghi = {ten: o_raw[i] if i < len(o_raw) else ''
                   for i, ten in anh_xa.items()}
        if not any(v for k, v in ban_ghi.items() if k != 'stt'):
            thong_ke['trong'] += 1
            continue

        stt_goc = re.sub(r'\.$', '', ban_ghi.get('stt', '')).strip()
        # "2A | Toxic Chemicals | Các hóa chất độc | (trống) | (trống)" là tiêu đề
        # nhóm con của Công ước CWC, không phải một hoá chất.
        if (RE_NHOM_CON.match(stt_goc) and not ban_ghi.get('ma_cas')
                and not ban_ghi.get('cong_thuc_hoa_hoc')):
            nhom = _ghep_nhan(stt_goc, ban_ghi.get('ten_chat')
                              or ban_ghi.get('ten_khoa_hoc') or '')
            thong_ke['nhom'] += 1
            continue

        # STT: ưu tiên số ghi thẳng trong ô (Phụ lục IV), nếu ô rỗng thì lấy số
        # tự động của Word (Phụ lục I, II, III) -> khớp đúng bản in.
        so_word = '' if stt_goc else _so_tu_dong(hang, dem_numid)
        ban_ghi['stt'] = stt_goc or so_word
        ban_ghi['nguon_stt'] = ('văn bản' if stt_goc else
                                'số tự động Word' if so_word else 'không có')
        ban_ghi['ma_cas_tach'], ban_ghi['cas_bat_thuong'] = _tach_cas(
            ban_ghi.get('ma_cas', ''))
        ban_ghi['nhom_lon'] = nhom_lon
        ban_ghi['nhom'] = nhom
        ban_ghi.update(boi_canh)
        dong.append(ban_ghi)
        thong_ke['du_lieu'] += 1
    return dong, thong_ke


def trich(duong_dan_docx: str) -> dict[str, list[dict]]:
    doc = Document(duong_dan_docx)
    bang_theo_muc: dict[str, list[dict]] = {}
    phu_luc, ten_danh_muc, muc = '', '', ''
    dang_gom_ten = False
    # bộ đếm số tự động của Word, dùng chung cho CẢ tài liệu vì Word đếm liên
    # tục theo numId — mỗi bảng một numId nên không lẫn nhau
    dem_numid: dict[str, int] = {}

    for khoi in duyet_khoi(doc):
        if hasattr(khoi, 'rows'):
            if not phu_luc:
                continue
            boi_canh = {'phu_luc': phu_luc, 'muc': muc, 'ten_danh_muc': ten_danh_muc}
            khoa = f'PL {phu_luc}' + (f' - {muc}' if muc else '')
            dong, thong_ke = _doc_bang(khoi, boi_canh, dem_numid)
            bang_theo_muc.setdefault(khoa, []).extend(dong)
            tong = sum(thong_ke.values())
            if tong != len(khoi.rows):        # không hàng nào bị bỏ sót lặng lẽ
                raise AssertionError(f'{khoa}: đọc {tong}/{len(khoi.rows)} hàng '
                                     f'({thong_ke})')
            print(f'   {khoa}: {thong_ke["du_lieu"]} chất '
                  f'(+{thong_ke["nhom"]} hàng tiêu đề nhóm, '
                  f'{thong_ke["tieu_de"]} hàng tiêu đề cột)')
            continue

        text = chuan_hoa(khoi.text)
        if not text:
            continue
        if (m := RE_PHU_LUC.match(text)):
            phu_luc, ten_danh_muc, muc = m.group(1), '', ''
            dang_gom_ten = True
            continue
        if dang_gom_ten:
            phan = text.split('(Kèm theo')[0].strip()
            if phan and phan == phan.upper():
                ten_danh_muc = (ten_danh_muc + ' ' + phan).strip()
            if '(Kèm theo' in text or 'của Chính phủ' in text:
                dang_gom_ten = False
            continue
        if (m := RE_MUC.match(text)) and len(text) < 90:
            muc = f'{m.group(1)}. {m.group(2)}'
    return bang_theo_muc


def _ten_sheet(khoa: str) -> str:
    ten = (khoa.replace('Chất sản xuất, kinh doanh có điều kiện', 'SXKD có điều kiện')
                .replace('Chất cần kiểm soát đặc biệt', 'Kiểm soát đặc biệt'))
    ten = re.sub(r'\b(\d+(?:\.\d+)?|[IVX]+)\.\s*', '', ten.split(' - ', 1)[0]) + \
        (' - ' + re.sub(r'^(\d+(?:\.\d+)?|[IVX]+)\.\s*', '', ten.split(' - ', 1)[1])
         if ' - ' in ten else '')
    return ten[:31]


def main() -> None:
    print('1. Tải bản Công báo')
    tep = chuyen_sang_docx(tai_van_ban(ND24, 'ND_24_2026'))

    print('2. Trích các phụ lục')
    bang_theo_muc = trich(tep)

    cac_sheet: dict[str, pd.DataFrame] = {}
    tat_ca: list[dict] = []
    for khoa, dong in bang_theo_muc.items():
        if not dong:
            continue
        df = pd.DataFrame(dong)
        for c in COT_RA:
            if c not in df.columns:
                df[c] = ''
        df = df[COT_RA].loc[:, lambda d: (d != '').any()]   # bỏ cột rỗng của sheet
        cac_sheet[_ten_sheet(khoa)] = df
        tat_ca.extend(dong)

    df_all = pd.DataFrame(tat_ca)
    for c in COT_RA:
        if c not in df_all.columns:
            df_all[c] = ''
    df_all = df_all[COT_RA].fillna('')
    cac_sheet['Tất cả'] = df_all

    co_cas = (df_all['ma_cas_tach'] != '').sum()
    print(f'   TỔNG: {len(df_all)} dòng | {co_cas} dòng có mã CAS hợp lệ | '
          f'{(df_all["cas_bat_thuong"] == "x").sum()} dòng CAS bất thường | '
          f'{(df_all["nguon_stt"] == "tự đánh").sum()} dòng STT do script đánh lại')

    print('3. Ghi Excel')
    ghi_excel(FILE_EXCEL, cac_sheet, DO_RONG)
    df_all.to_csv(
        os.path.join(THU_MUC, 'data', 'danh_muc_hoa_chat_ND24_2026.csv'),
        index=False, encoding='utf-8-sig')


if __name__ == '__main__':
    main()
