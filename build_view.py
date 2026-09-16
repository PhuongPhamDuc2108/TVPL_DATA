# -*- coding: utf-8 -*-
"""
Dựng trang GIAO DIỆN RIÊNG (độc lập) để:
  - Xem câu hỏi CÒN hiệu lực, trích Văn bản/Điều/Khoản/Điểm.
  - ĐỐI CHIẾU đáp án: cột trái = danh sách; cột phải = 2 ô (đáp án JSON vs đáp án AI
    dán vào). Khi dán đáp án AI, tự tách căn cứ pháp lý và so khớp với đáp án JSON.

Đọc  : cau_hoi_con_hieu_luc.json
Xuất : view_hieu_luc.html  (self-contained, mở trực tiếp)
"""
import json, re, sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

SRC = "cau_hoi_con_hieu_luc.json"
OUT = "view_hieu_luc.html"

data = json.load(open(SRC, encoding="utf-8"))

RE_DIEU  = re.compile(r'Điều\s+(\d+[A-Za-zđ]?)', re.I)
RE_KHOAN = re.compile(r'khoản\s+(\d+)', re.I)
RE_DIEM  = re.compile(r'điểm\s+([A-Za-zđ])\b', re.I)

def parse_date(s):
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', s or "")
    return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else ""

slim = []
for i, r in enumerate(data):
    cc = r.get("can_cu", "") or ""
    dieu = RE_DIEU.search(cc)
    slim.append({
        "i": i,
        "lv": r.get("linh_vuc", ""), "ng": r.get("nguon", ""),
        "date": r.get("ngay", ""), "d": parse_date(r.get("ngay", "")),
        "t": r.get("tieu_de", ""), "q": r.get("cau_hoi", ""),
        "a": r.get("dap_an", ""), "vb": r.get("van_ban", "") or "(không rõ)",
        "cc": cc, "dieu": dieu.group(1) if dieu else "",
        "khoan": RE_KHOAN.findall(cc), "diem": [x.lower() for x in RE_DIEM.findall(cc)],
        "tt": r.get("trang_thai", ""), "gc": r.get("ghi_chu_hieu_luc", ""),
        "url": r.get("url", ""),
    })

slim.sort(key=lambda x: x["d"], reverse=True)
for k, s in enumerate(slim): s["i"] = k  # index ổn định sau khi sắp

n_vb = len({s["vb"] for s in slim})
n_lv = len({s["lv"] for s in slim})
payload = json.dumps(slim, ensure_ascii=False).replace("</", "<\\/")

