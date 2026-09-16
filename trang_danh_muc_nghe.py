# -*- coding: utf-8 -*-
"""Sinh trang HTML tra cứu Danh mục nghề NNĐHNH (TT 11/2020 + TT 19/2023).

Đầu vào: data/danh_muc_nghe_nndhnh.json do danh_muc_nghe.py sinh ra.
Đầu ra:  public/danh_muc_nghe.html - một file tĩnh, nhúng sẵn dữ liệu, tìm kiếm
         tiếng Việt không dấu và lọc theo lĩnh vực / loại điều kiện lao động.

Chạy:  venv\\Scripts\\python.exe trang_danh_muc_nghe.py
"""
import sys, io, json, os, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

THU_MUC = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(THU_MUC, 'data', 'danh_muc_nghe_nndhnh.json')
OUT = os.path.join(THU_MUC, 'public', 'danh_muc_nghe.html')

rows = json.load(open(SRC, encoding='utf-8'))

groups = []
index = {}
for r in rows:
    vb = 'TT11' if '11/2020' in r['van_ban'] else 'TT19'
    key = (vb, r['so_linh_vuc'])
    if key not in index:
        index[key] = len(groups)
        groups.append({'vb': vb, 'n': r['so_linh_vuc'],
                       't': r['linh_vuc'], 'items': []})
    loai = r['dieu_kien_lao_dong'].replace('Loại ', '')
    groups[index[key]]['items'].append([loai, r['stt'],
                                        r['ten_nghe_cong_viec'],
                                        r['dac_diem_dieu_kien_lao_dong']])

cnt = collections.Counter(r['dieu_kien_lao_dong'] for r in rows)
n_iv, n_v, n_vi = cnt['Loại IV'], cnt['Loại V'], cnt['Loại VI']
n_tt11 = sum(1 for r in rows if '11/2020' in r['van_ban'])
n_tt19 = len(rows) - n_tt11
data = json.dumps(groups, ensure_ascii=False, separators=(',', ':'))


def vn(n):
    return f'{n:,}'.replace(',', '.')


