# -*- coding: utf-8 -*-
"""Xuất CẤU TRÚC bảng trong DB `questions` ra Excel.

Đọc thẳng từ information_schema / pg_indexes / pg_constraint nên luôn khớp với
DB thật, không phải chép tay từ file schema.

Chạy:
    venv\\Scripts\\python.exe xuat_cau_truc_db.py
        -> data/cau_truc_danh_muc_2_bang.xlsx, gồm CẢ HAI bảng
           danh_muc + danh_muc_chi_tiet trong một file

    venv\\Scripts\\python.exe xuat_cau_truc_db.py ten_bang [ten_bang2 ...]
        -> một bảng thì ra data/cau_truc_<ten_bang>.xlsx
           nhiều bảng thì gộp vào data/cau_truc_<bang_dau>_<n>_bang.xlsx
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import psycopg2

from danh_muc_common import ghi_excel

for _luong in (sys.stdout, sys.stderr):   # chạy được cả trong PowerShell lẫn bash
    try:
        _luong.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DSN = (os.environ.get('DATABASE_URL')
       or 'postgresql://questions:questions@172.16.10.71:5433/questions')
THU_MUC = os.path.dirname(os.path.abspath(__file__))
MAC_DINH = ['danh_muc', 'danh_muc_chi_tiet']

# Mô tả cột - phần này là kiến thức nghiệp vụ, DB không tự có.
# CHIA THEO BẢNG: `van_ban` và `ten` có mặt ở cả hai bảng nhưng mang nghĩa khác
# nhau, nên gộp một dict phẳng thì khóa trùng và bảng này lấy chú thích của
# bảng kia.
MO_TA_COT = {
    'danh_muc': {
        'danh_muc_id': 'Khóa chính, tự tăng. Bảng chi tiết trỏ vào đây',
        'ma': 'Mã danh mục: nghe_nndhnh | hoa_chat',
        'ten': 'Tên đầy đủ của danh mục',
        'ten_ngan': 'Tên gọi ngắn để hiện trên giao diện',
        'linh_vuc': 'Lĩnh vực quản lý nhà nước',
        'co_quan': 'Cơ quan ban hành',
        'can_cu': 'Luật gốc mà danh mục này chi tiết hóa',
        'van_ban': 'text[] - TÊN các văn bản của danh mục này (không phải id)',
        'mo_ta': 'Danh mục này liệt kê cái gì',
        'dung_de_lam_gi': 'Danh mục dùng để xác định quyền / nghĩa vụ gì',
        'pham_vi': 'Đối tượng áp dụng',
        'luu_y': 'Cạm bẫy khi tra cứu (quy tắc nằm ở phần lời, không ở bảng…)',
        'nhan_cap': 'text[] - nhãn TỪNG TẦNG của duong_dan; '
                    'nhan_cap[i] ứng với duong_dan[i]',
        'nhan_ten': 'Tiêu đề cột `ten` ở bảng chi tiết theo danh mục này',
        'nhan_ten_nhom': 'Tiêu đề cột `ten` cho dòng loai_muc=nhom '
                         "('Nhóm hóa chất' - tiêu đề gốc của Phụ lục IV Bảng B)",
        'nhan_ten_khac': 'Tiêu đề cột `ten_khac`; NULL nếu danh mục không dùng',
        'nhan_ma': 'Tiêu đề cột `ma_cas`; NULL nếu danh mục không dùng',
        'nhan_mo_ta': 'Tiêu đề cột `mo_ta`; NULL nếu danh mục không dùng',
        'so_muc': 'Số mục THẬT (loai_muc=muc ở v_danh_muc_chi_tiet). '
                  'Script nạp tự cập nhật',
        'so_dong': 'Tổng số dòng, KỂ CẢ dòng nhóm / ghi chú / nối tiếp. '
                   'hoa_chat: so_muc 1.348 nhưng so_dong 1.376',
        'cap_nhat_luc': 'Thời điểm cập nhật dòng danh mục',
    },
    'danh_muc_chi_tiet': {
        'muc_id': 'Khóa chính, tự tăng',
        'danh_muc_id': 'Khóa ngoại sang danh_muc, ON DELETE CASCADE',
        'van_ban': 'Tên văn bản ban hành mục này (1 trong danh_muc.van_ban)',
        'van_ban_id': 'Khóa ngoại sang bảng `van_ban` của DB - ĐIỂM NỐI với bộ '
                      'câu hỏi test (cau_hoi_van_ban). Tra theo van_ban.khoa',
        'duong_dan': 'text[] - đường dẫn phân cấp, sâu bao nhiêu tầng cũng được. '
                     'Nghề 2 tầng, hóa chất 1-4 tầng',
        'stt': 'Số thứ tự IN TRONG VĂN BẢN. KHÔNG duy nhất - bản gốc có chỗ đánh '
               'trùng hoặc nhảy số; giữ nguyên, không sửa',
        'ten': 'Tên của mục: tên nghề / tên chất / tên nhóm nguy hại',
        'ten_khac': 'Tên thay thế: tên khoa học IUPAC hoặc tên tiếng Anh',
        'ma_cas': 'Mã CAS NGUYÊN VĂN văn bản, không sửa. Nhiều mã ngăn bởi "; ". '
                  "Tra chính xác: '71-43-2' = ANY(string_to_array(ma_cas, '; '))",
        'cong_thuc_hoa_hoc': 'Công thức hóa học, lấy nguyên cột cùng tên trong NĐ. '
                             'Dấu "---" của bản gốc đã bỏ về NULL, như ma_cas',
        'nguong_khoi_luong_kg': 'Ngưỡng khối lượng, chỉ Phụ lục IV có. Đơn vị kg '
                                "nằm ở TÊN cột; giá trị nguyên văn ('5.000') nên "
                                'KHÔNG so sánh số được',
        'mo_ta': 'Diễn giải: đặc điểm điều kiện lao động…',
        'content_hash': 'md5 các trường định danh - để nạp lại không nhân bản',
        'created_at': 'Thời điểm nạp vào DB',
    },
}

# Cột chỉ có ở VIEW, không có ở bảng - ghi ra để khỏi tưởng là thiếu
COT_CHI_O_VIEW = [
    ('loai_muc', 'v_danh_muc_chi_tiet',
     'muc | nhom | ghi_chu | tiep_noi. TÍNH TẠI CHỖ bằng CASE, không lưu cột, '
     'vì suy được 100% từ dữ liệu sẵn có. Chỉ `muc` là mục thật của danh mục'),
    ('nhan_ten', 'v_danh_muc_chi_tiet',
     'Nhãn ĐÚNG cho cột `ten` của chính dòng đó: dòng loai_muc=nhom lấy '
     'danh_muc.nhan_ten_nhom, còn lại lấy danh_muc.nhan_ten'),
    ('vi_tri', 'v_danh_muc_chi_tiet',
     "duong_dan đã nối bằng ' › ' để đọc bằng mắt"),
    ('cap_1, cap_2', 'v_danh_muc_chi_tiet', 'duong_dan[1], duong_dan[2]'),
    ('phan_loai_nghe', 'v_danh_muc_chi_tiet',
     'Nặng nhọc (Loại IV) / Đặc biệt nặng nhọc (Loại V, VI), tính từ duong_dan'),
    ('ten_van_ban, link_van_ban', 'v_danh_muc_chi_tiet',
     'Lấy từ bảng `van_ban` qua van_ban_id - nguồn để đối chiếu nguyên văn'),
    ('cap, nhan, gia_tri', 'v_danh_muc_tang',
     'Trải TỪNG TẦNG của duong_dan thành một dòng, kèm đúng nhãn của tầng đó'),
    ('so_cau_hoi_test', 'v_danh_muc_van_ban',
     'Số câu hỏi test đang trỏ vào cùng văn bản đó - chỗ hai bộ dữ liệu gặp nhau'),
]

# Cùng một cột mang nội dung khác nhau tùy danh mục — 2 danh mục đang có trong DB
COT_Y_NGHIA = ['cot', 'nghe_nndhnh', 'hoa_chat']
Y_NGHIA = [
    ('van_ban', 'TT 11/2020/TT-BLĐTBXH hoặc TT 19/2023/TT-BLĐTBXH',
     'NĐ 24/2026/NĐ-CP'),
    ('duong_dan[1]', 'lĩnh vực (XV. Y TẾ VÀ DƯỢC)', 'Phụ lục I…IV'),
    ('duong_dan[2]', 'Loại IV / V / VI', 'mục trong phụ lục (1.1. Nhóm 1)'),
    ('duong_dan[3]', '— (nghề chỉ 2 tầng)', 'nhóm A/B/C của phụ lục III'),
    ('duong_dan[4]', '—', 'nhóm con (2B. Các tiền chất…)'),
    ('loai_muc (ở view)', 'muc: tất cả 1.892 dòng',
     'muc 1.348 / nhom 21 / tiep_noi 4 / ghi_chu 3'),
    ('stt', 'số thứ tự trong lĩnh vực + loại', 'số thứ tự trong phụ lục'),
    ('ten', 'tên nghề, công việc', 'tên chất tiếng Việt (dòng nhóm: nhóm nguy hại)'),
    ('ten_khac', '—', 'tên khoa học IUPAC'),
    ('ma_cas', '—', 'mã CAS nguyên văn'),
    ('cong_thuc_hoa_hoc', '—', 'công thức hóa học (C6H6)'),
    ('nguong_khoi_luong_kg', '—', 'ngưỡng khối lượng, chỉ Phụ lục IV'),
    ('mo_ta', 'đặc điểm điều kiện lao động', '—'),
]

LOAI_RANG_BUOC = {'p': 'PRIMARY KEY', 'u': 'UNIQUE', 'f': 'FOREIGN KEY',
                  'c': 'CHECK', 'x': 'EXCLUDE'}


def _dieu_kien_co_du_lieu(ten: str, kieu: str, udt: str) -> str:
    """Cột 'có dữ liệu' nghĩa là khác NULL và khác giá trị rỗng của kiểu đó."""
    if udt == '_text':
        return f"{ten} is not null and {ten} <> '{{}}'"
    if kieu == 'jsonb':
        return f"{ten} is not null and {ten} <> '{{}}'::jsonb"
    if kieu == 'text':
        return f"{ten} is not null and {ten} <> ''"
    return f'{ten} is not null'


def doc_mot_bang(cur, bang: str) -> dict:
    """Đọc mọi thứ về một bảng. Trả về dict các DataFrame + số tổng quan."""
    cur.execute("""select ordinal_position, column_name, data_type, udt_name,
                          is_nullable, column_default
                   from information_schema.columns
                   where table_schema='public' and table_name=%s
                   order by ordinal_position""", (bang,))
    cot = cur.fetchall()
    if not cot:
        raise SystemExit(f'Không có bảng "{bang}" trong DB')

    cur.execute(f'select count(*) from {bang}')
    tong = cur.fetchone()[0]
    do_lap_day = {}
    for _, ten, kieu, udt, _, _ in cot:
        cur.execute(f'select count(*) from {bang} where '
                    + _dieu_kien_co_du_lieu(ten, kieu, udt))
        do_lap_day[ten] = cur.fetchone()[0]

    mo_ta = MO_TA_COT.get(bang, {})
    df_cot = pd.DataFrame([{
        'stt': r[0],
        'ten_cot': r[1],
        'kieu_du_lieu': 'text[]' if r[3] == '_text' else r[2],
        'cho_phep_null': 'NULL' if r[4] == 'YES' else 'NOT NULL',
        'mac_dinh': r[5] or '',
        'so_dong_co_du_lieu': do_lap_day[r[1]],
        'ty_le': f'{do_lap_day[r[1]] * 100 // tong}%' if tong else '',
        'y_nghia': mo_ta.get(r[1], ''),
    } for r in cot])

    cur.execute("""select con.conname, con.contype, pg_get_constraintdef(con.oid)
                   from pg_constraint con join pg_class c on c.oid = con.conrelid
                   where c.relname = %s order by con.contype""", (bang,))
    df_rb = pd.DataFrame([{'bang': bang, 'ten': n, 'loai': LOAI_RANG_BUOC.get(t, t),
                           'dinh_nghia': d} for n, t, d in cur.fetchall()])

    cur.execute('select indexname, indexdef from pg_indexes '
                'where tablename = %s order by indexname', (bang,))
    df_ci = pd.DataFrame([{
        'bang': bang,
        'ten': n,
        'kieu': d.split(' USING ')[1].split(' ')[0] if ' USING ' in d else '',
        'dinh_nghia': d.split(' USING ')[1] if ' USING ' in d else d,
    } for n, d in cur.fetchall()])

    cur.execute(f"select pg_size_pretty(pg_total_relation_size('{bang}')),"
                f"       pg_size_pretty(pg_relation_size('{bang}')),"
                f"       pg_size_pretty(pg_indexes_size('{bang}'))")
    kt_tong, kt_bang, kt_ci = cur.fetchone()

    return {'bang': bang, 'cot': df_cot, 'rang_buoc': df_rb, 'chi_muc': df_ci,
            'so_cot': len(cot), 'so_dong': tong,
            'kich_thuoc': kt_tong, 'kt_bang': kt_bang, 'kt_chi_muc': kt_ci}


def main() -> None:
    bang = sys.argv[1:] or MAC_DINH
    conn = psycopg2.connect(DSN, connect_timeout=10)
    conn.set_session(readonly=True)
    with conn, conn.cursor() as cur:
        kq = [doc_mot_bang(cur, b) for b in bang]

        # View nào có nhắc tới bất kỳ bảng nào trong danh sách
        dk = ' or '.join(['view_definition like %s'] * len(bang))
        cur.execute("""select table_name, view_definition
                       from information_schema.views
                       where table_schema='public' and (""" + dk + ')'
                       + ' order by table_name', [f'%{b}%' for b in bang])
        df_view = pd.DataFrame([{'ten_view': n, 'dinh_nghia': ' '.join(d.split())}
                                for n, d in cur.fetchall()])

        # Hiện trạng dữ liệu - chỉ dựng khi có bảng chi tiết trong danh sách
        df_ht = pd.DataFrame()
        if 'danh_muc_chi_tiet' in bang:
            cur.execute("""select v.ma_danh_muc, v.van_ban, v.van_ban_id,
                                  count(*) filter (where v.loai_muc='muc'),
                                  count(*),
                                  count(distinct v.duong_dan[1]),
                                  max(array_length(v.duong_dan, 1)),
                                  count(v.ma_cas)
                           from v_danh_muc_chi_tiet v
                           group by 1, 2, 3 order by 1, 2""")
            df_ht = pd.DataFrame(cur.fetchall(),
                                 columns=['ma_danh_muc', 'van_ban', 'van_ban_id',
                                          'so_muc_that', 'so_dong', 'so_cap_1',
                                          'so_tang_sau_nhat', 'so_dong_co_ma_cas'])

        # Quan hệ giữa các bảng, đọc từ chính khóa ngoại
        cur.execute("""select c.relname, con.conname,
                              ct.relname, pg_get_constraintdef(con.oid)
                       from pg_constraint con
                       join pg_class c  on c.oid  = con.conrelid
                       join pg_class ct on ct.oid = con.confrelid
                       where con.contype='f' and c.relname = any(%s)
                       order by 1, 2""", (list(bang),))
        df_qh = pd.DataFrame(cur.fetchall(),
                             columns=['bang_con', 'ten_khoa_ngoai',
                                      'bang_cha', 'dinh_nghia'])
    conn.close()

    df_tq = pd.DataFrame([{
        'bang': k['bang'], 'so_cot': k['so_cot'], 'so_dong': k['so_dong'],
        'kich_thuoc_tong': k['kich_thuoc'], 'rieng_bang': k['kt_bang'],
        'rieng_chi_muc': k['kt_chi_muc'],
        'so_rang_buoc': len(k['rang_buoc']), 'so_chi_muc': len(k['chi_muc']),
    } for k in kq])

    sheets = {'Tổng quan': df_tq}
    for k in kq:
        # tên sheet Excel tối đa 31 ký tự
        sheets[f"Cột - {k['bang']}"[:31]] = k['cot']
    sheets['Quan hệ'] = df_qh
    sheets['Ràng buộc'] = pd.concat([k['rang_buoc'] for k in kq],
                                    ignore_index=True)
    sheets['Chỉ mục'] = pd.concat([k['chi_muc'] for k in kq], ignore_index=True)
    sheets['Cột chỉ có ở view'] = pd.DataFrame(
        COT_CHI_O_VIEW, columns=['cot', 'o_view', 'y_nghia'])
    sheets['Ý nghĩa cột theo danh mục'] = pd.DataFrame(Y_NGHIA,
                                                       columns=COT_Y_NGHIA)
    if len(df_ht):
        sheets['Hiện trạng dữ liệu'] = df_ht
    if len(df_view):
        sheets['View liên quan'] = df_view

    ten_file = (f'cau_truc_{bang[0]}.xlsx' if len(bang) == 1
                else f'cau_truc_{bang[0]}_{len(bang)}_bang.xlsx')
    for k in kq:
        print(f"  {k['bang']:20} {k['so_cot']:3} cột, {k['so_dong']:5} dòng, "
              f"{k['kich_thuoc']:>9}, {len(k['rang_buoc'])} ràng buộc, "
              f"{len(k['chi_muc'])} chỉ mục")
    print(f'  {len(df_view)} view liên quan, {len(df_qh)} khóa ngoại, '
          f'{len(sheets)} sheet')
    ghi_excel(os.path.join(THU_MUC, 'data', ten_file), sheets,
              {'y_nghia': 66, 'dinh_nghia': 70, 'ten': 34, 'ten_cot': 22,
               'kieu_du_lieu': 14, 'van_ban': 24, 'cot': 22, 'nghe_nndhnh': 40,
               'hoa_chat': 44, 'ten_view': 28, 'o_view': 21, 'bang': 20,
               'bang_con': 20, 'bang_cha': 12, 'ten_khoa_ngoai': 38})


if __name__ == '__main__':
    main()
