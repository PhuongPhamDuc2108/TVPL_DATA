# -*- coding: utf-8 -*-
"""
Nạp 2 danh mục (Excel) vào bảng `danh_muc` của DB "questions".

  * data/danh_muc_nghe_nndhnh.xlsx        - TT 11/2020 + TT 19/2023
  * data/danh_muc_hoa_chat_ND24_2026.xlsx - NĐ 24/2026/NĐ-CP

Văn bản ban hành được nạp vào chính bảng `van_ban` sẵn có, dùng ĐÚNG quy ước
khoá `sh:<số hiệu chuẩn hoá>` của nap_postgres.py -> câu hỏi test trích dẫn
TT 11/2020 và danh mục của TT 11/2020 dùng chung một van_ban_id.

3 chế độ, giống nap_postgres.py:
  --dry-run                    : chỉ đọc Excel, in thống kê (KHÔNG cần DB).
  --emit-sql nap_danh_muc.sql  : sinh file SQL để chạy trong DataGrip.
  --load                       : kết nối và nạp trực tiếp (idempotent).

KẾT NỐI: mặc định dùng cùng DSN với app.py / xuat_bang.py / don_van_ban.py
  postgresql://questions:questions@172.16.10.71:5433/questions   (cổng 5433)
Ghi đè bằng biến môi trường DATABASE_URL, hoặc tham số --dsn.
"""

import argparse
import hashlib
import json
import os
import re
import sys

import pandas as pd

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DSN = (os.environ.get('DATABASE_URL')
       or 'postgresql://questions:questions@172.16.10.71:5433/questions')

THU_MUC = os.path.dirname(os.path.abspath(__file__))
_D = os.path.join(THU_MUC, 'data')
XL_NGHE = os.path.join(_D, 'danh_muc_nghe_nndhnh.xlsx')
XL_HOA_CHAT = os.path.join(_D, 'danh_muc_hoa_chat_ND24_2026.xlsx')
XL_NGANH_NGHE = os.path.join(_D, 'danh_muc_nganh_nghe_kdcdk.xlsx')
XL_PHE_LIEU = os.path.join(_D, 'danh_muc_phe_lieu.xlsx')
XL_BMNN = os.path.join(_D, 'danh_muc_bi_mat_nha_nuoc.xlsx')

TEN_NGHE = ('Danh mục nghề, công việc nặng nhọc, độc hại, nguy hiểm và nghề, '
            'công việc đặc biệt nặng nhọc, độc hại, nguy hiểm')
TEN_HOA_CHAT = ('Các danh mục hoá chất thuộc phạm vi điều chỉnh của Luật Hoá chất')
TEN_NGANH_NGHE = 'Danh mục ngành, nghề đầu tư kinh doanh có điều kiện'
TEN_PHE_LIEU_NK = 'Danh mục phế liệu được phép nhập khẩu làm nguyên liệu sản xuất'
TEN_PHE_LIEU_TN = ('Danh mục phế liệu và hàng hóa đã qua sử dụng tạm ngừng kinh '
                   'doanh tạm nhập, tái xuất, chuyển khẩu')
TEN_BMNN = 'Danh mục bí mật nhà nước'

