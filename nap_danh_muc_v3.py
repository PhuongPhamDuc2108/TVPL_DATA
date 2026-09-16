# -*- coding: utf-8 -*-
"""
Nạp 2 danh mục từ Excel vào cấu trúc 2 bảng, phân cấp bằng MẢNG ĐƯỜNG DẪN.

    danh_muc            2 dòng  — tên, mô tả, văn bản (text[]), nhãn từng tầng
         └──< danh_muc_chi_tiet  — khóa ngoại danh_muc_id, phân cấp ở `duong_dan`

Khác bản v2: ba cột phan_muc / nhom / nhom_con gộp thành `duong_dan text[]`, vì
bản gốc hai văn bản có số tầng khác nhau (nghề 2 tầng, hóa chất 4 tầng).

Nguồn:
  * data/danh_muc_nghe_nndhnh.xlsx        - TT 11/2020 + TT 19/2023
    (Excel có cả TT 28/2025 Quân đội nhưng KHÔNG nạp, xem DANH_MUC dưới)
  * data/danh_muc_hoa_chat_ND24_2026.xlsx - NĐ 24/2026/NĐ-CP

3 chế độ:
  --dry-run                       : chỉ đọc Excel, in thống kê (KHÔNG cần DB).
  --emit-sql nap_danh_muc_v3.sql  : sinh file SQL để chạy trong DataGrip.
  --load                          : kết nối và nạp trực tiếp (idempotent).

KẾT NỐI: mặc định cùng DSN với app.py
  postgresql://questions:questions@172.16.10.71:5433/questions   (cổng 5433)
Ghi đè bằng biến môi trường DATABASE_URL, hoặc tham số --dsn.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

import pandas as pd

for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DSN = (os.environ.get('DATABASE_URL')
       or 'postgresql://questions:questions@172.16.10.71:5433/questions')
THU_MUC = os.path.dirname(os.path.abspath(__file__))
_D = os.path.join(THU_MUC, 'data')
XL_NGHE = os.path.join(_D, 'danh_muc_nghe_nndhnh.xlsx')
XL_HOA_CHAT = os.path.join(_D, 'danh_muc_hoa_chat_ND24_2026.xlsx')

# ---------------------------------------------------------------------------
#  Nội dung 2 dòng của bảng `danh_muc`
# ---------------------------------------------------------------------------
DANH_MUC = {
    'nghe_nndhnh': {
        'ten': 'Danh mục nghề, công việc nặng nhọc, độc hại, nguy hiểm và nghề, '
               'công việc đặc biệt nặng nhọc, độc hại, nguy hiểm',
        'ten_ngan': 'Nghề nặng nhọc, độc hại',
        'linh_vuc': 'Lao động',
        'co_quan': 'Bộ Nội vụ (trước là Bộ Lao động - Thương binh và Xã hội)',
        'can_cu': 'Luật An toàn, vệ sinh lao động 2015',
        # Chỉ nạp 2 thông tư này. TT 28/2025/TT-BNV (danh mục riêng cho Quân
        # đội, 537 nghề / 17 lĩnh vực) vẫn có đủ trong Excel nhưng KHÔNG nạp:
        # nó đánh số La Mã lĩnh vực từ I lại, trùng với hai thông tư kia nên
        # gộp vào một danh mục là gây nhầm khi tra cứu. Muốn nạp lại thì thêm
        # tên nó vào danh sách này, doc_nghe() lọc theo đúng danh sách.
        'van_ban': ['TT 11/2020/TT-BLĐTBXH', 'TT 19/2023/TT-BLĐTBXH'],
        'mo_ta': 'Danh mục các nghề, công việc được xếp vào điều kiện lao động '
                 'loại IV (nặng nhọc, độc hại, nguy hiểm) và loại V, VI (đặc biệt '
                 'nặng nhọc, độc hại, nguy hiểm), phân theo lĩnh vực.',
        'dung_de_lam_gi': 'Xác định người lao động được bồi dưỡng bằng hiện vật, '
                          'nghỉ hưu sớm, phụ cấp độc hại, rút ngắn thời giờ làm việc.',
        'pham_vi': 'Người lao động thuộc mọi thành phần kinh tế. Riêng trong Quân '
                   'đội áp dụng danh mục riêng của TT 28/2025/TT-BNV — danh mục đó '
                   'KHÔNG nằm trong bảng này.',
        'luu_y': 'Loại IV là nặng nhọc, loại V và VI là đặc biệt nặng nhọc. Số thứ '
                 'tự được đánh lại từ 1 ở mỗi lĩnh vực và mỗi loại điều kiện lao '
                 'động, nên stt không phải khóa.',
        'nhan_cap': ['Lĩnh vực', 'Điều kiện lao động'],
        'nhan_ten': 'Tên nghề, công việc',
        'nhan_ten_nhom': None,          # nghề không có dòng nhóm nào
        'nhan_ten_khac': None,
        'nhan_ma': None,
        'nhan_mo_ta': 'Đặc điểm điều kiện lao động',
    },
    'hoa_chat': {
        'ten': 'Các danh mục hóa chất thuộc phạm vi điều chỉnh của Luật Hóa chất',
        'ten_ngan': 'Hóa chất',
        'linh_vuc': 'Hóa chất',
        'co_quan': 'Bộ Công Thương',
        'can_cu': 'Luật Hóa chất 69/2025/QH15',
        'van_ban': ['NĐ 24/2026/NĐ-CP'],
        'mo_ta': 'Bốn phụ lục: hóa chất cơ bản trong công nghiệp trọng điểm (I), '
                 'hóa chất sản xuất kinh doanh có điều kiện (II), hóa chất cần '
                 'kiểm soát đặc biệt (III), hóa chất phải xây dựng Kế hoạch phòng '
                 'ngừa ứng phó sự cố (IV).',
        'dung_de_lam_gi': 'Xác định hóa chất phải xin phép sản xuất kinh doanh, '
                          'thuộc diện kiểm soát đặc biệt, hoặc phải lập Kế hoạch '
                          'phòng ngừa, ứng phó sự cố hóa chất.',
        'pham_vi': 'Tổ chức, cá nhân trong nước và nước ngoài hoạt động hóa chất '
                   'trên lãnh thổ Việt Nam.',
        'luu_y': 'Hỗn hợp chứa ít nhất một thành phần trong danh mục với hàm lượng '
                 'trên 5% khối lượng bị quản như chất tinh khiết (Phụ lục III là '
                 'trên 1% với nhóm 1) — quy tắc này nằm ở phần lời của phụ lục, '
                 'KHÔNG có trong bảng. Ngưỡng khối lượng tính bằng kg.',
        'nhan_cap': ['Phụ lục', 'Mục', 'Nhóm', 'Nhóm con'],
        'nhan_ten': 'Tên chất',
        # tiêu đề cột của Phụ lục IV Bảng B, lấy nguyên văn
        'nhan_ten_nhom': 'Nhóm hóa chất',
        'nhan_ten_khac': 'Tên khoa học (danh pháp IUPAC)',
        'nhan_ma': 'Mã số CAS',
        'nhan_mo_ta': None,
    },
}

COT_DANH_MUC = ['ma', 'ten', 'ten_ngan', 'linh_vuc', 'co_quan', 'can_cu', 'van_ban',
                'mo_ta', 'dung_de_lam_gi', 'pham_vi', 'luu_y', 'nhan_cap',
                'nhan_ten', 'nhan_ten_nhom', 'nhan_ten_khac', 'nhan_ma',
                'nhan_mo_ta']
COT_CHI_TIET = ['danh_muc_id', 'van_ban', 'van_ban_id', 'duong_dan',
                'stt', 'ten', 'ten_khac', 'ma_cas', 'cong_thuc_hoa_hoc',
                'nguong_khoi_luong_kg', 'mo_ta', 'content_hash']


# ------------------------------------------------------ nối sang bảng van_ban
#
#  Bảng `van_ban` đã có sẵn trong DB questions (2.612 dòng, kèm `link`) và bộ
#  câu hỏi test nối vào nó qua `cau_hoi_van_ban`. Ta lưu THÊM van_ban_id để
#  join được hai bộ dữ liệu, vẫn giữ cột tên đọc được.
#
#  Tra theo `khoa` — cột UNIQUE duy nhất dùng được. KHÔNG tra theo `so_hieu`:
#  cột đó NULL ở 732/2.612 dòng và không có ràng buộc duy nhất.
#      'TT 11/2020/TT-BLĐTBXH'  ->  khoa 'sh:11/2020/tt-blđtbxh'  ->  id 1916
RE_TIEN_TO = re.compile(r'^(TT|NĐ|QĐ|TTLT|VBHN|Luật|Thông tư|Nghị định)\s+')


def khoa_van_ban(ten: str) -> str:
    """Tên văn bản đang lưu -> `khoa` trong bảng van_ban."""
    return 'sh:' + RE_TIEN_TO.sub('', ten or '').strip().lower()


def tra_id_van_ban(cur, ten_van_ban) -> dict:
    """{tên văn bản: van_ban_id}. Tên nào không tra ra thì DỪNG, không để NULL.

    Để NULL âm thầm là kiểu lỗi tệ nhất ở đây: bảng vẫn nạp xong, mọi thống kê
    vẫn đúng, chỉ có việc join sang câu hỏi test là lặng lẽ mất dòng.
    """
    ten_van_ban = sorted(set(t for t in ten_van_ban if t))
    khoa = {t: khoa_van_ban(t) for t in ten_van_ban}
    cur.execute('SELECT khoa, van_ban_id FROM van_ban WHERE khoa = ANY(%s)',
                (list(khoa.values()),))
    theo_khoa = dict(cur.fetchall())
    ket_qua, thieu = {}, []
    for t, k in khoa.items():
        if k in theo_khoa:
            ket_qua[t] = theo_khoa[k]
        else:
            thieu.append(f'{t!r} -> khoa {k!r}')
    if thieu:
        raise SystemExit(
            'DỪNG: không tra ra van_ban_id cho:\n  ' + '\n  '.join(thieu) +
            '\nThêm văn bản vào bảng `van_ban` (đặt đúng `khoa`) rồi chạy lại.')
    return ket_qua

# ------------------------------------------------------------------ mã CAS
#
#  NGUYÊN TẮC: cột `ma_cas` lưu ĐÚNG NGUYÊN VĂN mã trong văn bản, KHÔNG sửa.
#  Đây là dữ liệu pháp lý — sửa mã, dù sửa đúng, là làm sai lệch văn bản. Bản
#  gốc NĐ 24/2026 có 4 mã không qua chữ số kiểm tra của CAS Registry:
#     50-00-00    Formaldehit (PL IV)                thừa một số 0
#     10037-74-3  Canxi clorat (PL II)               mã thật là 10137-74-3
#     7746-08-4   Selen dioxit (PL II)               mã thật là 7446-08-4
#     10118-77-6  1-Propen-2-clo-1,3-diol diaxetat   không tra ra mã đúng
#  Cả 4 vẫn lưu nguyên văn. Script không tự thay, và cũng không gắn cờ vào DB —
#  cần soi lại lúc nào thì chạy `nap_danh_muc_v3.py --dry-run`, nó in ra danh
#  sách; hoặc tính lại bằng cas_hop_le() vì cờ đó suy 100% từ chính mã CAS.

RE_CAS = re.compile(r'^\d{2,7}-\d{2}-\d$')

#  Ký hiệu "ô này không có giá trị" trong bản gốc. Dùng CHUNG cho cả `ma_cas`
#  lẫn `cong_thuc_hoa_hoc`: trước đây `ma_cas` đổi '---' thành NULL (55 dòng)
#  còn `cong_thuc_hoa_hoc` giữ nguyên văn '---' (32 dòng) — cùng một ký hiệu,
#  cùng một nghị định, hai cách xử lý. Đây là dấu TRÌNH BÀY, không phải dữ
#  liệu, nên bỏ về NULL; khác hẳn việc sửa mã CAS (không bao giờ làm).
KHONG_CO = ('-', '--', '---', '—', '–')


def cas_hop_le(ma: str) -> bool:
    """Kiểm tra mã CAS bằng chữ số kiểm tra chính thức của CAS Registry.

    Chữ số cuối = (tổng các chữ số còn lại, đếm từ phải sang, nhân 1,2,3...) mod 10.
    Ví dụ 7732-18-5 (nước): 8*1+1*2+2*3+3*4+7*5+7*6 = 105 -> 5.
    Dùng để GẮN CỜ, không dùng để loại mã ra khỏi dữ liệu.
    """
    if not RE_CAS.match(ma or ''):
        return False
    than, giua, kiem_tra = ma.split('-')
    chu_so = (than + giua)[::-1]
    return sum(int(c) * (i + 1) for i, c in enumerate(chu_so)) % 10 == int(kiem_tra)


def tach_cas(o_cas: str) -> tuple[list, list]:
    """Ô CAS -> (mọi mã nguyên văn, những mã không qua chữ số kiểm tra).

    Giữ nguyên thứ tự và nguyên giá trị như trong văn bản; chỉ bỏ ký hiệu
    "không có mã CAS" ('---') và chuẩn hoá khoảng trắng.
    """
    nguyen_van, sai = [], []
    for t in [x for x in re.split(r'[\s,;]+', str(o_cas or '')) if x]:
        if t in KHONG_CO:
            continue
        nguyen_van.append(t)
        if not cas_hop_le(t):
            sai.append(t)
    return nguyen_van, sai


# --------------------------------------------------------------- tiện ích

def bam(*phan) -> str:
    return hashlib.md5('|'.join(str(p or '') for p in phan).encode('utf-8')).hexdigest()


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    return str(v).strip()


def _mau(ma_danh_muc: str, **kw) -> dict:
    """Bản ghi chi tiết với mọi cột đã có mặt, tránh KeyError khi ghi."""
    ban_ghi = {'ma_danh_muc': ma_danh_muc, 'van_ban': '', 'duong_dan': [],
               'stt': '', 'ten': '', 'ten_khac': '',
               'ma_cas': [], 'cong_thuc_hoa_hoc': '', 'nguong_khoi_luong_kg': '',
               'mo_ta': ''}
    ban_ghi.update(kw)
    return ban_ghi


# ------------------------------------------------------------------- đọc

def doc_nghe() -> list[dict]:
    """Nghề: 2 tầng — lĩnh vực, rồi loại điều kiện lao động."""
    df = pd.read_excel(XL_NGHE, sheet_name='Danh mục nghề', dtype=str).fillna('')
    cho_phep = DANH_MUC['nghe_nndhnh']['van_ban']
    dong = []
    for r in df.to_dict('records'):
        if _s(r['van_ban']) not in cho_phep:      # Excel có cả TT 28/2025
            continue
        duong_dan = [f"{_s(r['so_linh_vuc'])}. {_s(r['linh_vuc'])}",
                     _s(r['dieu_kien_lao_dong'])]
        dong.append(_mau(
            'nghe_nndhnh',
            van_ban=_s(r['van_ban']),
            duong_dan=[x for x in duong_dan if x],
            stt=_s(r['stt']),
            ten=_s(r['ten_nghe_cong_viec']),
            mo_ta=_s(r['dac_diem_dieu_kien_lao_dong']),
        ))
    return dong


#  Dòng nào là mục thật, dòng nào là nhóm / ghi chú / nối tiếp: KHÔNG lưu cột,
#  tính tại chỗ ở view `v_danh_muc_chi_tiet` (cột `loai_muc`), vì suy được 100%
#  từ dữ liệu sẵn có. Luật nằm DUY NHẤT trong file schema — đừng viết lại ở
#  đây kẻo hai chỗ lệch nhau. Script này chỉ đọc lại con số từ view.

def doc_hoa_chat() -> tuple[list[dict], dict]:
    """Hóa chất: tới 4 tầng — Phụ lục, Mục, Nhóm A/B/C, Nhóm con."""
    df = pd.read_excel(XL_HOA_CHAT, sheet_name='Tất cả', dtype=str).fillna('')
    dong, thong_ke_cas = [], {'sai_chu_so_kiem_tra': []}
    for r in df.to_dict('records'):
        ma_nguyen_van, cas_sai = tach_cas(_s(r['ma_cas']))
        thong_ke_cas['sai_chu_so_kiem_tra'] += cas_sai

        # 4 tầng, bỏ tầng rỗng: Phụ lục I chỉ có 1 tầng, Phụ lục III có đủ 4
        duong_dan = [x for x in ['Phụ lục ' + _s(r['phu_luc']), _s(r['muc']),
                                 _s(r['nhom_lon']), _s(r['nhom'])] if x.strip(' ')]

        # Bảng B của Phụ lục IV phân loại theo NHÓM NGUY HẠI, không có tên chất
        # -> lấy nhóm nguy hại làm `ten` để cột này không bao giờ rỗng. Cột
        # `nhom_hoa_chat` chỉ có giá trị ở Bảng B — view v_danh_muc_chi_tiet
        # nhận ra các dòng đó bằng chính dấu hiệu này (duong_dan[2] có 'Bảng B'
        # và không có CAS lẫn công thức) để đặt loai_muc='nhom'.
        ten = _s(r['ten_chat']) or _s(r['nhom_hoa_chat']) or _s(r['ten_khoa_hoc'])
        ten_khac = _s(r['ten_khoa_hoc']) if _s(r['ten_chat']) else ''

        cong_thuc = _s(r['cong_thuc_hoa_hoc'])
        if cong_thuc in KHONG_CO:      # '---' là dấu trình bày, không phải dữ liệu
            cong_thuc = ''

        dong.append(_mau(
            'hoa_chat',
            van_ban='NĐ 24/2026/NĐ-CP',
            duong_dan=duong_dan,
            stt=_s(r['stt']),
            ten=ten,
            ten_khac=ten_khac,
            ma_cas=ma_nguyen_van,
            cong_thuc_hoa_hoc=cong_thuc,
            # đơn vị kg nằm ở tiêu đề cột của Phụ lục IV -> đưa vào TÊN cột
            nguong_khoi_luong_kg=_s(r['nguong_khoi_luong_tan']),
        ))
    return dong, thong_ke_cas


def build() -> tuple[list[dict], dict]:
    dong = doc_nghe()
    hoa_chat, cas = doc_hoa_chat()
    dong += hoa_chat
    for d in dong:
        d['content_hash'] = bam(d['ma_danh_muc'], d['van_ban'],
                                ' › '.join(d['duong_dan']), d['stt'], d['ten'])
    return dong, cas


# --------------------------------------------------------------- thống kê

def thong_ke(dong: list[dict], cas: dict) -> None:
    df = pd.DataFrame(dong)
    df['so_tang'] = df['duong_dan'].apply(len)
    print(f'\nTỔNG: {len(df)} dòng / {df["ma_danh_muc"].nunique()} danh mục')
    print(df.groupby(['ma_danh_muc', 'van_ban']).size().to_string())

    print('\nSố tầng của đường dẫn:')
    print(df.groupby(['ma_danh_muc', 'so_tang']).size().to_string())

    print(f'\nDòng có công thức HH: {sum(1 for d in dong if d["cong_thuc_hoa_hoc"])}'
          '  (dấu "---" của bản gốc bỏ về rỗng, giống ma_cas)')
    print(f'Mục có mã CAS       : {sum(1 for d in dong if d["ma_cas"])}')
    print(f'Mục có nhiều mã CAS : {sum(1 for d in dong if len(d["ma_cas"]) > 1)}')
    print(f'Tổng số mã CAS      : {sum(len(d["ma_cas"]) for d in dong)}'
          '  (lưu NGUYÊN VĂN, không sửa)')
    sai = sorted(set(cas['sai_chu_so_kiem_tra']))
    print(f'Mã sai chữ số kiểm tra trong BẢN GỐC: {len(sai)} -> {sai}')
    print('   (vẫn lưu NGUYÊN VĂN vào ma_cas; không sửa, không gắn cờ vào DB)')

    trung = len(df) - df['content_hash'].nunique()
    print(f'content_hash trùng nhau: {trung}')
    print(f'Mục có `ten` rỗng      : {(df["ten"].str.strip() == "").sum()}')
    print(f'Mục có đường dẫn rỗng  : {(df["so_tang"] == 0).sum()}')

    loi = []
    for d in dong:
        cau_hinh = DANH_MUC[d['ma_danh_muc']]
        if d['van_ban'] not in cau_hinh['van_ban']:
            loi.append(f'văn bản lạ: {d["van_ban"]}')
        if len(d['duong_dan']) > len(cau_hinh['nhan_cap']):
            loi.append(f'{d["ma_danh_muc"]}: đường dẫn {len(d["duong_dan"])} tầng '
                       f'> {len(cau_hinh["nhan_cap"])} nhãn đã khai')
    print(f'Lỗi cấu hình           : {len(loi)}'
          + (f' -> {sorted(set(loi))[:3]}' if loi else ''))
    if loi:
        raise SystemExit('Dữ liệu không khớp khai báo ở DANH_MUC, dừng.')


# ------------------------------------------------------- nạp trực tiếp

def load_db(dong: list[dict], args) -> None:
    import psycopg2
    from psycopg2.extras import execute_values

    conn = psycopg2.connect(args.dsn or DSN)
    with conn, conn.cursor() as cur:
        if args.schema_file:
            cur.execute(open(args.schema_file, encoding='utf-8').read())
        if args.reset:
            cur.execute('TRUNCATE danh_muc_chi_tiet, danh_muc RESTART IDENTITY')

        cap_nhat = ', '.join(f'{c} = EXCLUDED.{c}' for c in COT_DANH_MUC if c != 'ma')
        execute_values(cur, f"""
            INSERT INTO danh_muc ({', '.join(COT_DANH_MUC)}) VALUES %s
            ON CONFLICT (ma) DO UPDATE SET {cap_nhat}, cap_nhat_luc = now()
        """, [tuple(ma if c == 'ma' else d.get(c) for c in COT_DANH_MUC)
              for ma, d in DANH_MUC.items()])

        cur.execute('SELECT ma, danh_muc_id FROM danh_muc')
        id_danh_muc = dict(cur.fetchall())

        id_van_ban = tra_id_van_ban(cur, (d['van_ban'] for d in dong))
        print('\nNối sang bảng van_ban (tra theo `khoa`):')
        for t, i in sorted(id_van_ban.items()):
            print(f'  {t:24} -> van_ban_id {i}')

        execute_values(cur, f"""
            INSERT INTO danh_muc_chi_tiet ({', '.join(COT_CHI_TIET)}) VALUES %s
            ON CONFLICT (content_hash) DO NOTHING
        """, [(id_danh_muc[d['ma_danh_muc']], d['van_ban'] or None,
               id_van_ban.get(d['van_ban']), d['duong_dan'],
               d['stt'] or None, d['ten'], d['ten_khac'] or None,
               '; '.join(d['ma_cas']) or None,
               d['cong_thuc_hoa_hoc'] or None, d['nguong_khoi_luong_kg'] or None,
               d['mo_ta'] or None, d['content_hash'])
              for d in dong], page_size=500)

        # so_muc đếm qua VIEW vì `loai_muc` là cột tính tại chỗ ở đó
        cur.execute("""UPDATE danh_muc dm SET
                         so_muc = (SELECT count(*) FROM v_danh_muc_chi_tiet v
                                   WHERE v.ma_danh_muc = dm.ma
                                     AND v.loai_muc = 'muc'),
                         so_dong = (SELECT count(*) FROM danh_muc_chi_tiet ct
                                    WHERE ct.danh_muc_id = dm.danh_muc_id)""")

        cur.execute("""SELECT ma, ten_ngan, so_muc, so_dong,
                              array_length(van_ban,1), array_length(nhan_cap,1)
                       FROM danh_muc ORDER BY ma""")
        print('\nTrong DB sau khi nạp:')
        for ma, ten_ngan, so_muc, so_dong, so_vb, so_nhan in cur.fetchall():
            them = '' if so_muc == so_dong else f' (+{so_dong - so_muc} dòng khác)'
            print(f'  {ma:14} {ten_ngan or "":24} {so_muc:5} mục{them}'
                  f' / {so_vb} văn bản / {so_nhan} tầng')

        cur.execute("""SELECT ma_danh_muc, loai_muc, sum(so_dong)
                       FROM v_danh_muc_dem GROUP BY 1,2 ORDER BY 1, 3 DESC""")
        print('\nLoại dòng:')
        for ma, loai, n in cur.fetchall():
            print(f'  {ma:14} {loai:10} {n:5}')

        for view, nhan in (('v_danh_muc_sai_van_ban', 'tên văn bản'),
                           ('v_danh_muc_thieu_nhan', 'nhãn từng tầng'),
                           ('v_danh_muc_thieu_van_ban_id', 'van_ban_id')):
            cur.execute(f'SELECT count(*) FROM {view}')
            n = cur.fetchone()[0]
            print(f'  Kiểm tra chéo {nhan:16}: {"OK" if not n else str(n) + " SAI"}')

        cur.execute("""SELECT ma_danh_muc, van_ban, van_ban_id, so_muc,
                              so_cau_hoi_test
                       FROM v_danh_muc_van_ban ORDER BY 1, 2""")
        print('\nĐiểm nối với bộ câu hỏi test:')
        for ma, vb, vid, n, nch in cur.fetchall():
            print(f'  {ma:14} {vb:24} id={vid:5} {n:5} mục'
                  f' / {nch} câu hỏi test đang trỏ vào văn bản này')
    conn.close()


# -------------------------------------------------------------- sinh SQL

def q(s):
    if s is None or s == '':
        return 'NULL'
    return "'" + str(s).replace("'", "''") + "'"


def mang(xs) -> str:
    if not xs:
        return "'{}'"
    return 'ARRAY[' + ','.join(q(x) for x in xs) + ']::text[]'


def emit_sql(dong: list[dict], out: str, with_schema: bool) -> None:
    L = []
    if with_schema:
        L.append(open(os.path.join(THU_MUC, 'schema_danh_muc_v3.sql'),
                      encoding='utf-8').read())
    L.append('BEGIN;')
    for ma, d in DANH_MUC.items():
        gt = []
        for c in COT_DANH_MUC:
            v = ma if c == 'ma' else d.get(c)
            gt.append(mang(v) if isinstance(v, list) else q(v))
        L.append(f"INSERT INTO danh_muc({', '.join(COT_DANH_MUC)}) "
                 f"VALUES({','.join(gt)}) ON CONFLICT (ma) DO NOTHING;")
    for d in dong:
        dm = f"(SELECT danh_muc_id FROM danh_muc WHERE ma={q(d['ma_danh_muc'])})"
        L.append(
            f"INSERT INTO danh_muc_chi_tiet({', '.join(COT_CHI_TIET)}) VALUES("
            f"{dm},{q(d['van_ban'])},"
            f"(SELECT van_ban_id FROM van_ban WHERE khoa="
            f"{q(khoa_van_ban(d['van_ban']))}),"
            f"{mang(d['duong_dan'])},{q(d['stt'])},"
            f"{q(d['ten'])},{q(d['ten_khac'])},{q('; '.join(d['ma_cas']))},"
            f"{q(d['cong_thuc_hoa_hoc'])},{q(d['nguong_khoi_luong_kg'])},"
            f"{q(d['mo_ta'])},"
            f"{q(d['content_hash'])}) ON CONFLICT (content_hash) DO NOTHING;")
    L.append("UPDATE danh_muc dm SET"
             " so_muc = (SELECT count(*) FROM v_danh_muc_chi_tiet v"
             "  WHERE v.ma_danh_muc = dm.ma AND v.loai_muc = 'muc'),"
             " so_dong = (SELECT count(*) FROM danh_muc_chi_tiet ct"
             "  WHERE ct.danh_muc_id = dm.danh_muc_id);")
    L.append('COMMIT;')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print(f'\n-> {out}  ({len(L)} câu lệnh, {os.path.getsize(out) / 1024:.0f} KB)')


def main() -> None:
    ap = argparse.ArgumentParser(
        description='Nạp danh mục vào 2 bảng, phân cấp bằng mảng đường dẫn.')
    ap.add_argument('--dry-run', action='store_true', help='Chỉ in thống kê')
    ap.add_argument('--emit-sql', metavar='FILE', help='Sinh file SQL (không cần DB)')
    ap.add_argument('--with-schema', action='store_true',
                    help='Kèm schema_danh_muc_v3.sql vào đầu file SQL sinh ra')
    ap.add_argument('--schema-file', metavar='FILE',
                    help='Chạy file schema trước khi nạp trực tiếp')
    ap.add_argument('--reset', action='store_true',
                    help='TRUNCATE cả 2 bảng rồi nạp lại từ đầu')
    ap.add_argument('--load', action='store_true', help='Nạp trực tiếp vào DB')
    ap.add_argument('--dsn', help=f'Chuỗi kết nối; mặc định {DSN}')
    args = ap.parse_args()

    dong, cas = build()
    thong_ke(dong, cas)

    if args.emit_sql:
        emit_sql(dong, args.emit_sql, args.with_schema)
    if args.load:
        load_db(dong, args)
    if not args.emit_sql and not args.load:
        print('\n(dry-run: chưa ghi gì. Dùng --emit-sql FILE hoặc --load để nạp.)')


if __name__ == '__main__':
    main()
