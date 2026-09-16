# -*- coding: utf-8 -*-
"""
Làm sạch TÊN văn bản pháp luật bị "bắt lố" (dính mệnh đề phía sau).
Dùng chung cho: bộ tách trích dẫn (collect_*), dọn JSON, dọn DB.

  clean_name("Luật BHYT, đã được sửa đổi... tại Nghị định 75/2023") -> "Luật BHYT"
  Giữ NĂM / SỐ HIỆU; KHÔNG cắt nhầm tên ghép hợp lệ
  ("Luật Trật tự, an toàn giao thông đường bộ", "Luật Khám bệnh, chữa bệnh"...).
"""
import re
import unicodedata

_LOAI = ["Bộ luật", "Luật", "Thông tư liên tịch", "Thông tư", "Nghị định",
         "Nghị quyết", "Quyết định", "Pháp lệnh", "Văn bản hợp nhất", "Hiến pháp"]
_VBT = (r"(?:Bộ luật|Luật|Nghị định|Thông tư(?:\s+liên tịch)?|Nghị quyết|Quyết định|"
        r"Pháp lệnh|Hiến pháp|Văn bản hợp nhất)")
# Từ mở đầu MỆNH ĐỀ nối (không nằm trong tên luật) -> cắt tại đây.
_CLAUSE = (r"(?:đã|đang|được|hiện|nếu|khi|người|việc|những|các|trong|mà|do|để|thì|cụ thể|"
           r"theo|tại|quy định|nay|sau đây|sau đó|gồm|bao gồm|trừ|từ|thực hiện|thuộc|khám|"
           r"thẻ|có|không|nhằm|vẫn|chỉ|phải|sẽ|nêu|dùng để|áp dụng|giấy tờ|thời điểm|"
           r"trường hợp|mua|bán|quá trình|đối với|ngoài ra|đồng thời|thể hiện|nhưng|"
           r"đảm bảo|bảo đảm|kể từ|hành vi|thời gian|giá|trừ|còn|khi đó|do đó|vì)")
_RE_SOHIEU = re.compile(r"\d+[/-]\d{2,4}[/-][A-ZĐ][A-ZĐ0-9-]*")


def strip_dia(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def so_hieu(ten):
    m = _RE_SOHIEU.search(ten or "")
    return m.group(0) if m else ""


def doc_loai(ten):
    t = (ten or "").strip()
    for k in _LOAI:
        if t.startswith(k):
            return k
    if "Hiến pháp" in t:
        return "Hiến pháp"
    return None


def clean_name(ten):
    """Cắt tên văn bản về phần lõi (giữ năm/số hiệu)."""
    s = (ten or "").strip()
    s = re.sub(r"\s*\([^)]*\)", "", s)                               # bỏ (…) đóng ngoặc, GIỮ phần sau (vd năm)
    s = re.sub(r"\s*\([^)]*$", "", s, flags=re.S)                    # bỏ "(…" không đóng ngoặc tới hết
    s = re.sub(r"\s*\).*$", "", s, flags=re.S)                       # ")" lạc (đóng ngoặc thừa) -> cắt từ đó
    s = re.split(r"\s+(?:và|hoặc|cùng)\s+" + _VBT + r"\b", s)[0]     # "... và <văn bản khác>"
    s = re.split(r"\s*,\s*" + _VBT + r"\b", s)[0]
    s = re.split(r"\s+(?:và|hoặc)\s+" + _CLAUSE + r"\b", s)[0]       # "và <mệnh đề>"
    s = re.split(r"\s*,\s*" + _CLAUSE + r"\b", s)[0]                 # ", <mệnh đề>"
    s = re.split(r"\s+(?:với|nếu|thì|nhằm|đã được|quy định tại|trong quá trình|sau đó|không có|"
                 r"có hiệu lực|có giá trị|nhưng|đối với|và thời điểm|ngoài ra|đồng thời|kể từ|"
                 r"trừ|vì)\b", s)[0]
    s = re.split(r"\s+(?:tại|theo)\s+(?:Điều|khoản|điểm|Chương|Mục|Phụ lục|" + _VBT + r")\b", s)[0]
    s = re.sub(r"[\s,;:.\-–\"'’)(]+$", "", s).strip()               # bỏ dấu/ngoặc/nháy thừa cuối
    while True:                                                      # lặp bỏ TỪ LẺ vô nghĩa cuối
        s2 = re.sub(r"\s+(?:và|của|hoặc|cùng|tại|theo|thì|là|do|khi|mà|đã|đang|được|có|không|"
                    r"sau|đó|nếu|các|những|người|việc|với|thuộc|nay|vẫn|chỉ|phải|sẽ|quy|định|"
                    r"hiện|hành|nêu|gồm|từ|số|năm)$", "", s).strip()
        s2 = re.sub(r"[\s,;:.\-–\"'’)(]+$", "", s2).strip()
        if s2 == s:
            break
        s = s2
    return s or (ten or "").strip()


def ten_score(ten):
    """Điểm 'độ tốt' của một tên để chọn bản canonical khi gộp trùng
    (ưu tiên: có số hiệu > có năm > dài hơn)."""
    return (1 if so_hieu(ten) else 0,
            1 if re.search(r"\b(?:19|20)\d{2}\b", ten or "") else 0,
            len(ten or ""))


def doc_key(ten, sh=None):
    """Khóa gộp trùng: số hiệu (nếu có) else tên đã làm sạch (bỏ dấu)."""
    sh = sh or so_hieu(ten)
    if sh:
        return "sh:" + re.sub(r"\s+", "", sh.lower())
    return "tn:" + re.sub(r"\s+", " ", strip_dia((ten or "").lower())).strip()