# Văn bản ban hành -> nạp vào bảng van_ban (khoá gộp trùng giống nap_postgres.py)
VAN_BAN = {
    '11/2020/TT-BLĐTBXH': (
        'Thông tư 11/2020/TT-BLĐTBXH ban hành Danh mục nghề, công việc nặng nhọc, '
        'độc hại, nguy hiểm và nghề, công việc đặc biệt nặng nhọc, độc hại, nguy hiểm',
        'Thông tư',
        'https://congbao.chinhphu.vn/van-ban/thong-tu-so-11-2020-tt-bldtbxh-33183.htm'),
    '19/2023/TT-BLĐTBXH': (
        'Thông tư 19/2023/TT-BLĐTBXH ban hành bổ sung Danh mục nghề, công việc nặng '
        'nhọc, độc hại, nguy hiểm và nghề, công việc đặc biệt nặng nhọc, độc hại, '
        'nguy hiểm',
        'Thông tư',
        'https://congbao.chinhphu.vn/van-ban/thong-tu-so-19-2023-tt-bldtbxh-41242/48815.htm'),
    '24/2026/NĐ-CP': (
        'Nghị định 24/2026/NĐ-CP quy định các danh mục hoá chất thuộc phạm vi điều '
        'chỉnh của Luật Hoá chất',
        'Nghị định',
        'https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-24-2026-nd-cp-468796.htm'),
    '28/2025/TT-BNV': (
        'Thông tư 28/2025/TT-BNV ban hành Danh mục nghề, công việc nặng nhọc, độc '
        'hại, nguy hiểm và nghề, công việc đặc biệt nặng nhọc, độc hại, nguy hiểm '
        'trong Quân đội',
        'Thông tư',
        'https://luatvietnam.vn/lao-dong/thong-tu-28-2025-tt-bnv-danh-muc-nghe-nang-'
        'nhoc-doc-hai-trong-quan-doi-430915-d1.html'),
    '61/2020/QH14': (
        'Luật Đầu tư 2020', 'Luật', ''),
    '143/2025/QH15': (
        'Luật Đầu tư 2025', 'Luật', ''),
    '66.17/2026/NQ-CP': (
        'Nghị quyết 66.17/2026/NQ-CP cắt giảm, sửa đổi ngành, nghề đầu tư kinh '
        'doanh có điều kiện quy định tại Phụ lục IV của Luật Đầu tư số 143/2025/QH15',
        'Nghị quyết', ''),
    '13/2023/QĐ-TTg': (
        'Quyết định 13/2023/QĐ-TTg ban hành Danh mục phế liệu được phép nhập khẩu '
        'từ nước ngoài làm nguyên liệu sản xuất',
        'Quyết định',
        'https://vanban.chinhphu.vn/?pageid=27160&docid=207922'),
    '41/2026/TT-BCT': (
        'Thông tư 41/2026/TT-BCT quy định Danh mục phế liệu và Danh mục hàng hóa đã '
        'qua sử dụng tạm ngừng kinh doanh tạm nhập, tái xuất, chuyển khẩu',
        'Thông tư',
        'https://luatvietnam.vn/xuat-nhap-khau/thong-tu-41-2026-tt-bct-danh-muc-phe-'
        'lieu-va-hang-hoa-tam-ngung-kinh-doanh-441401-d1.html'),
}

# Sai sót trong CHÍNH bản gốc NĐ 24/2026: mã CAS không qua được chữ số kiểm tra.
# Cột `ma` lưu mã CAS THẬT (đã đối chiếu nguồn ngoài); nguyên văn của văn bản
# luôn được giữ ở thuoc_tinh.ma_cas_goc nên không mất dấu vết.
SUA_CAS = {
    '50-00-00': '50-00-0',      # PL IV - Formaldehit (thừa một số 0)
    '10037-74-3': '10137-74-3',  # PL II - Canxi clorat (nj.gov RTK, ChemicalBook)
    '7746-08-4': '7446-08-4',   # PL II - Selen dioxit (Sigma-Aldrich, TCI)
}
# 10118-77-6 (PL IV, 1-Propen-2-clo-1,3-diol diaxetat) cũng sai chữ số kiểm tra
# nhưng KHÔNG tra được mã đúng từ nguồn nào -> không đoán, để nguyên là mã hỏng:
# nằm ở thuoc_tinh.ma_cas_khong_hop_le, không vào cột `ma`.

RE_CAS = re.compile(r'^\d{2,7}-\d{2}-\d$')


# ------------------------------------------------------------------ mã CAS

def cas_hop_le(ma: str) -> bool:
    """Kiểm tra mã CAS bằng chữ số kiểm tra chính thức của CAS Registry.

    Chữ số cuối = (tổng các chữ số còn lại, đếm từ phải sang, nhân với 1,2,3...)
    chia lấy dư 10.  Ví dụ 7732-18-5 (nước): 8*1+1*2+2*3+3*4+7*5+7*6 = 105 -> 5.
    """
    if not RE_CAS.match(ma or ''):
        return False
    than, giua, kiem_tra = ma.split('-')
    chu_so = (than + giua)[::-1]
    tong = sum(int(c) * (i + 1) for i, c in enumerate(chu_so))
    return tong % 10 == int(kiem_tra)


