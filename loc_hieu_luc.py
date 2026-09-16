# -*- coding: utf-8 -*-
"""
LỌC câu hỏi theo TÌNH TRẠNG HIỆU LỰC của văn bản được viện dẫn.
Chỉ giữ câu dựa trên luật CÒN hiệu lực; loại câu dựa trên luật đã HẾT hiệu lực /
bị thay thế; đánh dấu phần CHƯA XÁC ĐỊNH để tra bổ sung.

Nguồn trạng thái: bảng HIEU_LUC (dưới đây) do người dựng kiểm chứng từ vbpl.vn /
thuvienphapluat.vn / luatvietnam.vn (tra ngày 11/08/2026). Nguyên tắc miền quan
trọng: VĂN BẢN HƯỚNG DẪN của một luật đã bị thay thế thì cũng HẾT hiệu lực.

Đầu ra:
  cau_hoi_con_hieu_luc.json    - GIỮ: luật còn hiệu lực (kể cả đã sửa đổi nhưng còn dùng)
  cau_hoi_het_hieu_luc.json    - LOẠI: luật hết hiệu lực / bị thay thế
  cau_hoi_hieu_luc_mot_phan.json - luật hết hiệu lực MỘT PHẦN (giữ nhưng cần soát điều được trích)
  cau_hoi_chua_xac_dinh.json   - văn bản chưa có trong bảng -> cần tra thêm
  docs_chua_xac_dinh.txt       - danh sách văn bản cần tra (kèm số lần xuất hiện)
  hieu_luc_map.json            - xuất bảng trạng thái ra JSON để tiện dùng/mở rộng
"""
import sys, json, re
from collections import Counter, OrderedDict

# ---- Shim fastapi + import _RE_DOC/_clean_cite từ main.py ----
import types
def _shim():
    def deco(*a, **k):
        def d(f): return f
        return d
    class App:
        def __init__(s,*a,**k): pass
        def add_middleware(s,*a,**k): pass
        def get(s,*a,**k): return deco()
        def post(s,*a,**k): return deco()
        def mount(s,*a,**k): pass
    fa=types.ModuleType("fastapi"); fa.FastAPI=App; fa.Query=lambda *a,**k:None
    fa.Body=lambda *a,**k:None; fa.Request=object
    st=types.ModuleType("fastapi.staticfiles"); st.StaticFiles=lambda *a,**k:None
    rp=types.ModuleType("fastapi.responses"); rp.StreamingResponse=object; rp.JSONResponse=lambda *a,**k:None
    mw=types.ModuleType("fastapi.middleware"); cr=types.ModuleType("fastapi.middleware.cors"); cr.CORSMiddleware=object
    fa.staticfiles=st; fa.responses=rp; fa.middleware=mw
    for n,m in [("fastapi",fa),("fastapi.staticfiles",st),("fastapi.responses",rp),
                ("fastapi.middleware",mw),("fastapi.middleware.cors",cr)]:
        sys.modules[n]=m
_shim()
import main as M
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ============================================================================
# BẢNG TRẠNG THÁI HIỆU LỰC (canonical -> trạng thái)
#   con        = còn hiệu lực
#   con_sd     = còn hiệu lực, đã được sửa đổi/bổ sung (vẫn áp dụng) -> GIỮ
#   het        = hết hiệu lực toàn bộ / bị thay thế -> LOẠI
#   het_phan   = hết hiệu lực MỘT PHẦN -> GIỮ nhưng cần soát điều được trích
# ============================================================================
CON = "con"; CON_SD = "con_sd"; HET = "het"; HET_PHAN = "het_phan"

