from fastapi import FastAPI, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Body
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
import asyncio
import json
import os
import random
import re
import uuid

app = FastAPI(title="LuatVietnam Scraper", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Nguồn dữ liệu: chuyên mục "Luật sư tư vấn" (hỏi đáp cùng chuyên gia) của
# luatvietnam.vn. Trang này KHÔNG có Cloudflare challenge như thuvienphapluat.vn
# nên chỉ cần curl_cffi giả lập TLS fingerprint Chrome là tải được, không cần
# điều khiển trình duyệt thật (nodriver) nữa.
BASE_URL = "https://luatvietnam.vn"
LIST_URL = BASE_URL + "/luat-su-tu-van.html"

# curl_cffi's `impersonate` replicates a real Chrome TLS/JA3 fingerprint.
IMPERSONATE = "chrome120"

EXTRA_HEADERS = {
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Số câu hỏi mỗi trang danh sách. Trang hỗ trợ ?pSize=15/20/30/50 — dùng 50 để
# giảm số request. LƯU Ý: pSize phải đứng TRƯỚC page trong query string, nếu
# không server bỏ qua pSize (đã kiểm chứng: ?page=2&pSize=50 chỉ trả 20 câu).
PAGE_SIZE = 50

# `path` = tên trang lĩnh vực trên luatvietnam.vn (lấy từ sidebar
# https://luatvietnam.vn/luat-su-tu-van.html, dạng /luat-su-tu-van/<path>.html).
CATEGORIES = [
    {"slug": "dat-dai-nha-o", "name": "Đất đai - Nhà ở", "path": "dat-dai-nha-o-3"},
    {"slug": "dan-su", "name": "Dân sự", "path": "dan-su-65"},
    {"slug": "hinh-su", "name": "Hình sự", "path": "hinh-su-66"},
    {"slug": "lao-dong-tien-luong", "name": "Lao động - Tiền lương", "path": "lao-dong-tien-luong-7"},
    {"slug": "doanh-nghiep", "name": "Doanh nghiệp", "path": "doanh-nghiep-24"},
    {"slug": "hon-nhan-gia-dinh", "name": "Hôn nhân gia đình", "path": "hon-nhan-gia-dinh-64"},
    {"slug": "bao-hiem", "name": "Bảo hiểm", "path": "bao-hiem-57"},
    {"slug": "hanh-chinh", "name": "Hành chính", "path": "hanh-chinh-27"},
    {"slug": "thue-phi-le-phi", "name": "Thuế - Phí - Lệ phí", "path": "thue-phi-le-phi-4"},
    {"slug": "giao-thong", "name": "Giao thông", "path": "giao-thong-28"},
    {"slug": "thuong-mai-quang-cao", "name": "Thương mại - Quảng cáo", "path": "thuong-mai-quang-cao-51"},
    {"slug": "tu-phap-ho-tich", "name": "Tư pháp - Hộ tịch", "path": "tu-phap-ho-tich-85"},
    {"slug": "giao-duc-dao-tao-day-nghe", "name": "Giáo dục - Đào tạo - Dạy nghề", "path": "giao-duc-dao-tao-day-nghe-5"},
    {"slug": "can-bo-cong-chuc-vien-chuc", "name": "Cán bộ - Công chức - Viên chức", "path": "can-bo-cong-chuc-vien-chuc-45"},
    {"slug": "cu-tru-ho-khau", "name": "Cư trú - Hộ khẩu", "path": "cu-tru-ho-khau-43"},
]

# Tra cứu nhanh lĩnh vực theo slug.
CATEGORY_BY_SLUG = {c["slug"]: c for c in CATEGORIES}


# Retry config cho lỗi 429 (Too Many Requests) từ trang gốc.
MAX_RETRIES = 5
BACKOFF_BASE = 2.0   # giây; lần chờ = BACKOFF_BASE * 2**(lần thử) -> 2, 4, 8, 16...
BACKOFF_CAP = 60.0   # trần thời gian chờ mỗi lần (giây)


async def fetch_page(client: AsyncSession, url: str, referer: str = None) -> str:
    """Fetch a page and return HTML content.

    Tự động thử lại với exponential backoff khi gặp 429 (và 503). Nếu server
    trả về header `Retry-After` thì tôn trọng giá trị đó.
    """
    headers = dict(EXTRA_HEADERS)
    if referer:
        headers["Referer"] = referer

    for attempt in range(MAX_RETRIES + 1):
        response = await client.get(url, headers=headers, timeout=30.0, allow_redirects=True)

        if response.status_code in (429, 503) and attempt < MAX_RETRIES:
            # Ưu tiên Retry-After nếu có, ngược lại dùng backoff luỹ thừa.
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait = float(retry_after)
            else:
                wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
            await asyncio.sleep(wait)
            continue

        response.raise_for_status()
        return response.text

    # Hết số lần thử mà vẫn bị chặn.
    response.raise_for_status()
    return response.text


def category_page_url(category: dict, page: int = 1) -> str:
    """URL trang danh sách câu hỏi của 1 lĩnh vực, phân trang bằng ?pSize&page.

    pSize phải đứng trước page (server bỏ qua pSize nếu đặt sau page).
    """
    url = f"{BASE_URL}/luat-su-tu-van/{category['path']}.html?pSize={PAGE_SIZE}"
    if page > 1:
        url += f"&page={page}"
    return url


def parse_question_list(html_content: str) -> list:
    """Trích danh sách {url, title, date} từ HTML trang danh sách lĩnh vực.

    Mỗi câu hỏi là 1 khối div.hoi-dap-post gồm: tiêu đề h3.article-hoi-dap > a
    (link ...-<id>-faqs.html), lĩnh vực p.meta-hoi-dap, ngày p.tag-hoi-dap.
    """
    soup = BeautifulSoup(html_content, "lxml")
    links = []
    for post in soup.select("div.hoi-dap-post"):
        title_link = post.select_one("h3.article-hoi-dap a")
        if not title_link:
            continue
        href = title_link.get("href", "")
        if not href or not href.endswith("-faqs.html"):
            continue
        date_el = post.select_one("p.tag-hoi-dap .time-date")
        links.append({
            "url": BASE_URL + href if href.startswith("/") else href,
            "title": title_link.get_text(strip=True),
            "date": date_el.get_text(strip=True) if date_el else "",
        })
    return links


async def get_question_links(client: AsyncSession, category: dict, page: int = 1) -> list:
    """Lấy danh sách link câu hỏi của 1 lĩnh vực (trang thứ `page`)."""
    html_content = await fetch_page(client, category_page_url(category, page), referer=LIST_URL)
    return parse_question_list(html_content)


# --- Trích dẫn pháp lý: tìm MỘT căn cứ chính xác nhất cho mỗi câu hỏi ---

# Chữ thường/chữ hoa tiếng Việt (regex [A-Z] không phủ được chữ có dấu như Ư, Đ).
_VN_LOWER = (
    "a-zàáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệ"
    "ìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
)
_VN_UPPER = (
    "A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆ"
    "ÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ"
)
# Văn bản có SỐ HIỆU (rất cụ thể): Nghị định 100/2019/NĐ-CP, Thông tư 12/2023/TT-BYT,
# Nghị quyết 254/2025/QH15..., kèm năm nếu có. Hậu tố cho phép chữ số (QH15).
_DOC_NUM = (
    r"(?:Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết|Quyết định|"
    r"Pháp lệnh|Văn bản hợp nhất)\s+(?:số\s+)?\d+[/-]?\d*(?:[/-][A-ZĐ][A-ZĐ0-9\-]*)*(?:\s+\d{4})?"
)
# Năm ban hành (chỉ nhận 19xx/20xx để không nhầm với số điều/khoản).
_YEAR = r"(?:19|20)\d{2}"
# Phần TÊN văn bản (sau "Bộ luật/Luật/Pháp lệnh"): không chứa số/dấu câu mạnh;
# cho phép dấu phẩy KHI theo sau là chữ thường (phần nối của tên, ví dụ
# "Luật Thi hành tạm giữ, tạm giam...").
_NAME_BODY = (
    r"[" + _VN_UPPER + r"](?:[^,.;:\n0-9]|,(?=\s+[" + _VN_LOWER + r"]))" r"{2,90}?"
)
# Văn bản có TÊN, dừng ở hư từ/động từ hoặc dấu câu. "\s+," bắt được dấu phẩy
# bị tách rời khỏi tên do tên văn bản là 1 link riêng ("Luật Đất đai 2024 , cụ
# thể..."); dấu phẩy DÍNH liền chỉ dừng khi theo sau là chữ hoa (trích dẫn mới).
_DOC_NAME_STOP = (
    r"(?:Bộ luật|Luật|Pháp lệnh)\s+" + _NAME_BODY +
    r"(?:\s+(?:năm\s+)?" + _YEAR + r")?"
    r"(?=\s+(?:quy định|sửa đổi|bổ sung|bao gồm|hiện hành|thì|là|gồm|"
    r"nêu|về|khi|do|cho|tại|theo|được|cụ thể|như sau|hướng dẫn|áp dụng)\b"
    r"|\s*[.;:\n]|\s+,|,\s+[" + _VN_UPPER + r"]|$)"
)
# Văn bản có TÊN + NĂM: năm ban hành là điểm kết thúc CỨNG, không cần biết sau
# đó là gì ("Luật Đất đai 2024, cụ thể như sau:" -> "Luật Đất đai 2024").
_DOC_NAME_YEAR = (
    r"(?:Bộ luật|Luật|Pháp lệnh)\s+" + _NAME_BODY +
    r"\s+(?:năm\s+)?" + _YEAR + r"\b"
)
# Văn bản có TÊN + SỐ HIỆU: "Luật Đất đai số 31/2024/QH15".
_DOC_NAME_NUM = (
    r"(?:Bộ luật|Luật|Pháp lệnh)\s+" + _NAME_BODY +
    r"\s+số\s+\d+[/-]\d+(?:[/-][A-ZĐ][A-ZĐ0-9\-]*)?"
)
# Thứ tự ưu tiên: số hiệu ngay sau loại văn bản > tên + số hiệu > tên + điểm
# dừng chuẩn > tên + năm (vét những ca tên bị hỏng điểm dừng như "2024 , cụ thể").
_DOC = (
    f"(?:{_DOC_NUM}|{_DOC_NAME_NUM}|{_DOC_NAME_STOP}|{_DOC_NAME_YEAR}"
    f"|Hiến pháp(?:\\s+(?:năm\\s+)?{_YEAR})?)"
)
# Phần điều/khoản/điểm. Cho phép cả thứ tự "điểm c, khoản 2, Điều 10" (có phẩy).
_ART = r"(?:điểm\s+[a-zđ],?\s+)?(?:khoản\s+\d+,?\s+)?Điều\s+\d+[a-zđ]?"
# Trích dẫn ĐẦY ĐỦ = điều/khoản + văn bản (liền nhau).
_RE_FULL_CITATION = re.compile(f"({_ART}\\s+(?:của\\s+)?{_DOC})")
_RE_ARTICLE = re.compile(f"({_ART})")
_RE_DOC = re.compile(_DOC)
_RE_CANCU = re.compile(r"[Cc]ăn cứ")


def _clean_cite(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    # Bỏ liên từ thừa dính cuối trích dẫn ("...Bộ luật Hình sự và" -> bỏ "và").
    return re.sub(r"\s+(?:và|hoặc|cùng|của)$", "", s)


def _nearest_doc(t: str, art_start: int, art_end: int) -> str:
    """Tìm tên văn bản gần vị trí điều/khoản nhất trong đoạn (ưu tiên đứng ngay sau)."""
    docs = [(m.start(), _clean_cite(m.group(0))) for m in _RE_DOC.finditer(t)]
    if not docs:
        return ""
    adjacent = [d for d in docs if 0 <= d[0] - art_end <= 3]
    if adjacent:
        return adjacent[0][1]
    docs.sort(key=lambda d: min(abs(d[0] - art_start), abs(d[0] - art_end)))
    nearest_pos, nearest_doc = docs[0]
    if min(abs(nearest_pos - art_start), abs(nearest_pos - art_end)) <= 150:
        return nearest_doc
    return ""


def dominant_doc(text: str) -> str:
    """Văn bản được viện dẫn nhiều nhất trong cả bài (dùng để gắn cho điều 'mồ côi').

    Ưu tiên văn bản có số hiệu; nếu hòa thì lấy cái xuất hiện sớm nhất.
    """
    counts = {}
    order = {}
    for i, m in enumerate(_RE_DOC.finditer(re.sub(r"\s+", " ", text or ""))):
        d = _clean_cite(m.group(0))
        counts[d] = counts.get(d, 0) + 1
        order.setdefault(d, i)
    if not counts:
        return ""
    def key(d):
        return (counts[d], bool(re.search(r"\d+[/-]\d+", d)), -order[d])
    return max(counts, key=key)


def best_reference(text: str, fallback_doc: str = "") -> str:
    """Trả về MỘT trích dẫn ĐẦY ĐỦ, chính xác nhất cho đoạn trả lời.

    Dạng "[điểm..] [khoản..] Điều .. <tên văn bản đầy đủ>", ví dụ:
    "khoản 2 Điều 63 Luật Thi hành tạm giữ, tạm giam và cấm đi khỏi nơi cư trú 2025".

    Ưu tiên trích dẫn ĐẦY ĐỦ (điều liền văn bản) nằm ngay sau "Căn cứ", cụ thể hơn
    (có điểm/khoản) và xuất hiện sớm. Nếu không có trích dẫn liền kề thì ghép điều
    gần "Căn cứ" nhất với văn bản gần nó nhất, cuối cùng dùng `fallback_doc` (văn bản
    chủ đạo của cả bài) cho điều "mồ côi". Rỗng nếu đoạn không viện dẫn điều nào.
    """
    t = re.sub(r"\s+", " ", text or "")
    cancu_pos = [m.start() for m in _RE_CANCU.finditer(t)]

    def near_cancu(pos: int) -> bool:
        return any(0 <= pos - c <= 80 for c in cancu_pos)

    def specificity(cit: str) -> int:
        return ("điểm" in cit) + ("khoản" in cit)

    # 1) Trích dẫn đầy đủ (điều/khoản + văn bản liền kề) — đáng tin nhất.
    full = [(m.start(), _clean_cite(m.group(1))) for m in _RE_FULL_CITATION.finditer(t)]
    if full:
        full.sort(key=lambda x: (not near_cancu(x[0]), -specificity(x[1]), x[0]))
        return full[0][1]

    # 2) Không có trích dẫn liền kề: ghép điều gần "Căn cứ" nhất với văn bản gần nhất.
    articles = [(m.start(), m.end(), _clean_cite(m.group(1))) for m in _RE_ARTICLE.finditer(t)]
    if not articles:
        return ""
    articles.sort(key=lambda a: (not near_cancu(a[0]), -specificity(a[2]), a[0]))
    start, end, cit = articles[0]
    doc = _nearest_doc(t, start, end) or fallback_doc
    return f"{cit} {doc}".strip()


# Selector các khối quảng cáo / rác cần loại khỏi nội dung trước khi lấy text.
# luatvietnam.vn chèn quảng cáo trong div.advHolder giữa bài trả lời.
_AD_SELECTORS = (
    '.advHolder', '[class*="viewAds"]', '[class*="ads-"]', '[class*="-ads"]',
    '[class*="adsbygoogle"]', '[class*="google-auto-placed"]',
    '.ad-label-container', 'script', 'style', 'ins', 'iframe', 'noscript',
)
# Chú thích ảnh chèn giữa nội dung: "(Hình từ Internet)", "(Hình minh họa)",
# "(Hình ảnh minh họa)", "(Ảnh từ Internet)"... CHỈ khớp đúng các biến thể này để
# không xóa nhầm cụm hợp lệ như "(Hình thức xử phạt bổ sung)".
_RE_IMG_CAPTION = re.compile(
    r"\s*\(\s*(?:Hình|Ảnh)(?:\s*ảnh)?\s*(?:từ\s*Internet|minh\s*h[oọ][aạ])\s*\)",
    re.IGNORECASE,
)


def clean_text(t: str) -> str:
    """Dọn text: bỏ chú thích ảnh, khoảng trắng thừa trước dấu câu, dòng trống thừa."""
    if not t:
        return t
    t = _RE_IMG_CAPTION.sub("", t)
    # "Luật Đất đai 2024 , cụ thể" -> "Luật Đất đai 2024, cụ thể" (dấu câu bị
    # tách rời khỏi chữ do tên văn bản/điều luật là link riêng trong HTML).
    t = re.sub(r"[ \t]+([,.;:!?])", r"\1", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def strip_ads(node) -> None:
    """Xóa các khối quảng cáo/script/style khỏi một node BeautifulSoup (tại chỗ)."""
    for junk in node.select(", ".join(_AD_SELECTORS)):
        junk.decompose()


# Nhãn đầu khối câu hỏi/trả lời và các đoạn boilerplate ở đuôi bài trả lời.
_RE_Q_LABEL = re.compile(r"^\s*Câu hỏi:\s*")
# Câu chào đầu thư gửi luật sư: "Xin hỏi LuatVietnam:", "Xin hỏi luatvietnam!"...
# -> bỏ để câu hỏi bắt đầu thẳng vào nội dung.
_RE_Q_GREETING = re.compile(
    r"^\s*Xin\s+hỏi\s+(?:Luat\s*Viet\s*Nam|Luật\s*Việt\s*Nam)\s*[:,.!]?\s*",
    re.IGNORECASE,
)
_RE_A_LABEL = re.compile(r"^\s*Trả lời:\s*")
_RE_ADVISOR = re.compile(r"Được tư vấn bởi")
# "Trên đây là nội dung tư vấn... vui lòng liên hệ 19006192..." -> cắt từ đây.
_BOILERPLATE_START = "Trên đây là nội dung tư vấn"


def extract_question(soup, fallback: str = "") -> str:
    """Nội dung câu hỏi người dùng gửi (khối .entry-hoidap-ls, bỏ nhãn 'Câu hỏi:')."""
    q_el = soup.select_one(".entry-hoidap-ls")
    if not q_el:
        return fallback
    text = _element_text(q_el)
    text = _RE_Q_LABEL.sub("", text)
    text = _RE_Q_GREETING.sub("", text)
    return clean_text(text) or fallback


def _element_text(el) -> str:
    """Lấy text của 1 khối, nối inline (link, b, i...) bằng KHOẢNG TRẮNG để câu
    không bị bẻ dòng giữa chừng; mỗi khối con (p/li/tr...) là 1 dòng riêng.

    get_text("\\n") mặc định xuống dòng ở MỌI ranh giới thẻ, kể cả link giữa câu
    -> "Điều 111\\nLuật Đất đai 2024" -> làm hỏng việc bóc căn cứ pháp lý.
    """
    if el.name in ("blockquote", "ul", "ol", "table", "div"):
        # Khối chứa nhiều đoạn: mỗi đoạn "lá" (không chứa đoạn con) là 1 dòng.
        blocks = [b for b in el.find_all(["p", "li", "tr", "h2", "h3", "h4"])
                  if not b.find(["p", "li", "tr"])]
        if blocks:
            lines = [" ".join(b.get_text(" ", strip=True).split()) for b in blocks]
            return "\n".join(l for l in lines if l)
    return " ".join(el.get_text(" ", strip=True).split())


def extract_answer(body) -> str:
    """Nội dung trả lời của luật sư (khối .the-article-body trong .entry-hoi-dap).

    Bỏ: nhãn "Trả lời:", quảng cáo, đoạn "Xem thêm: ..." (link bài liên quan) và
    toàn bộ phần đuôi từ "Trên đây là nội dung tư vấn..." (boilerplate liên hệ
    tổng đài, thông tin luật sư, lưu ý miễn trừ trách nhiệm).
    """
    strip_ads(body)
    parts = []
    for element in body.children:
        if not hasattr(element, "name") or element.name is None:
            text = str(element).strip()
        else:
            text = _element_text(element)
        if not text:
            continue

        norm = " ".join(text.split())
        if norm.startswith(_BOILERPLATE_START):
            break
        if norm.startswith("Xem thêm"):
            continue
        if _RE_A_LABEL.match(norm):
            text = _RE_A_LABEL.sub("", text)
            if not text.strip():
                continue
        parts.append(text)
    return clean_text("\n".join(parts))


def extract_author(box) -> str:
    """Tên luật sư/đơn vị tư vấn ("Được tư vấn bởi: ..." dưới bài trả lời)."""
    if box is None:
        return ""
    node = box.find(string=_RE_ADVISOR)
    if not node:
        return ""
    holder = node.find_parent(["a", "p", "div"]) or node.parent
    text = " ".join(holder.get_text(" ", strip=True).split())
    return re.sub(r"^Được tư vấn bởi:\s*", "", text)


def parse_detail_page(html_content: str, url: str, listing_title: str = "",
                      listing_date: str = "") -> dict:
    """Parse trang chi tiết 1 câu hỏi trên luatvietnam.vn thành {câu hỏi, trả lời}.

    Bố cục trang: h1.the-article-title (tiêu đề), .the-article-meta (ngày),
    .entry-hoidap-ls (câu hỏi người dùng), .entry-hoi-dap > .the-article-body
    (bài trả lời của luật sư).
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Main title
    h1 = soup.select_one("h1.the-article-title") or soup.select_one("h1")
    main_title = h1.get_text(strip=True) if h1 else listing_title

    # Date (vd: "Thứ Sáu, 26/06/2026, 10:22")
    date_el = soup.select_one(".the-article-meta")
    date_str = date_el.get_text(strip=True) if date_el else listing_date

    # Câu hỏi của người dùng; nếu trang thiếu khối câu hỏi thì dùng tiêu đề.
    question = extract_question(soup, fallback=main_title)

    # Bài trả lời của luật sư.
    answer_box = soup.select_one(".entry-hoi-dap")
    body = answer_box.select_one(".the-article-body") if answer_box else None
    answer = extract_answer(body) if body else ""

    author = extract_author(answer_box)

    # MỘT căn cứ pháp lý chính xác nhất, suy ra từ bài trả lời.
    reference = best_reference(answer, fallback_doc=dominant_doc(answer))

    return {
        "title": main_title,
        "question": question,
        "answer": answer,
        "author": author,
        "date": date_str,
        "url": url,
        "reference": reference,
    }


def make_sse(payload):
    """Create an SSE data line from a dict payload."""
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


@app.get("/api/categories")
async def get_categories():
    """Return list of available legal categories."""
    return JSONResponse(content=CATEGORIES)


# File dataset mặc định nạp sẵn lên /compare.html khi mở trang.
DEFAULT_DATASET = "luatvietnam_dataset.json"


@app.get("/api/default-dataset")
async def default_dataset():
    """Trả nội dung file dataset mặc định (ở thư mục dự án) để giao diện tự nạp."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_DATASET)
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Chưa có " + DEFAULT_DATASET})
    try:
        with open(path, "r", encoding="utf-8") as f:
            return JSONResponse(content=json.load(f))
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Lỗi đọc dataset: " + str(e)})


async def _scrape_events(request: Request, category: str, count: int,
                         randomize: bool, pool_pages: int, exclude_urls: set):
    """Generator SSE cào 1 lĩnh vực.

    - `exclude_urls`: các URL đã thu ở lần chạy trước (checkpoint) -> bỏ qua,
      chỉ cào phần còn thiếu; `count` khi đó là số câu cần thu THÊM.
    - Chủ động kiểm tra client còn kết nối không trước MỖI request tới trang
      gốc: nếu client đã ngắt (Ctrl+C collect.py, đóng tab...) thì dừng cào
      ngay, không chạy ngầm tiếp.
    """
    collected = []
    page = 1
    all_links = []

    cat = CATEGORY_BY_SLUG.get(category)
    if not cat:
        yield make_sse({"type": "error", "message": "Không tìm thấy lĩnh vực: " + category})
        return
    try:
        async with AsyncSession(impersonate=IMPERSONATE) as client:
            # Phase 1: Collect question links
            yield make_sse({"type": "status", "message": "Đang quét danh sách câu hỏi lĩnh vực " + cat["name"] + "..."})

            # count=0 -> LẤY HẾT: quét mọi trang cho tới khi hết câu hỏi.
            collect_all = count <= 0
            # Nếu random, cần quét nhiều trang để tạo pool đủ lớn rồi mới chọn.
            # Nếu không, chỉ cần đủ `count` câu đầu tiên (cộng phần sẽ bị loại
            # vì đã có trong checkpoint để không hụt số lượng).
            if collect_all:
                target_pool = float("inf")
                max_pages = 10 ** 9
            elif randomize:
                target_pool = (count + len(exclude_urls)) * 4
                max_pages = pool_pages
            else:
                target_pool = count + len(exclude_urls)
                max_pages = 10 ** 9

            while len(all_links) < target_pool and page <= max_pages:
                # Client đã ngắt kết nối -> dừng cào ngay, không chạy ngầm.
                if await request.is_disconnected():
                    print(f"[scrape] client ngắt kết nối ở trang {page} ({cat['slug']}), dừng.", flush=True)
                    return
                try:
                    links = await get_question_links(client, cat, page)
                except Exception as e:
                    yield make_sse({"type": "error", "message": "Lỗi khi lấy trang " + str(page) + ": " + str(e)})
                    break

                if not links:
                    yield make_sse({"type": "status", "message": "Hết câu hỏi ở trang " + str(page) + ". Tổng: " + str(len(all_links))})
                    break

                all_links.extend(links)
                yield make_sse({"type": "status", "message": "Trang " + str(page) + ": " + str(len(links)) + " câu hỏi (pool: " + str(len(all_links)) + ")"})

                page += 1
                await asyncio.sleep(0.5)

            # Loại trùng URL (các trang có thể lặp câu hỏi), giữ nguyên thứ tự.
            seen = set()
            unique = []
            for l in all_links:
                if l["url"] not in seen:
                    seen.add(l["url"])
                    unique.append(l)
            all_links = unique

            # Bỏ các câu đã thu ở lần chạy trước (checkpoint) -> chỉ cào phần thiếu.
            if exclude_urls:
                before = len(all_links)
                all_links = [l for l in all_links if l["url"] not in exclude_urls]
                yield make_sse({"type": "status", "message": "Checkpoint: bỏ qua " + str(before - len(all_links)) + " câu đã thu, còn " + str(len(all_links)) + " câu mới"})

            # Lấy HẾT thì giữ nguyên thứ tự; ngược lại random/cắt theo `count`.
            if not collect_all:
                if randomize:
                    random.shuffle(all_links)
                all_links = all_links[:count]
            total = len(all_links)

            yield make_sse({"type": "total", "total": total})

            # Phase 2: Fetch detail for each question
            for i, link_info in enumerate(all_links):
                # Client đã ngắt kết nối -> dừng cào ngay, không chạy ngầm.
                if await request.is_disconnected():
                    print(f"[scrape] client ngắt kết nối ở câu {i + 1}/{total} ({cat['slug']}), dừng.", flush=True)
                    return
                title_preview = link_info["title"][:60]
                progress_msg = "Đang lấy câu hỏi " + str(i + 1) + "/" + str(total) + ": " + title_preview + "..."
                yield make_sse({"type": "progress", "current": i + 1, "total": total, "message": progress_msg})

                try:
                    html_content = await fetch_page(client, link_info["url"], referer=category_page_url(cat))
                    question_data = parse_detail_page(
                        html_content, link_info["url"],
                        listing_title=link_info["title"],
                        listing_date=link_info.get("date", ""),
                    )
                    if not question_data["answer"]:
                        yield make_sse({"type": "error", "message": "Bỏ qua (không tìm thấy phần trả lời): " + link_info["url"]})
                        continue
                    collected.append(question_data)
                    yield make_sse({"type": "question", "index": i + 1, "data": question_data})
                except Exception as e:
                    yield make_sse({"type": "error", "message": "Lỗi câu hỏi " + str(i + 1) + ": " + str(e)})

                # Delay between requests to be respectful
                await asyncio.sleep(1.0)

        done_msg = "Hoàn thành! Đã thu thập " + str(len(collected)) + " câu hỏi mới."
        yield make_sse({"type": "done", "total": len(collected), "message": done_msg})

    except Exception as e:
        yield make_sse({"type": "error", "message": "Lỗi hệ thống: " + str(e)})


def _sse_response(generator):
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/scrape")
async def scrape(
    request: Request,
    category: str = Query(..., description="Category slug"),
    count: int = Query(0, ge=0, le=100000, description="Số câu hỏi cần lấy; 0 = LẤY HẾT (mặc định)"),
    randomize: bool = Query(True, description="Lấy ngẫu nhiên thay vì các câu đầu tiên (chỉ có tác dụng khi count > 0)"),
    pool_pages: int = Query(15, ge=1, le=1000, description="Số trang tối đa quét (bỏ qua khi count=0 -> quét đến hết)"),
):
    """Scrape 1 lĩnh vực, trả SSE stream (dùng cho giao diện web, không resume)."""
    return _sse_response(_scrape_events(request, category, count, randomize, pool_pages, set()))


@app.post("/api/scrape")
async def scrape_resume(request: Request, payload: dict = Body(...)):
    """Như GET /api/scrape nhưng nhận thêm `exclude_urls` (danh sách URL đã thu
    từ checkpoint) trong body JSON -> chỉ cào phần còn thiếu. Dùng cho collect.py
    vì danh sách URL quá dài để nhét vào query string.

    Body: {"category": "...", "count": 0, "randomize": true,
           "pool_pages": 15, "exclude_urls": ["...", ...]}
    """
    category = payload.get("category") or ""
    count = int(payload.get("count") or 0)
    randomize = bool(payload.get("randomize", True))
    pool_pages = int(payload.get("pool_pages") or 15)
    exclude_urls = set(payload.get("exclude_urls") or [])
    return _sse_response(_scrape_events(request, category, count, randomize, pool_pages, exclude_urls))


# External AI chatbot used to generate answers for comparison.
CHATBOT_URL = "http://172.16.10.73:8099/api/v1/chatbot/chat"


@app.post("/api/ai-answer")
async def ai_answer(payload: dict = Body(...)):
    """Proxy tới chatbot AI để sinh câu trả lời (tránh CORS phía trình duyệt).

    Body: {"question": "...", "user_id"?: "...", "session_id"?: "..."}
    Trả về: {"response": "...", "references": [...]}
    """
    question = (payload.get("question") or "").strip()
    if not question:
        return JSONResponse(status_code=400, content={"error": "Thiếu nội dung câu hỏi"})

    body = {
        "messages": [{"role": "user", "content": question}],
        "user_id": payload.get("user_id") or "lvn-eval",
        # Mỗi câu hỏi dùng session riêng để câu trả lời độc lập, không dính ngữ cảnh nhau.
        "session_id": payload.get("session_id") or ("cmp-" + uuid.uuid4().hex[:12]),
    }
    if payload.get("workspace_id"):
        body["workspace_id"] = payload["workspace_id"]

    try:
        async with AsyncSession() as client:
            resp = await client.post(CHATBOT_URL, json=body, timeout=180.0)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "Lỗi gọi chatbot AI: " + str(e)})

    return JSONResponse(content={
        "response": data.get("response", ""),
        "references": data.get("references", []),
    })


# Mount static files LAST so API routes take priority
public_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
if os.path.exists(public_dir):
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    # timeout_graceful_shutdown: khi Ctrl+C, uvicorn mặc định CHỜ VÔ THỜI HẠN các
    # kết nối đang mở (SSE stream không bao giờ tự đóng) -> server "tắt" nhưng vẫn
    # cào ngầm tiếp. Ép đóng mọi kết nối sau 3 giây để Ctrl+C tắt hẳn tiến trình.
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_graceful_shutdown=3)