def tach_cas(o_cas: str) -> tuple[list, list, list]:
    """Ô CAS -> (mã hợp lệ, mã đã sửa theo SUA_CAS, token không phải mã CAS)."""
    tokens = [t for t in re.split(r'[\s,;]+', str(o_cas or '')) if t]
    hop_le, da_sua, bo = [], [], []
    for t in tokens:
        if t in ('-', '--', '---'):
            continue
        if cas_hop_le(t):
            hop_le.append(t)
        elif t in SUA_CAS:
            hop_le.append(SUA_CAS[t])
            da_sua.append(f'{t} -> {SUA_CAS[t]}')
        else:
            bo.append(t)
    return hop_le, da_sua, bo


# --------------------------------------------------------------- chuẩn hoá

def khoa_van_ban(so_hieu: str) -> str:
    """Cùng quy ước với nap_postgres.doc_key() để gộp trùng với văn bản đã có."""
    return 'sh:' + re.sub(r'\s+', '', so_hieu.lower())


def bam(*phan) -> str:
    return hashlib.md5('|'.join(str(p or '') for p in phan).encode('utf-8')).hexdigest()


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    return str(v).strip()


# ------------------------------------------------------------------- đọc

def doc_nghe() -> list[dict]:
    df = pd.read_excel(XL_NGHE, sheet_name='Danh mục nghề', dtype=str).fillna('')
    ban_ghi = []
    for r in df.to_dict('records'):
        so_hieu = _s(r['van_ban']).replace('TT ', '')
        ban_ghi.append({
            'ma_danh_muc': 'nghe_nndhnh',
            'ten_danh_muc': TEN_NGHE,
            'so_hieu': so_hieu,
            'phan_muc': f"{_s(r['so_linh_vuc'])}. {_s(r['linh_vuc'])}",
            'nhom_cha': _s(r['dieu_kien_lao_dong']),
            'nhom_con': _s(r['phan_loai']),
            'stt': _s(r['stt']),
            'ten': _s(r['ten_nghe_cong_viec']),
            'ten_khac': '',
            'ma': [],
            'mo_ta': _s(r['dac_diem_dieu_kien_lao_dong']),
            'thuoc_tinh': {'id_excel': _s(r['id'])},
        })
    return ban_ghi


def doc_hoa_chat() -> list[dict]:
    df = pd.read_excel(XL_HOA_CHAT, sheet_name='Tất cả', dtype=str).fillna('')
    ban_ghi, thong_ke_cas = [], {'da_sua': [], 'bo': []}
    for r in df.to_dict('records'):
        hop_le, da_sua, bo = tach_cas(r.get('ma_cas'))
        thong_ke_cas['da_sua'] += da_sua
        thong_ke_cas['bo'] += bo

        # Bảng B của Phụ lục IV phân loại theo NHÓM NGUY HẠI, không có tên chất
        # -> lấy nhóm nguy hại làm `ten` để cột này không bao giờ rỗng.
        ten = _s(r['ten_chat']) or _s(r['nhom_hoa_chat']) or _s(r['ten_khoa_hoc'])
        phan_muc = 'Phụ lục ' + _s(r['phu_luc'])
        if _s(r['muc']):
            phan_muc += ' - ' + _s(r['muc'])

        thuoc_tinh = {k: _s(r[k]) for k in
                      ('cong_thuc_hoa_hoc', 'nguong_khoi_luong_tan', 'nhom_hoa_chat',
                       'nguon_stt') if _s(r[k])}
        if _s(r['ma_cas']):
            thuoc_tinh['ma_cas_goc'] = _s(r['ma_cas'])
        if da_sua:
            thuoc_tinh['ma_cas_da_sua'] = '; '.join(da_sua)
        if bo:
            thuoc_tinh['ma_cas_khong_hop_le'] = '; '.join(bo)

        ban_ghi.append({
            'ma_danh_muc': 'hoa_chat_nd24',
            'ten_danh_muc': TEN_HOA_CHAT,
            'so_hieu': '24/2026/NĐ-CP',
            'phan_muc': phan_muc,
            'nhom_cha': _s(r['nhom_lon']),
            'nhom_con': _s(r['nhom']),
            'stt': _s(r['stt']),
            'ten': ten,
            'ten_khac': _s(r['ten_khoa_hoc']) if _s(r['ten_chat']) else '',
            'ma': hop_le,
            'mo_ta': '',
            'thuoc_tinh': thuoc_tinh,
        })
    return ban_ghi, thong_ke_cas