HIEU_LUC = {
    # --- Bộ luật / luật nền còn hiệu lực ---
    "Bộ luật Dân sự 2015": (CON, ""),
    "Bộ luật Hình sự 2015": (CON_SD, "sửa đổi 2017"),
    "Bộ luật Lao động 2019": (CON, ""),
    "Bộ luật Tố tụng dân sự 2015": (CON, ""),
    "Bộ luật Tố tụng hình sự 2015": (CON, ""),
    "Luật Hôn nhân và gia đình 2014": (CON, ""),
    "Luật Thương mại 2005": (CON_SD, "còn hiệu lực; một số điều bị Luật Quản lý ngoại thương 2017 bãi bỏ"),
    "Luật Sở hữu trí tuệ 2005": (CON_SD, "sửa đổi 2009, 2019, 2022"),
    "Luật Xây dựng 2014": (HET, "thay bằng Luật Xây dựng 2025 (HL 01/7/2026)"),
    "Luật Xây dựng 2025": (CON, "HL 01/7/2026"),
    "Luật Xử lý vi phạm hành chính 2012": (CON_SD, "sửa đổi 2020"),
    "Luật Hộ tịch 2014": (CON, ""),
    "Luật Thi hành án dân sự 2008": (HET, "thay bằng Luật THADS 2025 (số 106/2025, HL 01/7/2026)"),
    "Luật Thi hành án dân sự 2025": (CON, "HL 01/7/2026"),
    "Luật Dược 2016": (CON_SD, "sửa đổi 2024"),
    "Luật Doanh nghiệp 2020": (CON, ""),
    "Luật Cư trú 2020": (CON, ""),
    # --- Luật MỚI (chủ đích test) ---
    "Luật Đất đai 2024": (CON, "HL 01/8/2024"),
    "Luật Nhà ở 2023": (CON, "HL 01/8/2024"),
    "Luật Kinh doanh bất động sản 2023": (CON, "HL 01/8/2024"),
    "Luật Căn cước 2023": (CON, "HL 01/7/2024"),
    "Luật Bảo hiểm xã hội 2024": (CON, "HL 01/7/2025"),
    "Luật Trật tự, an toàn giao thông đường bộ 2024": (CON, "HL 01/1/2025"),
    "Luật Đường bộ 2024": (CON, "HL 01/1/2025"),
    "Luật Công chứng 2024": (CON, "HL 01/7/2025"),
    # --- Nghị định còn hiệu lực ---
    "Nghị định 144/2021/NĐ-CP": (CON_SD, "xử phạt ANTT; phần PCCC bị NĐ 106/2025 thay, phần ANTT/bạo lực GĐ còn hiệu lực"),
    "Nghị định 123/2015/NĐ-CP": (CON_SD, "hướng dẫn Luật Hộ tịch; sửa đổi tới NĐ 18/2026"),
    "Nghị định 23/2015/NĐ-CP": (CON_SD, "chứng thực"),
    "Nghị định 98/2020/NĐ-CP": (CON_SD, "xử phạt thương mại; sửa đổi NĐ 17/2022"),
    "Nghị định 126/2020/NĐ-CP": (CON_SD, "hướng dẫn Luật Quản lý thuế 2019"),
    "Nghị định 101/2024/NĐ-CP": (CON, "đăng ký, cấp sổ đỏ - Luật ĐĐ 2024"),
    "Nghị định 102/2024/NĐ-CP": (CON, "hướng dẫn Luật ĐĐ 2024"),
    "Nghị định 88/2024/NĐ-CP": (CON, "bồi thường, tái định cư"),
    "Nghị định 71/2024/NĐ-CP": (CON, "giá đất"),
    "Nghị định 103/2024/NĐ-CP": (CON, "tiền sử dụng đất, tiền thuê đất"),
    "Nghị định 168/2024/NĐ-CP": (CON, "xử phạt giao thông đường bộ"),
    "Nghị định 145/2020/NĐ-CP": (CON_SD, "hướng dẫn BLLĐ 2019"),
    "Nghị định 12/2022/NĐ-CP": (CON, "xử phạt lao động - BHXH"),
    "Nghị định 01/2021/NĐ-CP": (HET, "đăng ký DN -> thay bằng NĐ 168/2025 (HL 01/7/2025)"),
    "Nghị định 168/2025/NĐ-CP": (CON, "đăng ký doanh nghiệp (HL 01/7/2025)"),
    "Nghị định 62/2015/NĐ-CP": (HET, "hướng dẫn THADS -> thay bằng NĐ 152/2026 (HL 01/7/2026)"),
    # --- Thông tư còn hiệu lực (thuế TNCN) ---
    "Thông tư 111/2013/TT-BTC": (HET, "thuế TNCN -> thay bằng TT 87/2026 (HL 01/7/2026, theo Luật TNCN 2025)"),

    # === HẾT HIỆU LỰC / BỊ THAY THẾ ===
    # Đất đai cũ (Luật ĐĐ 2013 + văn bản hướng dẫn -> thay bằng Luật ĐĐ 2024 & NĐ 2024)
    "Luật Đất đai 2013": (HET, "thay bằng Luật Đất đai 2024"),
    "Nghị định 43/2014/NĐ-CP": (HET, "thay bằng NĐ 101/2024 & 102/2024"),
    "Nghị định 44/2014/NĐ-CP": (HET, "giá đất -> thay bằng NĐ 71/2024"),
    "Nghị định 45/2014/NĐ-CP": (HET, "tiền SDĐ -> thay bằng NĐ 103/2024"),
    "Nghị định 01/2017/NĐ-CP": (HET, "sửa NĐ đất đai cũ"),
    "Nghị định 148/2020/NĐ-CP": (HET, "sửa NĐ đất đai cũ"),
    "Thông tư 23/2014/TT-BTNMT": (HET, "GCN - Luật ĐĐ 2013 -> thay bằng TT 10/2024/TT-BTNMT"),
    "Thông tư 24/2014/TT-BTNMT": (HET, "hồ sơ địa chính - Luật ĐĐ 2013"),
    "Thông tư 25/2014/TT-BTNMT": (HET, "bản đồ địa chính - Luật ĐĐ 2013"),
    # Lao động cũ (BLLĐ 2012 + hướng dẫn -> BLLĐ 2019 & NĐ 145/2020)
    "Bộ luật Lao động 2012": (HET, "thay bằng BLLĐ 2019"),
    "Nghị định 05/2015/NĐ-CP": (HET, "hướng dẫn BLLĐ 2012 -> thay bằng NĐ 145/2020"),
    "Nghị định 148/2018/NĐ-CP": (HET, "sửa NĐ 05/2015 -> thay bằng NĐ 145/2020"),
    "Nghị định 95/2013/NĐ-CP": (HET, "xử phạt LĐ -> thay bằng NĐ 12/2022"),
    "Nghị định 88/2015/NĐ-CP": (HET, "sửa NĐ 95/2013 -> thay bằng NĐ 12/2022"),
    "Thông tư 59/2015/TT-BLĐTBXH": (HET, "hướng dẫn Luật BHXH 2014"),
    "Thông tư 47/2015/TT-BLĐTBXH": (HET, "hướng dẫn BLLĐ 2012"),
    # BHXH cũ
    "Luật Bảo hiểm xã hội 2014": (HET, "thay bằng Luật BHXH 2024 (HL 01/7/2025)"),
    "Nghị định 115/2015/NĐ-CP": (HET, "hướng dẫn Luật BHXH 2014"),
    # Doanh nghiệp cũ
    "Luật Doanh nghiệp 2014": (HET, "thay bằng Luật Doanh nghiệp 2020"),
    "Nghị định 78/2015/NĐ-CP": (HET, "đăng ký DN -> thay bằng NĐ 01/2021"),
    "Nghị định 96/2015/NĐ-CP": (HET, "hướng dẫn Luật DN 2014 -> thay bằng NĐ 47/2021"),
    # Nhà ở cũ
    "Luật Nhà ở 2014": (HET, "thay bằng Luật Nhà ở 2023"),
    "Nghị định 99/2015/NĐ-CP": (HET, "hướng dẫn Luật Nhà ở 2014 -> thay bằng NĐ 95/2024"),
    # Cư trú cũ
    "Luật Cư trú 2006": (HET, "thay bằng Luật Cư trú 2020"),
    # Giao thông cũ
    "Luật Giao thông đường bộ 2008": (HET, "tách thành Luật TTATGTĐB 2024 + Luật Đường bộ 2024"),
    "Nghị định 100/2019/NĐ-CP": (HET, "xử phạt GT -> thay bằng NĐ 168/2024"),
    "Nghị định 171/2013/NĐ-CP": (HET, "xử phạt GT cũ"),
    "Nghị định 46/2016/NĐ-CP": (HET, "xử phạt GT cũ -> NĐ 100/2019 -> NĐ 168/2024"),
    "Thông tư 12/2017/TT-BGTVT": (HET, "đào tạo, sát hạch GPLX - đã chuyển quản lý & thay thế 2025"),
    # An ninh trật tự / căn cước cũ
    "Nghị định 167/2013/NĐ-CP": (HET, "xử phạt ANTT -> thay bằng NĐ 144/2021"),
    "Luật Căn cước công dân 2014": (HET, "thay bằng Luật Căn cước 2023"),
    "Nghị định 05/1999/NĐ-CP": (HET, "CMND -> hết"),
    "Thông tư 15/2014/TT-BCA": (HET, "đăng ký xe -> thay bằng TT 24/2023/TT-BCA"),
    # Viễn thông cũ
    "Nghị định 174/2013/NĐ-CP": (HET, "xử phạt bưu chính - viễn thông -> thay bằng NĐ 15/2020"),
    # Thuế/hóa đơn cũ
    "Thông tư 156/2013/TT-BTC": (HET, "quản lý thuế -> thay bằng TT 80/2021"),
    "Thông tư 39/2014/TT-BTC": (HET, "hóa đơn -> thay bằng NĐ 123/2020 & TT 78/2021"),
    # Bộ luật/luật đời cũ
    "Bộ luật Dân sự 2005": (HET, "thay bằng BLDS 2015"),
    "Bộ luật Hình sự 1999": (HET, "thay bằng BLHS 2015"),
    "Bộ luật Tố tụng hình sự 2003": (HET, "thay bằng BLTTHS 2015"),
    "Bộ luật Tố tụng dân sự 2004": (HET, "thay bằng BLTTDS 2015"),
    "Luật Công chứng 2014": (HET, "thay bằng Luật Công chứng 2024 (HL 01/7/2025)"),
    "Luật Doanh nghiệp 2005": (HET, "thay bằng Luật DN 2014 -> 2020"),
    "Luật Việc làm 2013": (HET, "thay bằng Luật Việc làm 2025 (HL 01/1/2026)"),
    "Nghị định 158/2005/NĐ-CP": (HET, "hộ tịch cũ -> thay bằng NĐ 123/2015"),
    "Nghị định 63/2014/NĐ-CP": (HET, "đấu thầu -> thay bằng NĐ 24/2024 (Luật Đấu thầu 2023)"),
    "Nghị định 47/2014/NĐ-CP": (HET, "bồi thường thu hồi đất - Luật ĐĐ 2013 -> NĐ 88/2024"),
    "Nghị định 31/2013/NĐ-CP": (HET, "ưu đãi người có công -> thay bằng NĐ 131/2021"),
    "Nghị quyết 93/2015/QH13": (HET, "BHXH một lần -> hết khi Luật BHXH 2024 có hiệu lực"),
    # --- thêm: còn hiệu lực ---
    "Hiến pháp 2013": (CON, ""),
    "Nghị định 39/2007/NĐ-CP": (CON, "cá nhân hoạt động TM không phải ĐKKD"),
    # --- Số hiệu LUẬT lớn (nhiều câu trích theo số hiệu) ---
    "Luật 45/2013/QH13": (HET, "= Luật Đất đai 2013"),
    "Luật 31/2024/QH15": (CON, "= Luật Đất đai 2024"),
    "Luật 65/2014/QH13": (HET, "= Luật Nhà ở 2014"),
    "Luật 27/2023/QH15": (CON, "= Luật Nhà ở 2023"),
    "Luật 66/2014/QH13": (HET, "= Luật KDBĐS 2014"),
    "Luật 29/2023/QH15": (CON, "= Luật KDBĐS 2023"),
    "Luật 58/2014/QH13": (HET, "= Luật BHXH 2014"),
    "Luật 41/2024/QH15": (CON, "= Luật BHXH 2024"),
    "Luật 68/2014/QH13": (HET, "= Luật Doanh nghiệp 2014"),
    "Luật 59/2020/QH14": (CON, "= Luật Doanh nghiệp 2020"),
    "Luật 52/2014/QH13": (CON, "= Luật Hôn nhân và gia đình 2014"),
    "Luật 23/2008/QH12": (HET, "= Luật Giao thông đường bộ 2008"),
    "Luật 15/2012/QH13": (CON_SD, "= Luật Xử lý VPHC 2012 (sửa đổi 2020)"),
    "Luật 26/2023/QH15": (CON, "= Luật Căn cước 2023"),
    "Bộ luật 91/2015/QH13": (CON, "= BLDS 2015"),
    "Bộ luật 33/2005/QH11": (HET, "= BLDS 2005"),
    "Bộ luật 100/2015/QH13": (CON_SD, "= BLHS 2015 (sửa đổi 2017)"),
    "Bộ luật 15/1999/QH10": (HET, "= BLHS 1999"),
    "Bộ luật 45/2019/QH14": (CON, "= BLLĐ 2019"),
    "Bộ luật 10/2012/QH13": (HET, "= BLLĐ 2012"),
    "Bộ luật 92/2015/QH13": (CON, "= BLTTDS 2015"),
    "Bộ luật 101/2015/QH13": (CON, "= BLTTHS 2015"),

    # === Nhóm đuôi hay gặp — đã tra/kiểm chứng (11/08/2026) ===
    # -- Thuế: đã có Luật Thuế GTGT 2024 & Luật Thuế TNDN 2025 -> loạt TT thuế cũ HẾT
    "Thông tư 78/2014/TT-BTC": (HET, "thuế TNDN -> thay bằng TT 20/2026 (Luật Thuế TNDN 2025), hết 12/3/2026"),
    "Thông tư 96/2015/TT-BTC": (HET, "sửa TT 78/2014 thuế TNDN -> hết cùng TT 78/2014"),
    "Thông tư 219/2013/TT-BTC": (HET, "thuế GTGT -> thay bằng TT 69/2025, hết 01/7/2025"),
    "Thông tư 92/2015/TT-BTC": (HET, "thuế TNCN hộ KD -> thay bằng TT 40/2021"),
    # -- Nhãn hàng hóa, thương mại
    "Nghị định 89/2006/NĐ-CP": (HET, "nhãn hàng hóa -> thay bằng NĐ 43/2017"),
    "Nghị định 52/2013/NĐ-CP": (CON_SD, "thương mại điện tử; sửa đổi NĐ 85/2021"),
    # -- Vận tải đường bộ
    "Nghị định 86/2014/NĐ-CP": (HET, "kinh doanh vận tải -> thay bằng NĐ 10/2020"),
    "Nghị định 10/2020/NĐ-CP": (HET, "kinh doanh vận tải -> thay bằng NĐ 158/2024 (HL 01/1/2025)"),
    "Nghị định 158/2024/NĐ-CP": (CON, "hoạt động vận tải đường bộ (HL 01/1/2025)"),
    # -- Đất đai hướng dẫn cũ (Luật ĐĐ 2013)
    "Thông tư 02/2015/TT-BTNMT": (HET, "hướng dẫn NĐ 43/2014 - Luật ĐĐ 2013"),
    "Nghị định 102/2014/NĐ-CP": (HET, "xử phạt đất đai - Luật ĐĐ 2013"),
    "Nghị định 47/2014/NĐ-CP": (HET, "bồi thường thu hồi đất - Luật ĐĐ 2013"),
    "Nghị định 187/2013/NĐ-CP": (HET, "xuất nhập khẩu -> thay bằng NĐ 69/2018"),
    # -- Hộ tịch / tư pháp
    "Thông tư 15/2015/TT-BTP": (HET, "hướng dẫn Luật Hộ tịch -> thay bằng TT 04/2020/TT-BTP"),
    "Nghị định 110/2013/NĐ-CP": (HET, "xử phạt bổ trợ tư pháp -> thay bằng NĐ 82/2020"),
    "Nghị định 82/2020/NĐ-CP": (CON, "xử phạt hành chính bổ trợ tư pháp, hôn nhân, hộ tịch"),
    # -- Lao động / BHXH hướng dẫn cũ
    "Nghị định 45/2013/NĐ-CP": (HET, "thời giờ làm việc - BLLĐ 2012 -> thay bằng NĐ 145/2020"),
    "Nghị định 28/2020/NĐ-CP": (HET, "xử phạt lao động -> thay bằng NĐ 12/2022"),
    "Nghị định 143/2018/NĐ-CP": (HET, "BHXH lao động nước ngoài - Luật BHXH 2014"),
    "Nghị định 28/2015/NĐ-CP": (HET, "BH thất nghiệp -> thay bằng NĐ 374/2025 (HL 01/1/2026, Luật Việc làm 2025)"),
    "Nghị định 146/2018/NĐ-CP": (HET, "hướng dẫn BHYT -> NĐ 188/2025 bãi bỏ hầu hết (HL 15/8/2025)"),
    "Nghị định 116/2010/NĐ-CP": (HET, "phụ cấp vùng ĐBKK -> thay bằng NĐ 76/2019"),
    # -- Công chức / căn cước / cư trú cũ
    "Nghị định 161/2018/NĐ-CP": (HET, "tuyển dụng công chức -> thay bằng NĐ 138/2020"),
    "Thông tư 07/2016/TT-BCA": (HET, "hướng dẫn Luật CCCD 2014"),
    "Thông tư 35/2014/TT-BCA": (HET, "hướng dẫn Luật Cư trú 2006"),
    "Nghị định 100/2006/NĐ-CP": (HET, "hướng dẫn BLDS/Luật SHTT cũ về quyền tác giả"),
    "Nghị định 103/2009/NĐ-CP": (HET, "quy chế hoạt động văn hóa -> đã thay thế"),
    # -- Còn hiệu lực
    "Nghị định 10/2022/NĐ-CP": (CON, "lệ phí trước bạ"),
    "Luật Thuế thu nhập cá nhân 2007": (HET, "thay bằng Luật Thuế TNCN 2025 (số 109/2025, HL 01/7/2026)"),
    "Luật Thuế thu nhập cá nhân 2025": (CON, "số 109/2025/QH15 (HL 01/7/2026)"),
    "Thông tư 87/2026/TT-BTC": (CON, "hướng dẫn thuế TNCN 2025 (HL 01/7/2026)"),
    "Luật Thi hành án hình sự 2019": (HET, "thay bằng Luật THAHS 2025 (số 127/2025, HL 01/7/2026)"),
    "Luật Thi hành án hình sự 2025": (CON, "số 127/2025/QH15 (HL 01/7/2026)"),
    "Luật Thi hành tạm giữ, tạm giam và cấm đi khỏi nơi cư trú 2025": (CON, "số 128/2025 (HL 01/7/2026)"),
    "Nghị định 374/2025/NĐ-CP": (CON, "BH thất nghiệp - Luật Việc làm 2025 (HL 01/1/2026)"),
    "Nghị định 152/2026/NĐ-CP": (CON, "hướng dẫn Luật THADS 2025 (HL 01/7/2026)"),
    # -- Xử phạt / chuyên ngành khác
    "Nghị định 91/2019/NĐ-CP": (HET, "xử phạt đất đai - Luật ĐĐ 2013 -> thay bằng NĐ 123/2024"),
    "Nghị định 139/2017/NĐ-CP": (HET, "xử phạt xây dựng -> thay bằng NĐ 16/2022"),
    "Nghị định 16/2022/NĐ-CP": (CON, "xử phạt xây dựng"),
    "Thông tư 33/2017/TT-BTNMT": (HET, "hướng dẫn đất đai - Luật ĐĐ 2013"),
    "Nghị định 15/2020/NĐ-CP": (CON_SD, "xử phạt bưu chính, viễn thông, CNTT; sửa đổi NĐ 14/2022"),
    "Nghị định 123/2020/NĐ-CP": (HET, "hóa đơn, chứng từ -> thay bằng NĐ 254/2026 (HL 01/7/2026)"),
    "Nghị định 254/2026/NĐ-CP": (CON, "hóa đơn, chứng từ điện tử (HL 01/7/2026)"),
    "Luật Khiếu nại 2011": (CON, ""),
    "Luật Tố cáo 2018": (CON, ""),
    "Luật Thi hành tạm giữ, tạm giam 2015": (HET, "thay bằng Luật 128/2025 (HL 01/7/2026)"),
    "Luật 55/2010/QH12": (CON, "= Luật An toàn thực phẩm 2010"),

    # === HẾT MỘT PHẦN (giữ, cần soát điều được trích) ===
    "Luật Sở hữu trí tuệ 2019": (HET_PHAN, "văn bản sửa đổi; tra theo điều"),
}