HTML = """<title>Danh mục nghề nặng nhọc</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bitter:wght@500;600;700&family=Be+Vietnam+Pro:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>
:root{
  --ground:#EEF1F2; --surface:#FFFFFF; --surface-2:#F7F9F9;
  --ink:#111A1F; --ink-2:#3D4E58; --muted:#66787F;
  --rule:#D8E0E3; --rule-soft:#E6ECEE;
  --accent:#125E6E; --accent-soft:#DCEBEE; --accent-ink:#0C4653;
  --sev4:#5F7480; --sev4-bg:#E7ECEF;
  --sev5:#9A6208; --sev5-bg:#F6ECD9;
  --sev6:#9B2C1B; --sev6-bg:#F7E1DD;
  --shadow:0 1px 2px rgba(17,26,31,.05),0 8px 24px -18px rgba(17,26,31,.35);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0F1417; --surface:#171E22; --surface-2:#1C2429;
    --ink:#E7EDEF; --ink-2:#B9C7CD; --muted:#8D9DA5;
    --rule:#2A353B; --rule-soft:#222C31;
    --accent:#5FB3C7; --accent-soft:#14343C; --accent-ink:#9FD4E0;
    --sev4:#9FB1B9; --sev4-bg:#242E33;
    --sev5:#E0A63F; --sev5-bg:#33280F;
    --sev6:#E8705B; --sev6-bg:#3A1E18;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --ground:#0F1417; --surface:#171E22; --surface-2:#1C2429;
  --ink:#E7EDEF; --ink-2:#B9C7CD; --muted:#8D9DA5;
  --rule:#2A353B; --rule-soft:#222C31;
  --accent:#5FB3C7; --accent-soft:#14343C; --accent-ink:#9FD4E0;
  --sev4:#9FB1B9; --sev4-bg:#242E33;
  --sev5:#E0A63F; --sev5-bg:#33280F;
  --sev6:#E8705B; --sev6-bg:#3A1E18;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -18px rgba(0,0,0,.8);
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"Be Vietnam Pro",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1080px; margin:0 auto; padding:0 20px 72px}

/* ---------- header ---------- */
header{border-bottom:1px solid var(--rule); background:var(--surface)}
.head-in{max-width:1080px; margin:0 auto; padding:30px 20px 24px;
  display:flex; flex-direction:column; gap:18px}
.eyebrow{font-size:11.5px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--muted); font-weight:600}
h1{font-family:Bitter,Georgia,serif; font-weight:600; font-size:clamp(26px,4vw,38px);
  line-height:1.15; margin:0; text-wrap:balance; letter-spacing:-.01em}
.sub{margin:0; max-width:64ch; color:var(--ink-2); font-size:15px}
.sources{display:flex; flex-wrap:wrap; gap:8px}
.src{display:flex; align-items:baseline; gap:8px; padding:7px 12px;
  border:1px solid var(--rule); border-radius:3px; background:var(--surface-2);
  font-size:13px}
.src b{font-weight:600; font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12.5px}
.src span{color:var(--muted)}
.tally{display:flex; flex-wrap:wrap; gap:0; border:1px solid var(--rule);
  border-radius:3px; overflow:hidden; background:var(--surface-2)}
.tally div{flex:1 1 130px; padding:11px 14px; border-right:1px solid var(--rule)}
.tally div:last-child{border-right:0}
.tally .k{display:block; font-size:11px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); font-weight:600}
.tally .v{font-family:"IBM Plex Mono",ui-monospace,monospace; font-weight:600;
  font-size:19px; font-variant-numeric:tabular-nums}

/* ---------- controls ---------- */
.controls{position:sticky; top:0; z-index:20; background:var(--ground);
  border-bottom:1px solid var(--rule); padding:12px 0 12px; margin-bottom:26px}
.controls-in{max-width:1080px; margin:0 auto; padding:0 20px;
  display:flex; flex-wrap:wrap; gap:10px; align-items:center}
input[type="search"]{flex:1 1 260px; min-width:0; padding:9px 12px; font:inherit;
  font-size:14px; color:var(--ink); background:var(--surface);
  border:1px solid var(--rule); border-radius:3px}
input[type="search"]::placeholder{color:var(--muted)}
select{padding:9px 10px; font:inherit; font-size:13.5px; color:var(--ink);
  background:var(--surface); border:1px solid var(--rule); border-radius:3px;
  max-width:230px}
.seg{display:flex; border:1px solid var(--rule); border-radius:3px; overflow:hidden;
  background:var(--surface)}
.seg button{appearance:none; border:0; border-right:1px solid var(--rule);
  background:transparent; font:inherit; font-size:13px; font-weight:500;
  color:var(--ink-2); padding:9px 12px; cursor:pointer;
  display:flex; align-items:center; gap:6px}
.seg button:last-child{border-right:0}
.seg button:hover{background:var(--surface-2)}
.seg button[aria-pressed="true"]{background:var(--accent-soft); color:var(--accent-ink);
  font-weight:600}
.seg .n{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11.5px;
  font-variant-numeric:tabular-nums; opacity:.75}
:where(button,input,select,a):focus-visible{outline:2px solid var(--accent);
  outline-offset:2px}
.count{margin-left:auto; font-size:13px; color:var(--muted);
  font-variant-numeric:tabular-nums}
.count b{color:var(--ink); font-weight:600}

/* ---------- legend ---------- */
.legend{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
  gap:10px; margin:0 0 28px}
.legend div{padding:12px 14px; background:var(--surface); border:1px solid var(--rule);
  border-left:3px solid var(--sev4); border-radius:3px; font-size:13px; color:var(--ink-2)}
.legend .l5{border-left-color:var(--sev5)}
.legend .l6{border-left-color:var(--sev6)}
.legend b{display:block; color:var(--ink); font-weight:600; font-size:13.5px}

/* ---------- groups ---------- */
.group{background:var(--surface); border:1px solid var(--rule); border-radius:4px;
  margin-bottom:14px; box-shadow:var(--shadow); overflow:hidden}
.group > summary{list-style:none; cursor:pointer; padding:14px 16px;
  display:flex; align-items:baseline; gap:12px; background:var(--surface-2);
  border-bottom:1px solid var(--rule-soft)}
.group > summary::-webkit-details-marker{display:none}
.group:not([open]) > summary{border-bottom-color:transparent}
.group > summary:hover{background:var(--accent-soft)}
.gnum{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12px;
  font-weight:600; color:var(--accent); min-width:52px}
.gtitle{font-family:Bitter,Georgia,serif; font-weight:600; font-size:15.5px;
  flex:1; text-wrap:balance; letter-spacing:.005em}
.gmeta{font-size:11.5px; color:var(--muted); font-variant-numeric:tabular-nums;
  white-space:nowrap}
.gvb{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:10.5px;
  color:var(--muted); border:1px solid var(--rule); border-radius:2px; padding:1px 5px}

ol{list-style:none; margin:0; padding:0}
li{display:grid; grid-template-columns:44px 34px 1fr; gap:0 12px;
  padding:11px 16px; border-bottom:1px solid var(--rule-soft); align-items:baseline}
li:last-child{border-bottom:0}
.sev{grid-row:span 2; align-self:start; margin-top:2px; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px; font-weight:600; text-align:center; padding:2px 0; border-radius:2px}
.s4{color:var(--sev4); background:var(--sev4-bg)}
.s5{color:var(--sev5); background:var(--sev5-bg)}
.s6{color:var(--sev6); background:var(--sev6-bg)}
.stt{grid-row:span 2; align-self:start; font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:12px; color:var(--muted); text-align:right; font-variant-numeric:tabular-nums}
.ten{font-weight:500; color:var(--ink)}
.dd{font-size:13px; color:var(--muted); margin-top:2px}
mark{background:var(--accent-soft); color:var(--accent-ink); border-radius:2px;
  padding:0 1px}
.empty{padding:48px 20px; text-align:center; color:var(--muted);
  border:1px dashed var(--rule); border-radius:4px; background:var(--surface)}
footer{margin-top:34px; padding-top:18px; border-top:1px solid var(--rule);
  font-size:12.5px; color:var(--muted); max-width:74ch}
footer p{margin:0 0 7px}
@media (max-width:620px){
  li{grid-template-columns:40px 1fr; gap:0 10px}
  .stt{display:none}
  .count{margin-left:0; width:100%}
}
</style>

<header>
  <div class="head-in">
    <div>
      <p class="eyebrow">Thông tư 11/2020/TT-BLĐTBXH · Thông tư 19/2023/TT-BLĐTBXH</p>
      <h1>Danh mục nghề, công việc nặng nhọc, độc hại, nguy hiểm</h1>
    </div>
    <p class="sub">Toàn bộ danh mục hợp nhất từ hai thông tư, trích trực tiếp từ bản
      Công báo. Lọc theo lĩnh vực, theo điều kiện lao động, hoặc tìm bằng tiếng Việt
      không dấu.</p>
    <div class="sources">
      <div class="src"><b>TT 11/2020/TT-BLĐTBXH</b>
        <span>12/11/2020 · hiệu lực 01/3/2021 · __N11__ nghề / 42 lĩnh vực</span></div>
      <div class="src"><b>TT 19/2023/TT-BLĐTBXH</b>
        <span>29/12/2023 · hiệu lực 15/02/2024 · bổ sung __N19__ nghề / 3 lĩnh vực</span></div>
    </div>
    <div class="tally">
      <div><span class="k">Tổng cộng</span><span class="v">__NTOT__</span></div>
      <div><span class="k">Loại IV</span><span class="v">__N4__</span></div>
      <div><span class="k">Loại V</span><span class="v">__N5__</span></div>
      <div><span class="k">Loại VI</span><span class="v">__N6__</span></div>
    </div>
  </div>
</header>

<div class="controls">
  <div class="controls-in">
    <input type="search" id="q" placeholder="Tìm nghề, công việc hoặc đặc điểm…"
           aria-label="Tìm trong danh mục" autocomplete="off">
    <div class="seg" role="group" aria-label="Lọc theo điều kiện lao động">
      <button data-sev="" aria-pressed="true">Tất cả</button>
      <button data-sev="IV" aria-pressed="false">Loại IV <span class="n">__N4__</span></button>
      <button data-sev="V" aria-pressed="false">Loại V <span class="n">__N5__</span></button>
      <button data-sev="VI" aria-pressed="false">Loại VI <span class="n">__N6__</span></button>
    </div>
    <select id="lv" aria-label="Lọc theo lĩnh vực"></select>
    <select id="vb" aria-label="Lọc theo văn bản">
      <option value="">Cả hai thông tư</option>
      <option value="TT11">Chỉ TT 11/2020</option>
      <option value="TT19">Chỉ TT 19/2023 (bổ sung)</option>
    </select>
    <p class="count" id="count"></p>
  </div>
</div>

<div class="wrap">
  <div class="legend">
    <div><b>Điều kiện lao động loại IV</b>Nghề, công việc <em>nặng nhọc, độc hại,
      nguy hiểm</em>.</div>
    <div class="l5"><b>Điều kiện lao động loại V</b>Nghề, công việc <em>đặc biệt</em>
      nặng nhọc, độc hại, nguy hiểm.</div>
    <div class="l6"><b>Điều kiện lao động loại VI</b>Nhóm nặng nhất trong danh mục —
      cũng thuộc nhóm <em>đặc biệt</em>.</div>
  </div>
  <div id="list"></div>
  <footer>
    <p>Nguồn: bản Công báo số 301+302 và 303+304 năm 2021 (TT 11/2020) và Công báo số
      301+302 năm 2024 (TT 19/2023) trên congbao.chinhphu.vn. Số thứ tự được đánh lại
      theo từng lĩnh vực và từng loại điều kiện lao động, đúng như bản gốc.</p>
    <p>Số La Mã lĩnh vực giữ nguyên cách đánh của bản gốc, kể cả các số không chuẩn
      (XXXX, XXXXI, XXXXII). Danh mục nghề nặng nhọc, độc hại, nguy hiểm trong Quân đội
      được quy định riêng tại Thông tư 28/2025/TT-BNV và không nằm trong trang này.</p>
  </footer>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
const GROUPS = JSON.parse(document.getElementById('data').textContent);
const listEl = document.getElementById('list');
const countEl = document.getElementById('count');
const qEl = document.getElementById('q');
const lvEl = document.getElementById('lv');
const vbEl = document.getElementById('vb');
const VBNAME = {TT11:'TT 11/2020', TT19:'TT 19/2023'};
const SEVN = {IV:4, V:5, VI:6};
let sev = '';

const fold = s => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')
  .replace(/đ/g,'d').replace(/Đ/g,'D').toLowerCase();

GROUPS.forEach((g,i) => {
  g.key = g.vb + '|' + g.n;
  g.fold = g.items.map(it => fold(it[2] + ' ' + it[3]));
  const o = document.createElement('option');
  o.value = g.key;
  o.textContent = g.n + '. ' + g.t.slice(0,52) + (g.t.length>52?'…':'') +
    (g.vb==='TT19' ? ' (TT 19)' : '');
  lvEl.append(o);
});
lvEl.prepend(Object.assign(document.createElement('option'),
  {value:'', textContent:'Tất cả lĩnh vực'}));

const esc = s => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function hl(text, needle){
  const out = esc(text);
  if(!needle) return out;
  const f = fold(text), idx = [];
  let p = f.indexOf(needle);
  while(p !== -1 && needle){ idx.push([p, p+needle.length]); p = f.indexOf(needle, p+needle.length); }
  if(!idx.length) return out;
  let res = '', last = 0;
  for(const [a,b] of idx){ res += esc(text.slice(last,a)) + '<mark>' + esc(text.slice(a,b)) + '</mark>'; last = b; }
  return res + esc(text.slice(last));
}

function render(){
  const needle = fold(qEl.value.trim());
  const lv = lvEl.value, vb = vbEl.value;
  let shown = 0, html = '';
  for(const g of GROUPS){
    if(lv && g.key !== lv) continue;
    if(vb && g.vb !== vb) continue;
    const hits = [];
    g.items.forEach((it,i) => {
      if(sev && it[0] !== sev) return;
      if(needle && !g.fold[i].includes(needle)) return;
      hits.push(it);
    });
    if(!hits.length) continue;
    shown += hits.length;
    const open = (needle || lv || sev) ? ' open' : '';
    html += '<details class="group"' + open + '><summary><span class="gnum">' +
      esc(g.n) + '</span><span class="gtitle">' + esc(g.t) +
      '</span><span class="gvb">' + VBNAME[g.vb] + '</span><span class="gmeta">' +
      hits.length + ' nghề</span></summary><ol>' +
      hits.map(it => '<li><span class="sev s' + SEVN[it[0]] + '">' + it[0] +
        '</span><span class="stt">' + it[1] + '</span><span class="ten">' +
        hl(it[2], needle) + '</span><span class="dd">' + hl(it[3], needle) +
        '</span></li>').join('') + '</ol></details>';
  }
  listEl.innerHTML = html || '<p class="empty">Không có nghề, công việc nào khớp bộ lọc.</p>';
  countEl.innerHTML = '<b>' + shown.toLocaleString('vi-VN') + '</b> / ' +
    TOTAL.toLocaleString('vi-VN') + ' nghề, công việc';
}
const TOTAL = GROUPS.reduce((a,g) => a + g.items.length, 0);

document.querySelectorAll('.seg button').forEach(b => b.addEventListener('click', () => {
  sev = b.dataset.sev;
  document.querySelectorAll('.seg button').forEach(x =>
    x.setAttribute('aria-pressed', String(x === b)));
  render();
}));
let t; qEl.addEventListener('input', () => { clearTimeout(t); t = setTimeout(render, 120); });
lvEl.addEventListener('change', render);
vbEl.addEventListener('change', render);
render();
</script>
"""

HTML = (HTML.replace('__DATA__', data)
            .replace('__N11__', vn(n_tt11)).replace('__N19__', vn(n_tt19))
            .replace('__NTOT__', vn(len(rows)))
            .replace('__N4__', vn(n_iv)).replace('__N5__', vn(n_v))
            .replace('__N6__', vn(n_vi)))

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('wrote', OUT, os.path.getsize(OUT))
print('groups', len(groups), 'rows', len(rows))