def doc_nganh_nghe() -> list[dict]:
    """Ba bản danh mục ngành nghề. Cùng một tên ngành có ở cả ba bản nhưng khác
    `so_hieu` nên content_hash không đụng nhau."""
    ban = [('230 - Luật ĐT 2020 (cũ)', '61/2020/QH14', 'Phụ lục IV (bản hợp nhất)'),
           ('198 - Luật 143.2025', '143/2025/QH15', 'Phụ lục IV'),
           ('142 - NQ 66.17.2026', '66.17/2026/NQ-CP', 'Phụ lục')]
    ket_qua = []
    for sheet, so_hieu, phan_muc in ban:
        df = pd.read_excel(XL_NGANH_NGHE, sheet_name=sheet, dtype=str).fillna('')
        for r in df.to_dict('records'):
            thuoc_tinh = {k: _s(r[k]) for k in
                          ('trang_thai', 'stt_142', 'ten_moi_142') if _s(r.get(k))}
            ket_qua.append({
                'ma_danh_muc': 'nganh_nghe_kdcdk', 'ten_danh_muc': TEN_NGANH_NGHE,
                'so_hieu': so_hieu, 'phan_muc': phan_muc,
                'nhom_cha': _s(r.get('trang_thai')), 'nhom_con': '',
                'stt': _s(r['stt']), 'ten': _s(r['nganh_nghe']), 'ten_khac': '',
                'ma': [], 'mo_ta': '', 'thuoc_tinh': thuoc_tinh})
    return ket_qua


def doc_phe_lieu() -> list[dict]:
    """Hai danh mục phế liệu khác nhau -> hai mã danh mục riêng."""
    df = pd.read_excel(XL_PHE_LIEU, sheet_name='Tất cả', dtype=str).fillna('')
    ket_qua = []
    for r in df.to_dict('records'):
        la_nk = '13/2023' in _s(r['van_ban'])
        ma_hs = _s(r['ma_hs'])
        ket_qua.append({
            'ma_danh_muc': 'phe_lieu_duoc_nk' if la_nk else 'phe_lieu_tam_ngung',
            'ten_danh_muc': TEN_PHE_LIEU_NK if la_nk else TEN_PHE_LIEU_TN,
            'so_hieu': '13/2023/QĐ-TTg' if la_nk else '41/2026/TT-BCT',
            'phan_muc': _s(r['phu_luc']), 'nhom_cha': _s(r['nhom']),
            'nhom_con': _s(r.get('muc_cha')), 'stt': _s(r['stt']),
            'ten': _s(r['mo_ta']), 'ten_khac': '',
            'ma': [ma_hs] if ma_hs else [], 'mo_ta': '',
            'thuoc_tinh': {'ma_hs': ma_hs} if ma_hs else {}})
    return ket_qua