# --- Tên-TRƠN không năm: suy luận theo NGÀY câu hỏi ---
# name -> (cutoff 'YYYY-MM-DD', trạng thái nếu NGÀY >= cutoff, trạng thái nếu trước, ghi chú)
AMBIG = {
    "Bộ luật Dân sự":        ("0000-00-00", CON, CON, "hiện hành BLDS 2015"),
    "Bộ luật Hình sự":       ("0000-00-00", CON_SD, CON_SD, "hiện hành BLHS 2015"),
    "Bộ luật Lao động":      ("2021-01-01", CON, HET, "BLLĐ 2019 (từ 2021) / trước là BLLĐ 2012"),
    "Bộ luật Tố tụng dân sự":("0000-00-00", CON, CON, "hiện hành BLTTDS 2015"),
    "Bộ luật Tố tụng hình sự":("0000-00-00", CON, CON, "hiện hành BLTTHS 2015"),
    "Luật Hôn nhân và gia đình":("0000-00-00", CON, CON, "hiện hành 2014"),
    "Luật Sở hữu trí tuệ":   ("0000-00-00", CON_SD, CON_SD, "hiện hành 2005 sửa đổi"),
    "Luật Thương mại":       ("0000-00-00", CON, CON, "hiện hành 2005"),
    "Luật Đất đai":          ("2024-08-01", CON, HET, "Luật ĐĐ 2024 (từ 01/8/2024) / trước là 2013"),
    "Luật Nhà ở":            ("2024-08-01", CON, HET, "Luật Nhà ở 2023 (từ 01/8/2024) / trước 2014"),
    "Luật Kinh doanh bất động sản":("2024-08-01", CON, HET, "KDBĐS 2023 / trước 2014"),
    "Luật Doanh nghiệp":     ("2021-01-01", CON, HET, "Luật DN 2020 / trước 2014"),
    "Luật Cư trú":           ("2021-07-01", CON, HET, "Luật Cư trú 2020 / trước 2006"),
    "Luật Bảo hiểm xã hội":  ("2025-07-01", CON, HET, "Luật BHXH 2024 / trước 2014"),
    "Luật Giao thông đường bộ":("2025-01-01", CON, HET, "Luật Đường bộ/TTATGT 2024 / trước 2008"),
    "Luật Căn cước":         ("0000-00-00", CON, CON, "Luật Căn cước 2023"),
    "Luật Công chứng":       ("2025-07-01", CON, HET, "Luật Công chứng 2024 / trước 2014"),
    "Luật Việc làm":         ("2026-01-01", CON, HET, "Luật Việc làm 2025 / trước 2013"),
    "Hiến pháp":             ("0000-00-00", CON, CON, "Hiến pháp 2013"),
    "Luật Tố tụng hành chính":("0000-00-00", CON, CON, "hiện hành 2015"),
    "Luật Thi hành án hình sự":("2026-07-01", CON, HET, "Luật THAHS 2025 (từ 01/7/2026) / trước là 2019"),
    "Luật Bảo hiểm y tế":    ("0000-00-00", CON_SD, CON_SD, "2008 sửa đổi 2014, 2024"),
    "Luật Người lao động Việt Nam đi làm việc ở nước ngoài":("0000-00-00", CON, CON, "hiện hành 2020"),
    "Luật Quốc tịch Việt Nam":("0000-00-00", CON_SD, CON_SD, "2008 sửa đổi 2014, 2024"),
    "Luật Quốc tịch":        ("0000-00-00", CON_SD, CON_SD, "Luật Quốc tịch VN 2008 sửa đổi"),
    "Luật Trọng tài thương mại":("0000-00-00", CON, CON, "hiện hành 2010"),
    "Luật Giáo dục":         ("2020-07-01", CON, HET, "Luật Giáo dục 2019 / trước 2005"),
    "Luật Thuế thu nhập cá nhân":("2026-07-01", CON, HET, "Luật TNCN 2025 (từ 01/7/2026) / trước là 2007"),
    "Luật Lý lịch tư pháp":  ("0000-00-00", CON_SD, CON_SD, "hiện hành 2009"),
    "Luật Sở hữu trí tuệ":   ("0000-00-00", CON_SD, CON_SD, "2005 sửa đổi 2009/2019/2022"),
    "Luật Xây dựng":         ("2026-07-01", CON, HET, "Luật Xây dựng 2025 (từ 01/7/2026) / trước là 2014"),
    "Luật Xử lý vi phạm hành chính":("0000-00-00", CON_SD, CON_SD, "2012 sửa đổi 2020"),
    "Luật Thi hành án dân sự":("2026-07-01", CON, HET, "Luật THADS 2025 (từ 01/7/2026) / trước là 2008"),
    "Luật Hộ tịch":          ("0000-00-00", CON, CON, "hiện hành 2014"),
    "Luật Doanh nghiệp":     ("2021-01-01", CON, HET, "Luật DN 2020 / trước 2014"),
}