HTML = r"""<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đối chiếu đáp án — câu hỏi còn hiệu lực</title>
<style>
:root{
  --bg:#f6f7f9;--panel:#fff;--ink:#1f2430;--muted:#6b7280;--line:#e5e7eb;
  --brand:#1d4ed8;--brand-weak:#eaf0ff;--ok:#0f766e;--ok-weak:#e6f5f2;
  --warn:#b45309;--warn-weak:#fdf1df;--bad:#b91c1c;--bad-weak:#fdeaea;
  --chip:#f1f3f5;--shadow:0 1px 2px rgba(0,0,0,.06);
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1216;--panel:#171b21;--ink:#e7e9ee;--muted:#9aa3af;--line:#2a2f37;
  --brand:#6ea8fe;--brand-weak:#1b2740;--ok:#5eead4;--ok-weak:#123230;
  --warn:#fbbf24;--warn-weak:#3a2c12;--bad:#fca5a5;--bad-weak:#3a1a1a;
  --chip:#232830;--shadow:none;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,"Segoe UI",Roboto,Arial,sans-serif}
header{position:sticky;top:0;z-index:20;background:var(--panel);border-bottom:1px solid var(--line);padding:12px 18px}
h1{margin:0;font-size:17px}
.sub{color:var(--muted);font-size:12.5px;margin-top:3px}
.wrap{max-width:1500px;margin:0 auto;padding:12px 18px 40px}
.tabs{display:flex;gap:8px;align-items:center;margin:6px 0 12px}
.tab{padding:6px 13px;border:1px solid var(--line);border-radius:999px;background:var(--panel);cursor:pointer;font-size:14px}
.tab.on{background:var(--brand);color:#fff;border-color:var(--brand)}
.btn{padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);cursor:pointer;font-size:13.5px}
.btn:hover{border-color:var(--brand)}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.controls input,.controls select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 9px;font-size:13.5px}
.controls input[type=search]{min-width:220px;flex:1}
.count{color:var(--muted);font-size:13px;align-self:center}

/* split layout */
.split{display:grid;grid-template-columns:minmax(320px,40%) 1fr;gap:14px;align-items:start}
@media(max-width:900px){.split{grid-template-columns:1fr}}
.listcol{display:flex;flex-direction:column;gap:8px;max-height:calc(100vh - 190px);overflow:auto;padding-right:4px}
.row{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;cursor:pointer;box-shadow:var(--shadow)}
.row:hover{border-color:var(--brand)}
.row.sel{border-color:var(--brand);background:var(--brand-weak)}
.row .rt{font-weight:600;font-size:14px;margin-bottom:5px}
.row .rmeta{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:11.5px;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--ink);white-space:nowrap}
.chip.vb{background:var(--brand-weak);color:var(--brand);font-weight:600}
.chip.dieu{background:var(--ok-weak);color:var(--ok);font-weight:600}
.chip.khoan,.chip.diem{background:var(--warn-weak);color:var(--warn)}
.chip.lv{color:var(--muted)}
.more{text-align:center;color:var(--muted);padding:10px;font-size:13px}

/* compare panel */
.cmpcol{position:sticky;top:150px}
.cmp{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:var(--shadow)}
.cmp .ph{color:var(--muted);text-align:center;padding:40px 10px}
.cmp h3{margin:0 0 4px;font-size:16px}
.cmp .cbody{color:var(--muted);font-size:13.5px;margin-bottom:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:1150px){.grid2{grid-template-columns:1fr}}
.box{border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column;min-height:180px}
.box-h{padding:8px 11px;font-weight:600;font-size:13.5px;border-bottom:1px solid var(--line);background:var(--chip)}
.box-h.json{color:var(--ok)} .box-h.ai{color:var(--brand)}
.box-ans{padding:11px;font-size:13.5px;white-space:pre-wrap;max-height:300px;overflow:auto}
.box textarea{border:0;resize:vertical;min-height:200px;max-height:400px;padding:11px;font:13.5px/1.55 inherit;background:transparent;color:var(--ink);outline:none;width:100%}
.cites{border-top:1px dashed var(--line);padding:9px 11px;background:var(--bg)}
.cites .lbl{font-size:11.5px;color:var(--muted);margin:2px 0 4px}
.cites .chips{display:flex;flex-wrap:wrap;gap:5px}
.cites .empty{color:var(--muted);font-size:12px;font-style:italic}

.verdict{margin-top:14px;border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--bg)}
.verdict h4{margin:0 0 8px;font-size:14px}
.vrow{display:flex;flex-wrap:wrap;gap:6px;align-items:baseline;margin:6px 0}
.vrow .k{font-size:12.5px;color:var(--muted);min-width:74px}
.chip.match{background:var(--ok-weak);color:var(--ok);border:1px solid var(--ok)}
.chip.only-json{background:var(--warn-weak);color:var(--warn);border:1px dashed var(--warn)}
.chip.only-ai{background:var(--bad-weak);color:var(--bad);border:1px dashed var(--bad)}
.score{font-size:13px;margin-top:6px}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
.badge.g{background:var(--ok-weak);color:var(--ok)} .badge.r{background:var(--bad-weak);color:var(--bad)}
.badge.b{background:var(--brand-weak);color:var(--brand)} .badge.a{background:var(--warn-weak);color:var(--warn)}
.gauge{height:9px;border-radius:6px;background:var(--chip);overflow:hidden;margin:5px 0}
.gauge>span{display:block;height:100%}
.evalrow{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:13px}
.evalrow .k{min-width:120px;color:var(--muted)}
.evalrow .v{font-variant-numeric:tabular-nums;font-weight:600;min-width:44px;text-align:right}
.linkrow{margin-top:10px;font-size:13px}.linkrow a{color:var(--brand)}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}
th{background:var(--chip);position:sticky;top:64px}
.dieulist{color:var(--muted);font-size:13px}
.hidden{display:none}
mark{background:#ffe58a;color:#111;border-radius:2px}
</style>
</head><body>
<header>
  <h1>Đối chiếu đáp án — Câu hỏi CÒN hiệu lực</h1>
  <div class="sub">__N__ câu · __NVB__ văn bản · __NLV__ lĩnh vực · Chọn câu bên trái → dán đáp án AI bên phải để tách căn cứ &amp; đối chiếu</div>
</header>
<div class="wrap">
  <div class="tabs">
    <div class="tab on" data-tab="list" onclick="switchTab('list')">📋 Danh sách &amp; đối chiếu</div>
    <div class="tab" data-tab="agg" onclick="switchTab('agg')">📊 Thống kê theo văn bản</div>
    <button class="btn" style="margin-left:auto" onclick="exportCSV()">⬇ Xuất CSV</button>
  </div>
  <div class="controls" id="ctl">
    <input type="search" id="q" placeholder="Tìm tiêu đề / câu hỏi / căn cứ…" oninput="render()">
    <select id="lv" onchange="render()"><option value="">— Mọi lĩnh vực —</option></select>
    <select id="vb" onchange="onVb()"><option value="">— Mọi văn bản —</option></select>
    <select id="dieu" onchange="render()"><option value="">— Mọi Điều —</option></select>
    <select id="sort" onchange="render()"><option value="new">Mới nhất trước</option><option value="old">Cũ nhất trước</option></select>
    <span class="count" id="count"></span>
  </div>

  <div id="listView" class="split">
    <div id="list" class="listcol"></div>
    <div class="cmpcol"><div class="cmp" id="cmp"><div class="ph">← Chọn một câu hỏi bên trái để đối chiếu đáp án.</div></div></div>
  </div>
  <div id="agg" class="hidden"></div>
</div>

<script id="DATA" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('DATA').textContent);
const CAP = 200;
let tab='list', selId=null;

/* ---------- filter options ---------- */
(function(){
  const lv=[...new Set(DATA.map(d=>d.lv).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'vi'));
  const vc={}; DATA.forEach(d=>vc[d.vb]=(vc[d.vb]||0)+1);
  const vb=Object.keys(vc).sort((a,b)=>vc[b]-vc[a]);
  const L=document.getElementById('lv'),V=document.getElementById('vb');
  lv.forEach(x=>L.add(new Option(x,x)));
  vb.forEach(x=>V.add(new Option(`${x} (${vc[x]})`,x)));
})();

function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function hl(s,t){s=esc(s);if(!t)return s;try{return s.replace(new RegExp('('+t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','ig'),'<mark>$1</mark>');}catch(e){return s;}}

/* ================= BỘ TÁCH CĂN CỨ PHÁP LÝ ================= */
const DOCT='(?:Bộ luật|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết|Quyết định|Pháp lệnh|Hiến pháp|Văn bản hợp nhất)';
function normDoc(s){
  s=s.replace(/\s+/g,' ').replace(/^của\s+/i,'').trim().replace(/[.,;:)]+$/,'');
  const m=s.match(new RegExp('('+DOCT+')\\s+(?:số\\s+)?(\\d+)\\/(\\d{4})(?:\\/([A-ZĐ][A-ZĐ0-9\\-]*))?','i'));
  if(m) return `${m[1]} ${m[2]}/${m[3]}${m[4]?'/'+m[4]:''}`;
  return s.replace(/\s+năm\s+/i,' ');
}
// DANH SÁCH TÊN LUẬT/BỘ LUẬT đã biết (khớp cứng) — tránh nhánh tên-trơn tham lam vơ đuôi
const NAMES=['Bộ luật Tố tụng dân sự','Bộ luật Tố tụng hình sự','Bộ luật Dân sự','Bộ luật Hình sự','Bộ luật Lao động',
 'Luật Trật tự, an toàn giao thông đường bộ','Luật Giao thông đường bộ','Luật Đường bộ',
 'Luật Hôn nhân và gia đình','Luật Kinh doanh bất động sản','Luật Bảo hiểm xã hội','Luật Bảo hiểm y tế',
 'Luật Sở hữu trí tuệ','Luật Xử lý vi phạm hành chính','Luật Quốc tịch Việt Nam',
 'Luật Người lao động Việt Nam đi làm việc ở nước ngoài','Luật Thi hành án dân sự','Luật Thi hành án hình sự',
 'Luật Thi hành tạm giữ, tạm giam','Luật Tố tụng hành chính','Luật Đất đai','Luật Nhà ở','Luật Doanh nghiệp',
 'Luật Cư trú','Luật Hộ tịch','Luật Thương mại','Luật Xây dựng','Luật Việc làm','Luật Căn cước','Luật Công chứng',
 'Luật Giáo dục','Luật Khiếu nại','Luật Tố cáo','Luật Dược','Luật Trọng tài thương mại','Luật Lý lịch tư pháp',
 'Luật An toàn thực phẩm','Luật Thuế thu nhập cá nhân','Luật Thuế thu nhập doanh nghiệp','Luật Thuế giá trị gia tăng',
 'Luật Quản lý thuế','Luật Đấu thầu','Hiến pháp'];
// Trả: {docs:Set, arts:[{dieu,khoan,diem,label,key}]}
function extractCites(text){
  const res={docs:new Set(), arts:[], artKeys:new Set()};
  if(!text) return res;
  const t=(' '+text+' ').replace(/\s+/g,' '), tl=t.toLowerCase();
  // 1) văn bản có SỐ HIỆU (Nghị định/Thông tư/Luật số .../QH..)
  let m, reNum=new RegExp(DOCT+'\\s+(?:số\\s+)?\\d+\\/\\d{4}(?:\\/[A-ZĐ][A-ZĐ0-9\\-]*)?','gi');
  while((m=reNum.exec(t))) res.docs.add(normDoc(m[0]));
  // 2) TÊN luật đã biết (khớp cứng) + kèm NĂM nếu đứng ngay sau
  for(const nm of NAMES){
    const nl=nm.toLowerCase(); let i=0;
    while((i=tl.indexOf(nl,i))>=0){
      const after=t.slice(i+nm.length, i+nm.length+11);
      const ym=after.match(/^\s+(?:năm\s+)?((?:19|20)\d{2})/);
      res.docs.add(ym?nm+' '+ym[1]:nm);
      i+=nm.length;
    }
  }
  // 3) trích dẫn ĐIỀU/KHOẢN/ĐIỂM (chỉ lấy điều-khoản, không đoán văn bản ở đây)
  let reA=new RegExp('(?:điểm\\s+([a-zđ])\\s*[,;.]?\\s*)?(?:khoản\\s+(\\d+)\\s*[,;.]?\\s*)?Điều\\s+(\\d+[a-zđ]?)','gi');
  while((m=reA.exec(t))){
    const diem=m[1]||'', khoan=m[2]||'', dieu=m[3];
    const label='Điều '+dieu+(khoan?' · Khoản '+khoan:'')+(diem?' · Điểm '+diem:'');
    const key=('điều '+dieu+(khoan?' k'+khoan:'')+(diem?' đ'+diem:'')).toLowerCase();
    if(!res.artKeys.has(key)){res.artKeys.add(key); res.arts.push({dieu,khoan,diem,label,key});}
  }
  // bỏ "Điều N" trơn nếu đã có "Điều N · Khoản/Điểm..." cùng Điều
  const withSub=new Set(res.arts.filter(a=>a.khoan||a.diem).map(a=>a.dieu));
  res.arts=res.arts.filter(a=>(a.khoan||a.diem)||!withSub.has(a.dieu));
  // bỏ tên-trơn trùng bản đã có năm ("Luật Đất đai" ⊂ "Luật Đất đai 2024")
  let docs=[...res.docs];
  docs=docs.filter(d=>!docs.some(o=>o!==d && o.toLowerCase().startsWith(d.toLowerCase()+' ')));
  res.docs=new Set(docs);
  return res;
}
// so khớp văn bản: coi là KHỚP nếu bằng nhau hoặc tên là tiền tố của nhau
// ("Luật Đất đai" ~ "Luật Đất đai 2024"; "Bộ luật Hình sự" ~ "Bộ luật Hình sự 2015")
function docEq(x,list){const a=x.toLowerCase();return list.some(y=>{const b=y.toLowerCase();return a===b||a.startsWith(b)||b.startsWith(a);});}

/* ===== TƯƠNG ĐỒNG NỘI DUNG (cosine từ khóa, chạy offline) ===== */
const VN_STOP=new Set('và của là có cho các một những này đó thì mà với để khi nếu hoặc tại theo về trong ra vào đã sẽ bị cũng như nên do vì bởi tuy nhưng hay còn nữa rất quá lại đang người việc từ đến trên dưới sau trước cùng nhau khác nào thế ấy nó họ tôi bạn mình ông bà anh chị em à ạ ơi nhé thôi vậy sao gì đâu được thể cần theo tại đối tuy_nhiên trường hợp'.split(' '));
function toks(s){return (s||'').toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(w=>w.length>1 && !VN_STOP.has(w));}
function cosine(a,b){
  const ta={},tb={}; a.forEach(w=>ta[w]=(ta[w]||0)+1); b.forEach(w=>tb[w]=(tb[w]||0)+1);
  let dot=0,na=0,nb=0; for(const k in ta){na+=ta[k]*ta[k]; if(tb[k])dot+=ta[k]*tb[k];} for(const k in tb)nb+=tb[k]*tb[k];
  return (na&&nb)?dot/Math.sqrt(na*nb):0;
}
function pct(x){return Math.round(x*100);}
function barColor(p){return p>=80?'var(--ok)':p>=60?'var(--brand)':p>=40?'var(--warn)':'var(--bad)';}
function gradeLabel(p){return p>=80?['Tốt','g']:p>=60?['Khá','b']:p>=40?['Trung bình','a']:['Kém','r'];}
function docChips(docs,cls){const a=[...docs];return a.length?a.map(d=>`<span class="chip vb ${cls||''}">📘 ${esc(d)}</span>`).join(''):'<span class="empty">—</span>';}
function artChips(arts,cls){return arts.length?arts.map(x=>`<span class="chip dieu ${cls||''}">${esc(x.label)}</span>`).join(''):'<span class="empty">—</span>';}

/* ================= LIST + FILTER ================= */
function onVb(){
  const vb=document.getElementById('vb').value;
  const pool=vb?DATA.filter(d=>d.vb===vb):DATA;
  const ds=[...new Set(pool.map(d=>d.dieu).filter(Boolean))].sort((a,b)=>(parseInt(a)||0)-(parseInt(b)||0)||a.localeCompare(b));
  const sel=document.getElementById('dieu'); sel.length=1; ds.forEach(x=>sel.add(new Option('Điều '+x,x)));
  render();
}
function current(){
  const term=document.getElementById('q').value.trim().toLowerCase();
  const lv=document.getElementById('lv').value, vb=document.getElementById('vb').value, dieu=document.getElementById('dieu').value;
  let rows=DATA.filter(d=>{
    if(lv&&d.lv!==lv)return false; if(vb&&d.vb!==vb)return false; if(dieu&&d.dieu!==dieu)return false;
    if(term&&!((d.t||'').toLowerCase().includes(term)||(d.q||'').toLowerCase().includes(term)||(d.cc||'').toLowerCase().includes(term)))return false;
    return true;
  });
  const s=document.getElementById('sort').value;
  rows.sort((a,b)=>s==='old'?a.d.localeCompare(b.d):b.d.localeCompare(a.d));
  return rows;
}
function render(){
  const rows=current(), term=document.getElementById('q').value.trim();
  document.getElementById('count').textContent=rows.length+' câu';
  if(tab==='agg'){renderAgg(rows);return;}
  const box=document.getElementById('list'), show=rows.slice(0,CAP);
  box.innerHTML=show.map(d=>{
    const di=d.dieu?`<span class="chip dieu">Điều ${d.dieu}</span>`:'';
    const kh=(d.khoan||[]).slice(0,1).map(k=>`<span class="chip khoan">Khoản ${k}</span>`).join('');
    return `<div class="row ${d.i===selId?'sel':''}" onclick="selectQ(${d.i})">
      <div class="rt">${d.t?hl(d.t,term):hl(d.q.slice(0,90),term)}</div>
      <div class="rmeta"><span class="chip lv">${esc(d.lv)}</span><span class="chip">${esc(d.date.slice(-10))}</span>
        <span class="chip vb">📘 ${esc(d.vb)}</span>${di}${kh}</div>
    </div>`;
  }).join('');
  if(rows.length>CAP) box.insertAdjacentHTML('beforeend',`<div class="more">Hiện ${CAP}/${rows.length} câu — thu hẹp bộ lọc.</div>`);
  if(!rows.length) box.innerHTML='<div class="more">Không có câu nào khớp.</div>';
}

/* ================= COMPARE PANEL ================= */
function aiKey(url){return 'ai::'+url;}
function selectQ(i){
  selId=i;
  document.querySelectorAll('.row').forEach(r=>r.classList.remove('sel'));
  render(); // cập nhật highlight
  const d=DATA[i];
  const saved=localStorage.getItem(aiKey(d.url))||'';
  const cmp=document.getElementById('cmp');
  cmp.innerHTML=`
    <h3>${esc(d.t||d.q.slice(0,90))}</h3>
    <div class="cbody">${esc(d.q)}</div>
    <div class="grid2">
      <div class="box">
        <div class="box-h json">📗 Đáp án tham khảo (JSON)</div>
        <div class="box-ans">${esc(d.a)||'<i>(trống)</i>'}</div>
        <div class="cites" id="jsonCites"></div>
      </div>
      <div class="box">
        <div class="box-h ai">🤖 Đáp án AI — dán vào đây</div>
        <textarea id="aiText" placeholder="Dán câu trả lời của AI vào đây… hệ thống sẽ tự tách Điều/Khoản/Điểm và đối chiếu.">${esc(saved)}</textarea>
        <div class="cites" id="aiCites"></div>
      </div>
    </div>
    <div class="verdict" id="verdict"></div>
    <div class="verdict" id="eval"></div>
    <div class="linkrow">Căn cứ (JSON): <b>${esc(d.cc)}</b>${d.url?` · <a href="${esc(d.url)}" target="_blank" rel="noopener">↗ nguồn gốc</a>`:''}</div>
  `;
  document.getElementById('aiText').addEventListener('input', onAI);
  runCompare();
}
function onAI(){
  const d=DATA[selId]; if(!d)return;
  localStorage.setItem(aiKey(d.url), document.getElementById('aiText').value);
  runCompare();
}
function runCompare(){
  const d=DATA[selId]; if(!d)return;
  const J=extractCites(d.a);
  const A=extractCites(document.getElementById('aiText').value);
  document.getElementById('jsonCites').innerHTML=
    `<div class="lbl">Văn bản:</div><div class="chips">${docChips(J.docs)}</div>
     <div class="lbl">Điều/Khoản/Điểm:</div><div class="chips">${artChips(J.arts)}</div>`;
  document.getElementById('aiCites').innerHTML=
    `<div class="lbl">Văn bản:</div><div class="chips">${docChips(A.docs)}</div>
     <div class="lbl">Điều/Khoản/Điểm:</div><div class="chips">${artChips(A.arts)}</div>`;
  // đối chiếu
  const jd=[...J.docs], ad=[...A.docs];
  const dMatch=jd.filter(x=>docEq(x,ad));
  const dOnlyJ=jd.filter(x=>!docEq(x,ad));
  const dOnlyA=ad.filter(x=>!docEq(x,jd));
  const jk=new Map(J.arts.map(x=>[x.key,x.label])), ak=new Map(A.arts.map(x=>[x.key,x.label]));
  const aMatch=[...jk].filter(([k])=>ak.has(k)).map(([,l])=>l);
  const aOnlyJ=[...jk].filter(([k])=>!ak.has(k)).map(([,l])=>l);
  const aOnlyA=[...ak].filter(([k])=>!jk.has(k)).map(([,l])=>l);
  const hasAI=document.getElementById('aiText').value.trim().length>0;
  const okDoc = dOnlyJ.length===0 && dMatch.length>0;
  const okArt = aOnlyJ.length===0 && aMatch.length>0;
  const badge = !hasAI ? '' :
    (okDoc&&okArt ? '<span class="badge g">✔ Khớp các căn cứ chính trong JSON</span>'
                  : '<span class="badge r">✗ Có căn cứ lệch — xem chi tiết</span>');
  const cc=(arr,cls)=>arr.length?arr.map(x=>`<span class="chip ${cls}">${esc(x)}</span>`).join(''):'<span class="empty">—</span>';
  document.getElementById('verdict').innerHTML = !hasAI
    ? '<h4>Đối chiếu</h4><div class="empty" style="color:var(--muted)">Dán đáp án AI để đối chiếu.</div>'
    : `<h4>Đối chiếu &nbsp; ${badge}</h4>
       <div class="vrow"><span class="k">Văn bản</span>
         ${cc(dMatch,'match')} ${cc(dOnlyJ.map(x=>x+' (chỉ JSON)'),'only-json')} ${cc(dOnlyA.map(x=>x+' (chỉ AI)'),'only-ai')}</div>
       <div class="vrow"><span class="k">Điều/Khoản</span>
         ${cc(aMatch,'match')} ${cc(aOnlyJ.map(x=>x+' (chỉ JSON)'),'only-json')} ${cc(aOnlyA.map(x=>x+' (chỉ AI)'),'only-ai')}</div>
       <div class="score">Văn bản khớp <b>${dMatch.length}/${jd.length||0}</b> · Điều-Khoản khớp <b>${aMatch.length}/${jk.size||0}</b> (so với JSON)</div>`;

  // ===== ĐÁNH GIÁ MỨC ĐỘ TRẢ LỜI =====
  const ev=document.getElementById('eval');
  if(!hasAI){ ev.innerHTML=''; return; }
  const parts=[]; if(jd.length) parts.push(dMatch.length/jd.length); if(jk.size) parts.push(aMatch.length/jk.size);
  const citation = parts.length? parts.reduce((a,b)=>a+b,0)/parts.length : null;
  const content = cosine(toks(d.a), toks(document.getElementById('aiText').value));
  const composite = citation!=null ? 0.6*citation + 0.4*content : content;
  const P=pct(composite), [lb,cls]=gradeLabel(P);
  const gauge=(p)=>`<div class="gauge" style="flex:1"><span style="width:${p}%;background:${barColor(p)}"></span></div>`;
  ev.innerHTML=`<h4>Đánh giá mức độ trả lời &nbsp; <span class="badge ${cls}">${lb} • ${P}%</span></h4>
    <div class="evalrow"><span class="k">Điểm tổng hợp</span>${gauge(P)}<span class="v">${P}%</span></div>
    <div class="evalrow"><span class="k">Căn cứ pháp lý ${citation!=null?'':'(JSON không có)'}</span>${gauge(citation!=null?pct(citation):0)}<span class="v">${citation!=null?pct(citation)+'%':'—'}</span></div>
    <div class="evalrow"><span class="k">Tương đồng câu chữ</span>${gauge(pct(content))}<span class="v">${pct(content)}%</span></div>
    <div style="font-size:12px;color:var(--muted);margin-top:8px">
      Điểm tổng hợp = 60% <b>căn cứ pháp lý khớp</b> + 40% <b>tương đồng câu chữ</b> (cosine từ khóa — chỉ đo trùng từ ngữ, KHÔNG hiểu ngữ nghĩa).
      Để chấm ĐÚNG/SAI &amp; đầy đủ về pháp lý, dùng: <button class="btn" style="margin-top:6px" onclick="copyGrade(this)">📋 Sao chép prompt chấm điểm (dán vào AI)</button>
    </div>`;
}
function copyGrade(btn){
  const d=DATA[selId]; if(!d) return;
  const ai=document.getElementById('aiText').value.trim();
  const p=`Bạn là chuyên gia pháp luật Việt Nam. Hãy CHẤM ĐIỂM câu trả lời của một hệ thống AI so với đáp án tham khảo, cho câu hỏi dưới đây. Lưu ý: chỉ công nhận căn cứ pháp lý CÒN HIỆU LỰC (tính đến 2026); nếu AI trích luật đã hết hiệu lực/bị thay thế thì trừ điểm và nêu rõ.

# CÂU HỎI
${d.q}

# ĐÁP ÁN THAM KHẢO (nguồn: ${d.ng||''}; căn cứ: ${d.cc||''})
${d.a}

# CÂU TRẢ LỜI CỦA AI
${ai||'(chưa dán)'}

# YÊU CẦU CHẤM (thang 0-10 mỗi tiêu chí)
1. Đúng căn cứ pháp lý (điều/khoản/văn bản, còn hiệu lực)
2. Đúng kết luận so với đáp án tham khảo
3. Đầy đủ nội dung
4. Không bịa/không sai lệch
Trả về: điểm từng tiêu chí, ĐIỂM TỔNG (0-10), và 2-3 câu nhận xét ngắn chỉ ra điểm lệch quan trọng nhất.`;
  navigator.clipboard.writeText(p).then(()=>{
    const o=btn.textContent; btn.textContent='✓ Đã sao chép'; setTimeout(()=>btn.textContent=o,1500);
  }).catch(()=>{ alert('Không sao chép được — trình duyệt chặn clipboard.'); });
}

/* ================= AGG + MISC ================= */
function renderAgg(rows){
  document.getElementById('listView').classList.add('hidden');
  const w=document.getElementById('agg'); w.classList.remove('hidden');
  const by={}; rows.forEach(d=>{(by[d.vb]=by[d.vb]||{n:0,dieu:{}}); by[d.vb].n++; if(d.dieu)by[d.vb].dieu[d.dieu]=(by[d.vb].dieu[d.dieu]||0)+1;});
  const ks=Object.keys(by).sort((a,b)=>by[b].n-by[a].n);
  let h='<table><thead><tr><th>Văn bản</th><th>Số câu</th><th>Các Điều được viện dẫn (số câu)</th></tr></thead><tbody>';
  ks.forEach(k=>{const ds=Object.keys(by[k].dieu).sort((a,b)=>(parseInt(a)||0)-(parseInt(b)||0));
    h+=`<tr><td><b>${esc(k)}</b></td><td>${by[k].n}</td><td class="dieulist">${esc(ds.map(x=>'Điều '+x+'·'+by[k].dieu[x]).join(' , '))}</td></tr>`;});
  w.innerHTML=h+'</tbody></table>';
}
function switchTab(t){
  tab=t; document.querySelectorAll('.tab').forEach(el=>el.classList.toggle('on',el.dataset.tab===t));
  document.getElementById('listView').classList.toggle('hidden',t!=='list');
  document.getElementById('agg').classList.toggle('hidden',t!=='agg');
  document.getElementById('ctl').classList.remove('hidden');
  render();
}
function exportCSV(){
  const rows=current();
  const head=['linh_vuc','ngay','nguon','van_ban','dieu','khoan','diem','trang_thai','tieu_de','cau_hoi','can_cu','url'];
  const q=s=>'"'+String(s==null?'':s).replace(/"/g,'""').replace(/\r?\n/g,' ')+'"';
  const lines=[head.join(',')];
  rows.forEach(d=>lines.push([d.lv,d.date,d.ng,d.vb,d.dieu,(d.khoan||[]).join('/'),(d.diem||[]).join('/'),d.tt,d.t,d.q,d.cc,d.url].map(q).join(',')));
  const b=new Blob(['\ufeff'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(b); a.download='cau_hoi_'+rows.length+'.csv'; a.click();
}
render();
</script>
</body></html>"""

out = (HTML.replace("__DATA__", payload)
           .replace("__N__", str(len(slim)))
           .replace("__NVB__", str(n_vb))
           .replace("__NLV__", str(n_lv)))
open(OUT, "w", encoding="utf-8").write(out)
print(f"Đã tạo {OUT} — {len(slim)} câu, {n_vb} văn bản, {len(out)//1024} KB")