def doc_bmnn() -> tuple[list[dict], list[tuple]]:
    """Mỗi khoản/điểm là một mục. Trả thêm danh sách 31 văn bản để nạp van_ban."""
    vb = pd.read_excel(XL_BMNN, sheet_name='Văn bản', dtype=str).fillna('')
    van_ban = [(_s(r['so_hieu']),
                f'Quyết định {_s(r["so_hieu"])} ban hành Danh mục bí mật nhà nước '
                f'lĩnh vực {_s(r["linh_vuc"])}',
                'Quyết định', _s(r.get('nguon_toan_van')))
               for r in vb.to_dict('records')]

    kh = pd.read_excel(XL_BMNN, sheet_name='Khoản', dtype=str).fillna('')
    ket_qua = []
    for r in kh.to_dict('records'):
        diem = _s(r['diem'])
        ket_qua.append({
            'ma_danh_muc': 'bi_mat_nha_nuoc', 'ten_danh_muc': TEN_BMNN,
            'so_hieu': _s(r['so_hieu']), 'phan_muc': _s(r['linh_vuc']),
            'nhom_cha': f'Độ {_s(r["do_mat"])}', 'nhom_con': '',
            'stt': _s(r['so_khoan']) + (f'.{diem}' if diem else ''),
            'ten': _s(r['noi_dung']), 'ten_khac': '', 'ma': [], 'mo_ta': '',
            'thuoc_tinh': {'do_mat': _s(r['do_mat']), 'khoan': _s(r['so_khoan']),
                           **({'diem': diem} if diem else {})}})
    return ket_qua, van_ban


def build() -> tuple[list[dict], dict]:
    ban_ghi = doc_nghe()
    hoa_chat, thong_ke_cas = doc_hoa_chat()
    ban_ghi += hoa_chat
    ban_ghi += doc_nganh_nghe()
    ban_ghi += doc_phe_lieu()
    bmnn, vb_bmnn = doc_bmnn()
    ban_ghi += bmnn
    for so_hieu, ten, loai, link in vb_bmnn:     # 31 QĐ-TTg -> bảng van_ban
        VAN_BAN.setdefault(so_hieu, (ten, loai, link))
    for b in ban_ghi:
        b['content_hash'] = bam(b['ma_danh_muc'], b['so_hieu'], b['phan_muc'],
                                b['nhom_cha'], b['nhom_con'], b['stt'], b['ten'])
    return ban_ghi, thong_ke_cas


# --------------------------------------------------------------- thống kê

def thong_ke(ban_ghi: list[dict], cas: dict) -> None:
    df = pd.DataFrame(ban_ghi)
    print(f'\nTỔNG: {len(df)} mục')
    print(df.groupby(['ma_danh_muc', 'so_hieu']).size().to_string())
    # cột `ma` chứa mã CAS (hóa chất) HOẶC mã HS (phế liệu) - đếm tách ra
    cas_ = sum(1 for b in ban_ghi if b['ma'] and b['ma_danh_muc'] == 'hoa_chat_nd24')
    hs_ = sum(1 for b in ban_ghi if b['ma'] and b['ma_danh_muc'].startswith('phe_lieu'))
    print(f'\nMục có mã CAS hợp lệ    : {cas_}')
    print(f'Mục có nhiều mã CAS     : {sum(1 for b in ban_ghi if len(b["ma"]) > 1)}')
    print(f'Mục có mã HS            : {hs_} '
          f'({sum(1 for b in ban_ghi if not b["ma"] and b["ma_danh_muc"].startswith("phe_lieu"))}'
          f' dòng phân nhóm HS không có mã, đúng như bản gốc)')
    if cas['da_sua']:
        print(f'Mã CAS sửa theo SUA_CAS : {sorted(set(cas["da_sua"]))}')
    if cas['bo']:
        print(f'Token KHÔNG phải mã CAS (giữ trong thuoc_tinh, không vào cột ma): '
              f'{len(cas["bo"])} -> {sorted(set(cas["bo"]))[:5]}')
    trung = len(df) - df['content_hash'].nunique()
    print(f'content_hash trùng nhau: {trung}')
    if trung:
        d = df[df.duplicated('content_hash', keep=False)].sort_values('content_hash')
        print(d[['ma_danh_muc', 'phan_muc', 'nhom_con', 'stt', 'ten']]
              .head(10).to_string())
    rong = df[df['ten'].str.strip() == '']
    print(f'Mục có `ten` rỗng: {len(rong)}')


# ------------------------------------------------------- nạp trực tiếp