# Với văn bản "Tên + NĂM tường minh" thuộc dòng luật AMBIG: chỉ các NĂM dưới đây là
# bản CÒN hiệu lực (bản gốc + các luật sửa đổi). Năm KHÁC = bản CŨ đã bị thay -> HẾT.
# (sửa lỗi: "Bộ luật Dân sự 1995", "Bộ luật Hình sự 2009"... trước đây bị nhận nhầm là còn)
VALID_YEARS = {
    "bộ luật dân sự": {"2015"},
    "bộ luật hình sự": {"2015", "2017"},
    "bộ luật lao động": {"2019"},
    "bộ luật tố tụng dân sự": {"2015"},
    "bộ luật tố tụng hình sự": {"2015"},
    "luật hôn nhân và gia đình": {"2014"},
    "luật sở hữu trí tuệ": {"2005", "2009", "2019", "2022"},
    "luật thương mại": {"2005"},
    "luật đất đai": {"2024"},
    "luật nhà ở": {"2023"},
    "luật kinh doanh bất động sản": {"2023"},
    "luật doanh nghiệp": {"2020"},
    "luật cư trú": {"2020", "2021"},
    "luật bảo hiểm xã hội": {"2024"},
    "luật giao thông đường bộ": set(),
    "luật căn cước": {"2023"},
    "luật công chứng": {"2024"},
    "luật việc làm": {"2025"},
    "hiến pháp": {"2013"},
    "luật tố tụng hành chính": {"2015"},
    "luật thi hành án hình sự": {"2025"},
    "luật bảo hiểm y tế": {"2008", "2014", "2024"},
    "luật người lao động việt nam đi làm việc ở nước ngoài": {"2020"},
    "luật quốc tịch việt nam": {"2008", "2014", "2024"},
    "luật quốc tịch": {"2008", "2014", "2024"},
    "luật trọng tài thương mại": {"2010"},
    "luật giáo dục": {"2019"},
    "luật thuế thu nhập cá nhân": {"2025"},
    "luật lý lịch tư pháp": {"2009"},
    "luật xây dựng": {"2025"},
    "luật xử lý vi phạm hành chính": {"2012", "2020"},
    "luật thi hành án dân sự": {"2025"},
    "luật hộ tịch": {"2014"},
}

