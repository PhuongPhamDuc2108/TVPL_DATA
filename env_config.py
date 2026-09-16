# -*- coding: utf-8 -*-
"""
Nạp biến môi trường từ file .env ở thư mục gốc dự án.

Vì sao tự viết thay vì dùng python-dotenv: cả dự án chỉ dùng thư viện chuẩn
(gọi API bằng urllib chứ không phải requests), và tool_annotate còn chạy bằng
một interpreter riêng (ocr_env) không cài thêm gói nào. Thêm một phụ thuộc chỉ
để đọc file 5 dòng thì không đáng.

Biến ĐÃ CÓ trong môi trường thì .env KHÔNG ghi đè, để còn tạm đổi key bằng
    set GEMINI_API_KEY=...        (cmd)
    $env:GEMINI_API_KEY="..."     (PowerShell)
mà không phải sửa file.

Dùng: chỉ cần "import env_config" một lần, ở đầu file nào đọc os.environ.
"""
import os


def tim_env(bat_dau=None):
    """Tìm ngược lên các thư mục cha cho tới khi gặp .env (hoặc hết đường)."""
    d = os.path.abspath(bat_dau or os.path.dirname(os.path.abspath(__file__)))
    while True:
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            return p
        cha = os.path.dirname(d)
        if cha == d:
            return None
        d = cha


def nap_env(duong_dan=None):
    """Đọc .env vào os.environ. Trả về số biến thực sự được đặt."""
    p = duong_dan or tim_env()
    if not p:
        return 0
    n = 0
    with open(p, "r", encoding="utf-8") as f:
        for dong in f:
            dong = dong.strip()
            if dong.startswith("export "):        # chấp nhận cả cú pháp shell
                dong = dong[7:].strip()
            if not dong or dong.startswith("#") or "=" not in dong:
                continue
            ten, _, gia_tri = dong.partition("=")
            ten = ten.strip()
            gia_tri = gia_tri.strip()
            if len(gia_tri) >= 2 and gia_tri[0] == gia_tri[-1] and gia_tri[0] in "\"'":
                gia_tri = gia_tri[1:-1]
            if ten and ten not in os.environ:
                os.environ[ten] = gia_tri
                n += 1
    return n


nap_env()