def load_db(ban_ghi: list[dict], args) -> None:
    import psycopg2
    from psycopg2.extras import Json, execute_values

    conn = psycopg2.connect(args.dsn or DSN)
    conn.autocommit = False
    with conn, conn.cursor() as cur:
        if args.schema_file:
            cur.execute(open(args.schema_file, encoding='utf-8').read())
        if args.reset:
            cur.execute('TRUNCATE danh_muc RESTART IDENTITY')

        # 1) văn bản ban hành -> gộp vào bảng van_ban sẵn có
        execute_values(cur, """
            INSERT INTO van_ban(khoa, so_hieu, ten, loai, link) VALUES %s
            ON CONFLICT(khoa) DO UPDATE SET
                so_hieu = coalesce(van_ban.so_hieu, EXCLUDED.so_hieu),
                link    = coalesce(van_ban.link,    EXCLUDED.link)
        """, [(khoa_van_ban(sh), sh, ten, loai, link)
              for sh, (ten, loai, link) in VAN_BAN.items()])

        cur.execute('SELECT khoa, van_ban_id FROM van_ban WHERE khoa = ANY(%s)',
                    ([khoa_van_ban(sh) for sh in VAN_BAN],))
        id_van_ban = dict(cur.fetchall())

        # 2) các mục của danh mục
        execute_values(cur, """
            INSERT INTO danh_muc(ma_danh_muc, ten_danh_muc, van_ban_id, so_hieu,
                                 phan_muc, nhom_cha, nhom_con, stt, ten, ten_khac,
                                 ma, mo_ta, thuoc_tinh, content_hash) VALUES %s
            ON CONFLICT(content_hash) DO NOTHING
        """, [(b['ma_danh_muc'], b['ten_danh_muc'],
               id_van_ban.get(khoa_van_ban(b['so_hieu'])), b['so_hieu'],
               b['phan_muc'], b['nhom_cha'], b['nhom_con'], b['stt'], b['ten'],
               b['ten_khac'] or None, b['ma'], b['mo_ta'] or None,
               Json(b['thuoc_tinh']), b['content_hash']) for b in ban_ghi],
            page_size=500)

        cur.execute("""SELECT ma_danh_muc, so_hieu, count(*),
                              count(*) FILTER (WHERE van_ban_id IS NULL)
                       FROM danh_muc GROUP BY 1, 2 ORDER BY 1, 2""")
        print('\nTrong DB sau khi nạp:')
        for ma, sh, n, thieu_vb in cur.fetchall():
            print(f'  {ma:16} {sh:22} {n:5} mục'
                  + (f'  ⚠ {thieu_vb} mục chưa nối được văn bản' if thieu_vb else ''))
    conn.close()


# -------------------------------------------------------------- sinh SQL

def q(s):
    if s is None or s == '':
        return 'NULL'
    return "'" + str(s).replace("'", "''") + "'"


def mang_sql(xs: list) -> str:
    if not xs:
        return "'{}'"
    return "ARRAY[" + ','.join(q(x) for x in xs) + "]::text[]"


def emit_sql(ban_ghi: list[dict], out: str, with_schema: bool) -> None:
    L = []
    if with_schema:
        L.append(open(os.path.join(THU_MUC, 'schema_danh_muc.sql'),
                      encoding='utf-8').read())
    L.append('BEGIN;')
    for sh, (ten, loai, link) in VAN_BAN.items():
        L.append(f'INSERT INTO van_ban(khoa,so_hieu,ten,loai,link) VALUES'
                 f'({q(khoa_van_ban(sh))},{q(sh)},{q(ten)},{q(loai)},{q(link)}) '
                 f'ON CONFLICT(khoa) DO NOTHING;')
    for b in ban_ghi:
        vb = (f"(SELECT van_ban_id FROM van_ban WHERE khoa="
              f"{q(khoa_van_ban(b['so_hieu']))})")
        L.append(
            'INSERT INTO danh_muc(ma_danh_muc,ten_danh_muc,van_ban_id,so_hieu,'
            'phan_muc,nhom_cha,nhom_con,stt,ten,ten_khac,ma,mo_ta,thuoc_tinh,'
            f"content_hash) VALUES({q(b['ma_danh_muc'])},{q(b['ten_danh_muc'])},"
            f"{vb},{q(b['so_hieu'])},{q(b['phan_muc'])},{q(b['nhom_cha'])},"
            f"{q(b['nhom_con'])},{q(b['stt'])},{q(b['ten'])},{q(b['ten_khac'])},"
            f"{mang_sql(b['ma'])},{q(b['mo_ta'])},"
            f"{q(json.dumps(b['thuoc_tinh'], ensure_ascii=False))}::jsonb,"
            f"{q(b['content_hash'])}) ON CONFLICT(content_hash) DO NOTHING;")
    L.append('COMMIT;')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print(f'\n-> {out}  ({len(L)} câu lệnh, {os.path.getsize(out)/1024:.0f} KB)')