KEEP = {CON, CON_SD}   # trạng thái được GIỮ khi lọc

# ---- helpers ----
SOHIEU = re.compile(r'(\d+)\s*/\s*(\d{4})(?:\s*/\s*([A-ZĐ][A-ZĐ0-9\-]*))?')
# tra cứu KHÔNG phân biệt hoa/thường
HIEU_LUC_CF = {k.casefold(): v for k, v in HIEU_LUC.items()}
AMBIG_CF = {k.casefold(): v for k, v in AMBIG.items()}
# chỉ mục bỏ hậu tố số hiệu -> khớp cả khi trích thiếu "/NĐ-CP", "/QH13"...
HIEU_LUC_NOSFX = {re.sub(r'/([A-ZĐ][A-ZĐ0-9\-]*)$', '', k).casefold(): v
                  for k, v in HIEU_LUC.items() if '/' in k}
def canon(d):
    d0 = re.sub(r'\bnăm\s+', '', d); d0 = re.sub(r'\s+', ' ', d0).strip()
    d0 = re.sub(r'\s*/\s*', '/', d0)  # "43/ 2014" -> "43/2014"
    tm = re.match(r'(Bộ luật|Luật|Nghị định|Nghị quyết|Thông tư liên tịch|Thông tư|Quyết định|Pháp lệnh|Hiến pháp|Văn bản hợp nhất)', d0)
    typ = tm.group(1) if tm else ''
    m = SOHIEU.search(d0)
    if m:
        base = f'{typ} {m.group(1)}/{m.group(2)}'.strip()
        return f'{base}/{m.group(3)}' if m.group(3) else base
    name = re.sub(r'\b(19|20)\d{2}\b', '', d0).strip(' )(.,;:"\'-'); name = re.sub(r'\s+', ' ', name)
    name = name.replace('Luật Dân sự', 'Bộ luật Dân sự').replace('Bộ luật Bộ luật', 'Bộ luật')
    name = re.sub(r'Hôn nhân và [Gg]ia đình', 'Hôn nhân và gia đình', name)
    name = re.sub(r'Hôn nhân gia đình', 'Hôn nhân và gia đình', name)
    # mở rộng viết tắt thường gặp trong tên văn bản
    name = re.sub(r'\bBHXH\b', 'Bảo hiểm xã hội', name)
    name = re.sub(r'\bBHYT\b', 'Bảo hiểm y tế', name)
    name = re.sub(r'\bBHTN\b', 'Bảo hiểm thất nghiệp', name)
    name = re.sub(r'\bGTGT\b', 'giá trị gia tăng', name)
    name = re.sub(r'\bTNCN\b', 'thu nhập cá nhân', name)
    name = re.sub(r'\bTNDN\b', 'thu nhập doanh nghiệp', name)
    y = re.search(r'\b(19|20)\d{2}\b', d0)
    return f'{name} {y.group(0)}'.strip() if y else name