def loc_danh_muc(ban_ghi: list[dict], chi: str | None,
                 bo_qua: str | None) -> list[dict]:
    """Lọc theo mã danh mục để nạp từng phần. Khớp theo TIỀN TỐ nên `phe_lieu`
    bắt cả `phe_lieu_duoc_nk` lẫn `phe_lieu_tam_ngung`."""
    def khop(ma: str, danh_sach: str) -> bool:
        return any(ma.startswith(x.strip()) for x in danh_sach.split(',') if x.strip())

    truoc = len(ban_ghi)
    if chi:
        ban_ghi = [b for b in ban_ghi if khop(b['ma_danh_muc'], chi)]
    if bo_qua:
        ban_ghi = [b for b in ban_ghi if not khop(b['ma_danh_muc'], bo_qua)]
    if chi or bo_qua:
        con = sorted({b['ma_danh_muc'] for b in ban_ghi})
        print(f'Lọc danh mục: giữ {len(ban_ghi)}/{truoc} mục -> {con}')
        if not ban_ghi:
            raise SystemExit('Bộ lọc không khớp danh mục nào, dừng.')
        # `van_ban` là bảng DÙNG CHUNG với cau_hoi -> chỉ nạp văn bản của những
        # danh mục thực sự được giữ, tránh để lại văn bản mồ côi.
        dung = {b['so_hieu'] for b in ban_ghi}
        for sh in [k for k in VAN_BAN if k not in dung]:
            VAN_BAN.pop(sh)
        print(f'   kèm {len(VAN_BAN)} văn bản ban hành')
    return ban_ghi


def main() -> None:
    ap = argparse.ArgumentParser(description='Nạp danh mục (Excel) vào bảng danh_muc.')
    ap.add_argument('--dry-run', action='store_true', help='Chỉ in thống kê, không nạp')
    ap.add_argument('--emit-sql', metavar='FILE', help='Sinh file SQL (không cần DB)')
    ap.add_argument('--with-schema', action='store_true',
                    help='Kèm schema_danh_muc.sql vào đầu file SQL sinh ra')
    ap.add_argument('--schema-file', metavar='FILE',
                    help='Chạy file schema trước khi nạp trực tiếp')
    ap.add_argument('--reset', action='store_true',
                    help='TRUNCATE bảng danh_muc rồi nạp lại từ đầu')
    ap.add_argument('--load', action='store_true', help='Nạp trực tiếp vào DB')
    ap.add_argument('--dsn', help=f'Chuỗi kết nối; mặc định {DSN}')
    ap.add_argument('--chi', metavar='MA', help='CHỈ nạp các danh mục này '
                    '(ngăn bởi dấu phẩy, khớp theo tiền tố mã danh mục)')
    ap.add_argument('--bo-qua', metavar='MA', dest='bo_qua',
                    help='BỎ QUA các danh mục này (ngăn bởi dấu phẩy)')
    args = ap.parse_args()

    ban_ghi, cas = build()
    ban_ghi = loc_danh_muc(ban_ghi, args.chi, args.bo_qua)
    thong_ke(ban_ghi, cas)

    if args.emit_sql:
        emit_sql(ban_ghi, args.emit_sql, args.with_schema)
    if args.load:
        load_db(ban_ghi, args)
    if not args.emit_sql and not args.load:
        print('\n(dry-run: chưa ghi gì. Dùng --emit-sql FILE hoặc --load để nạp.)')


if __name__ == '__main__':
    main()