def _strip_suffix(s):
    return re.sub(r'/([A-ZĐ][A-ZĐ0-9\-]*)$', '', s)

def doc_of(ref):
    if not ref: return None
    m = M._RE_DOC.search(ref)
    return M._clean_cite(m.group(0)) if m else None

def qdate(q):
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', q.get('date','') or '')
    return f'{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}' if m else ""

def status_of(ref, date_iso):
    doc = doc_of(ref)
    if not doc:
        return ("chua_ro", "", "(không rút được văn bản)")
    c = canon(doc)
    cf = c.casefold()
    if cf in HIEU_LUC_CF:
        st, note = HIEU_LUC_CF[cf]; return (st, c, note)
    # thử bỏ hậu tố số hiệu ("Nghị định 43/2014" ~ "Nghị định 43/2014/NĐ-CP")
    nsfx = _strip_suffix(cf)
    if '/' in cf and nsfx in HIEU_LUC_NOSFX:
        st, note = HIEU_LUC_NOSFX[nsfx]; return (st, c, note)
    ym = re.search(r'\b((?:19|20)\d{2})\b', c)   # năm tường minh (nếu có)
    base = re.sub(r'\s+\d{4}$', '', c).casefold()
    # 1) tên-TRƠN không năm -> suy theo NGÀY câu hỏi
    if not ym and cf in AMBIG_CF:
        cutoff, aft, bef, note = AMBIG_CF[cf]
        st = aft if (date_iso and date_iso >= cutoff) else bef
        return (st, c, note + (f" [ngày {date_iso}]" if date_iso else " [thiếu ngày -> giả định cũ]"))
    # 2) tên + NĂM tường minh thuộc dòng AMBIG -> đối chiếu VALID_YEARS
    if ym and base in AMBIG_CF:
        Y = ym.group(1)
        cutoff, aft, bef, note = AMBIG_CF[base]
        valid = VALID_YEARS.get(base)
        if valid is not None:
            st = aft if Y in valid else HET
            tag = "bản hiện hành" if Y in valid else "BẢN CŨ đã bị thay"
            return (st, c, f"{note} [năm {Y}: {tag}]")
        st = aft if (date_iso and date_iso >= cutoff) else bef
        return (st, c, note)
    return ("chua_ro", c, "chưa có trong bảng")

# ---- chạy ----
buckets = {"con": [], "het": [], "het_phan": [], "chua_ro": []}
undef_docs = Counter()
stt = Counter()
for fn, src in [("luatvietnam_dataset.json","luatvietnam.vn"),
                ("hethongphapluat_dataset.json","hethongphapluat.com")]:
    d = json.load(open(fn, encoding="utf-8"))
    for c in d.get("categories", []):
        for q in c.get("questions", []):
            di = qdate(q)
            st, canon_doc, note = status_of(q.get("reference",""), di)
            stt[st] += 1
            rec = OrderedDict([
                ("linh_vuc", c.get("name","")), ("nguon", src), ("ngay", q.get("date","")),
                ("tieu_de", (q.get("title","") or "").strip()),
                ("cau_hoi", (q.get("question") or q.get("title","")).strip()),
                ("dap_an", q.get("answer","").strip()),
                ("can_cu", q.get("reference","")),
                ("van_ban", canon_doc), ("trang_thai", st), ("ghi_chu_hieu_luc", note),
                ("url", q.get("url","")),
            ])
            key = "con" if st in KEEP else ("het_phan" if st==HET_PHAN else ("het" if st==HET else "chua_ro"))
            buckets[key].append(rec)
            if st == "chua_ro" and canon_doc:
                undef_docs[canon_doc] += 1

# sắp theo ngày mới nhất
def pdk(r):
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', r["ngay"] or "")
    return (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else (0,0,0)
for k in buckets: buckets[k].sort(key=pdk, reverse=True)

json.dump(buckets["con"], open("cau_hoi_con_hieu_luc.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(buckets["het"], open("cau_hoi_het_hieu_luc.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(buckets["het_phan"], open("cau_hoi_hieu_luc_mot_phan.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(buckets["chua_ro"], open("cau_hoi_chua_xac_dinh.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
with open("docs_chua_xac_dinh.txt","w",encoding="utf-8") as f:
    for doc,n in undef_docs.most_common():
        f.write(f"{n}\t{doc}\n")
# xuất bảng ra JSON để tiện dùng/mở rộng
export = {k: {"trang_thai": v[0], "ghi_chu": v[1]} for k,v in HIEU_LUC.items()}
json.dump(export, open("hieu_luc_map.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

total = sum(stt.values())
print(f"Tổng câu: {total}")
print(f"  CÒN hiệu lực (giữ):        {len(buckets['con'])}  ({stt['con']} con + {stt['con_sd']} con_sửa_đổi)")
print(f"  HẾT hiệu lực (loại):       {len(buckets['het'])}")
print(f"  HẾT một phần (soát lại):   {len(buckets['het_phan'])}")
print(f"  CHƯA xác định (cần tra):   {len(buckets['chua_ro'])}")
print(f"\n{len(undef_docs)} văn bản chưa xác định (top 15):")
for doc,n in undef_docs.most_common(15):
    print(f"  {n:4d}  {doc}")
