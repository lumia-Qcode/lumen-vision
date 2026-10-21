"""HTML/JS component for the multi-camera room: 3D floor plan with live agent messages,
synchronised multi-angle playback with a best-angle pick, and a subject-track ribbon."""
import json

TEMPLATE = r"""
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--ink:#0E1726;--panel:#15223A;--line:#263754;--text:#E6ECF5;--muted:#8A9AB5;--amber:#F2B33D;--red:#E5484D;--orange:#F08C3A;--teal:#3CCB9A;--blue:#7FB2FF}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--text);font:14px/1.45 'IBM Plex Sans',system-ui,sans-serif}
.top{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:14px}
@media(max-width:820px){.top{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px}
.plan-wrap{perspective:1100px;padding:14px 10px 0;overflow:hidden;height:400px;position:relative}
.plan3d{transform:rotateX(34deg) scale(.96);transform-origin:50% 40%;transition:transform 1.2s cubic-bezier(.2,.7,.2,1)}
.plan-title{position:absolute;left:16px;top:10px;font:600 15px 'IBM Plex Sans Condensed',sans-serif;z-index:2}
.plan-title span{display:block;color:var(--muted);font:400 12px 'IBM Plex Sans',sans-serif}
svg text{font-family:'IBM Plex Sans',sans-serif}
.cam circle.core{transition:r .2s}
.cam.active circle.ring{animation:ping .8s ease-out}
@keyframes ping{from{r:10;opacity:.9}to{r:26;opacity:0}}
.log{display:flex;flex-direction:column;height:400px}
.log h3{margin:0;padding:12px 14px 8px;font:600 15px 'IBM Plex Sans Condensed',sans-serif;border-bottom:1px solid var(--line)}
.log h3 span{color:var(--muted);font:400 12px 'IBM Plex Sans',sans-serif;margin-left:6px}
.log ol{list-style:none;margin:0;padding:6px 10px 10px;overflow-y:auto;flex:1;scroll-behavior:smooth}
.log li{padding:7px 8px;border-radius:8px;margin-bottom:4px;animation:in .35s ease both;font-size:13px}
.log li .who{color:var(--muted);font-size:12px}
.log li .who b{color:var(--text);font-weight:500}
.log li.k-VERDICT{background:rgba(242,179,61,.10);border:1px solid rgba(242,179,61,.35)}
.badge{display:inline-block;font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;margin-right:6px;border:1px solid currentColor}
@keyframes in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.verdict{margin-top:14px;padding:14px 16px;display:flex;flex-wrap:wrap;gap:22px;align-items:center}
.verdict .big{font:600 26px 'IBM Plex Sans Condensed',sans-serif}
.verdict .lbl{color:var(--muted);font-size:12px}
.verdict .brief{flex:1 1 320px;color:var(--text);font-size:13.5px;border-left:2px solid var(--amber);padding-left:12px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
.card{padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--panel);transition:border-color .3s, box-shadow .3s}
.card.pick{border-color:var(--amber);box-shadow:0 0 0 1px var(--amber),0 8px 30px rgba(242,179,61,.12)}
.card header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:8px}
.card header b{font:600 14px 'IBM Plex Sans Condensed',sans-serif}
.pickflag{font-size:11px;color:var(--ink);background:var(--amber);border-radius:999px;padding:1px 8px;opacity:0;transition:opacity .3s}
.card.pick .pickflag{opacity:1}
.vp{position:relative;aspect-ratio:16/9;overflow:hidden;border-radius:8px;background:#000}
.vp video{position:absolute;max-width:none}
.box{position:absolute;border:1.5px solid var(--amber);border-radius:3px;box-shadow:0 0 0 1px rgba(0,0,0,.4);transition:all .25s linear}
.ts{position:absolute;left:8px;bottom:6px;font-size:11px;color:#fff;background:rgba(14,23,38,.7);padding:1px 6px;border-radius:4px}
.ribbon{margin-top:12px;padding:12px 14px}
.ribbon h4{margin:0 0 8px;font:600 14px 'IBM Plex Sans Condensed',sans-serif}
.ribbon h4 span{color:var(--muted);font:400 12px 'IBM Plex Sans',sans-serif;margin-left:6px}
.rrow{display:grid;grid-template-columns:150px 1fr;align-items:center;gap:10px;margin:4px 0}
.rrow .nm{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cells{position:relative;display:grid;gap:2px;height:16px}
.cell{border-radius:3px;background:rgba(138,154,181,.10)}
.cell.cut{outline:1.5px solid var(--amber);outline-offset:-1.5px}
.head{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--text);border-radius:1px;pointer-events:none}
.controls{display:flex;gap:8px;margin-top:12px}
button{font:500 13px 'IBM Plex Sans',sans-serif;border-radius:8px;padding:8px 14px;cursor:pointer;border:1px solid var(--line);background:var(--panel);color:var(--text)}
button.primary{background:var(--amber);color:var(--ink);border-color:var(--amber)}
button:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
.status{font-size:11px;font-weight:600}
.empty{color:var(--muted);padding:16px}
@media (prefers-reduced-motion: reduce){.plan3d{transition:none}.log li{animation:none}}
</style>
<div class="top">
  <div class="panel plan-wrap"><div class="plan-title" id="ptitle"></div><div class="plan3d" id="plan3d"></div></div>
  <div class="panel log"><h3>Agent channel<span id="lcount"></span></h3><ol id="log"></ol></div>
</div>
<div id="after" hidden>
  <div class="panel verdict" id="verdict"></div>
  <div class="grid" id="grid"></div>
  <div class="panel ribbon" id="ribbon"></div>
  <div class="controls"><button class="primary" id="play">Pause</button><button id="replay">Replay conversation</button></div>
</div>
<script>
const D = __DATA__;
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const S = 60, W = D.plan.w*S, H = D.plan.h*S;
const KIND = {HELLO:['Hello','#8A9AB5'],REQUEST:['Request','#F2B33D'],REPORT:['Report','#7FB2FF'],VERIFY:['Verify','#F2B33D'],
  CORROBORATE:['Corroborate','#3CCB9A'],NOT_VISIBLE:['Not visible','#C77B7E'],HANDOFF:['Handoff','#F08C3A'],ACQUIRED:['Acquired','#3CCB9A'],
  LOST:['Lost','#E5484D'],TRACK:['Track','#F2B33D'],VERDICT:['Verdict','#F2B33D']};
const STATUS = {reported:['Reported','#7FB2FF'],corroborated:['Corroborated','#3CCB9A'],not_visible:['Out of view','#8A9AB5']};
const name = id => id==='coordinator'?'Coordinator':id==='all'?'All cameras':id==='operator'?'Operator':(D.views.find(v=>v.id===id)||{}).name||id;
const pos = {}; D.views.forEach(v=>pos[v.id]=[v.pos[0]*S, v.pos[1]*S]);
pos.coordinator=[W*0.42, H*0.62]; pos.operator=[W*0.42, H+30];
document.getElementById('ptitle').innerHTML = `${D.room_name}<span>Floor plan schematic. Cones show each camera's field of view.</span>`;

// ---------- floor plan ----------
const ns='http://www.w3.org/2000/svg';
const svg=document.createElementNS(ns,'svg'); svg.setAttribute('viewBox',`-20 -20 ${W+40} ${H+70}`); svg.style.width='100%';
let html=`<defs><pattern id="g" width="${S/2}" height="${S/2}" patternUnits="userSpaceOnUse"><path d="M ${S/2} 0 L 0 0 0 ${S/2}" fill="none" stroke="rgba(138,154,181,.13)" stroke-width="1"/></pattern>
<radialGradient id="cone"><stop offset="0" stop-color="#F2B33D" stop-opacity=".30"/><stop offset="1" stop-color="#F2B33D" stop-opacity="0"/></radialGradient></defs>
<rect x="0" y="0" width="${W}" height="${H}" rx="10" fill="#111D31" stroke="#2C3F60"/><rect x="0" y="0" width="${W}" height="${H}" fill="url(#g)"/>`;
D.plan.props.forEach(p=>{html+=`<rect x="${p.x*S}" y="${p.y*S}" width="${p.w*S}" height="${p.h*S}" rx="4" fill="#1C2C49" stroke="#34496E"/>
<text x="${(p.x+p.w/2)*S}" y="${(p.y+p.h/2)*S+4}" fill="#8A9AB5" font-size="12" text-anchor="middle">${p.label}</text>`});
D.views.forEach(v=>{const [x,y]=pos[v.id], r=300, a0=(v.yaw-v.fov/2)*Math.PI/180, a1=(v.yaw+v.fov/2)*Math.PI/180;
  html+=`<path d="M${x},${y} L${x+r*Math.cos(a0)},${y+r*Math.sin(a0)} A${r},${r} 0 0,1 ${x+r*Math.cos(a1)},${y+r*Math.sin(a1)} Z" fill="url(#cone)" id="cone-${v.id}" opacity=".55"/>`});
html+=`<g id="links"></g>`;
const node=(id,x,y,label,hub)=>`<g class="cam" id="n-${id}"><circle class="ring" cx="${x}" cy="${y}" r="10" fill="none" stroke="#F2B33D" opacity="0"/>
<circle class="core" cx="${x}" cy="${y}" r="${hub?11:8}" fill="${hub?'#0E1726':'#E6ECF5'}" stroke="${hub?'#F2B33D':'#0E1726'}" stroke-width="2.5"/>
<text x="${x}" y="${y+(hub?28:24)}" fill="#E6ECF5" font-size="13" font-weight="500" text-anchor="middle">${label}</text></g>`;
html+=node('coordinator',...pos.coordinator,'Coordinator',true);
D.views.forEach(v=>html+=node(v.id,...pos[v.id],v.name,false));
html+=`<g id="dots"></g>`;
svg.innerHTML=html; document.getElementById('plan3d').appendChild(svg);

function pulse(id){const g=document.getElementById('n-'+id); if(!g) return; g.classList.remove('active'); void g.getBBox(); g.classList.add('active');
  const ring=g.querySelector('.ring'); ring.style.opacity=1; setTimeout(()=>ring.style.opacity=0,800)}
function fly(from,to,color){ if(reduce) return; const a=pos[from]||pos.coordinator, b=pos[to]||pos.coordinator;
  const line=document.createElementNS(ns,'line'); Object.entries({x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:color,'stroke-width':1.5,'stroke-dasharray':'4 5',opacity:.55}).forEach(([k,v])=>line.setAttribute(k,v));
  document.getElementById('links').appendChild(line);
  const dot=document.createElementNS(ns,'circle'); dot.setAttribute('r',5); dot.setAttribute('fill',color); document.getElementById('dots').appendChild(dot);
  const t0=performance.now(), dur=520;
  (function step(t){const k=Math.min(1,(t-t0)/dur), e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
    dot.setAttribute('cx',a[0]+(b[0]-a[0])*e); dot.setAttribute('cy',a[1]+(b[1]-a[1])*e);
    if(k<1) requestAnimationFrame(step); else {dot.remove(); pulse(to); setTimeout(()=>line.remove(),900)}})(t0)}

// ---------- conversation ----------
const log=document.getElementById('log'); let timers=[];
function play(){timers.forEach(clearTimeout); timers=[]; log.innerHTML=''; document.getElementById('after').hidden=true;
  const dt = reduce?60:Math.max(260, Math.min(560, 9000/D.messages.length));
  D.messages.forEach((m,i)=>timers.push(setTimeout(()=>{
    const [lbl,col]=KIND[m.kind]||[m.kind,'#8A9AB5'];
    pulse(m.sender);
    if(m.recipient==='all') D.views.forEach(v=>v.id!==m.sender&&fly(m.sender,v.id,col)); else fly(m.sender,m.recipient,col);
    if(m.sender!=='coordinator' && D.views.find(v=>v.id===m.sender)){const c=document.getElementById('cone-'+m.sender); c.setAttribute('opacity','1'); setTimeout(()=>c.setAttribute('opacity','.55'),700)}
    const li=document.createElement('li'); li.className='k-'+m.kind;
    li.innerHTML=`<div class="who"><span class="badge" style="color:${col}">${lbl}</span><b>${name(m.sender)}</b> to <b>${name(m.recipient)}</b></div><div>${m.text}</div>`;
    log.appendChild(li); log.scrollTop=log.scrollHeight; document.getElementById('lcount').textContent=`${i+1} messages`;
    if(i===D.messages.length-1) setTimeout(showResult, reduce?0:500);
  }, i*dt)));
}

// ---------- result: synced angles ----------
let vids=[], n=15, ticking=false;
function showResult(){ if(!D.moment){return}
  const M=D.moment; document.getElementById('after').hidden=false;
  const best=D.views.find(v=>v.id===M.cut[M.frame])||D.views[0];
  document.getElementById('verdict').innerHTML=`<div><div class="lbl">Moment</div><div class="big">${M.time}</div><div class="lbl">${M.date}</div></div>
   <div><div class="lbl">Cameras agreeing</div><div class="big">${M.agree} of ${D.views.length}</div></div>
   <div><div class="lbl">Best angle at that moment</div><div class="big" style="font-size:20px">${best.name}</div></div>
   <div class="brief">${D.briefing || D.messages[D.messages.length-1].text}${M.others.length?`<div class="lbl" style="margin-top:6px">Other candidates: ${M.others.map(o=>o.time+' ('+o.votes+' camera'+(o.votes>1?'s':'')+')').join(', ')}</div>`:''}</div>`;
  const grid=document.getElementById('grid'); grid.innerHTML=''; vids=[];
  D.views.forEach(v=>{const [cx,cy,s]=v.crop, st=STATUS[v.status]||['','#8A9AB5'];
    const card=document.createElement('div'); card.className='card'; card.id='card-'+v.id;
    card.innerHTML=`<header><b>${v.name}</b><span><span class="pickflag">Best angle</span> <span class="status" style="color:${st[1]}">${st[0]}</span></span></header>
      <div class="vp"><video muted playsinline preload="auto" src="/${M.video}" style="width:${100/s}%;left:${-cx/s*100}%;top:${-cy/s*100}%"></video><div class="ov"></div><div class="ts"></div></div>`;
    grid.appendChild(card); vids.push(card.querySelector('video'))});
  n=M.track[D.views[0].id].length;
  const rib=document.getElementById('ribbon');
  rib.innerHTML=`<h4>Subject track<span>Filled cells: subject visible in that view (brighter = closer). Outlined: best angle each second.</span></h4>`+
   D.views.map(v=>`<div class="rrow"><div class="nm">${v.name}</div><div class="cells" style="grid-template-columns:repeat(${n},1fr)">${
    M.track[v.id].map((a,f)=>`<div class="cell ${M.cut[f]===v.id&&a>0?'cut':''}" style="${a>0?`background:rgba(242,179,61,${Math.min(.9,.25+Math.sqrt(a)*1.3)})`:''}"></div>`).join('')
   }<div class="head"></div></div></div>`).join('');
  const start=Math.max(0,M.frame-2);
  vids.forEach(x=>x.addEventListener('loadedmetadata',()=>{x.currentTime=start},{once:true}));
  vids[0].addEventListener('timeupdate',sync);
  setTimeout(()=>{vids.forEach(x=>x.play().catch(()=>{})); document.getElementById('play').textContent='Pause'},400);
  if(!ticking){ticking=true; (function loop(){sync(); requestAnimationFrame(loop)})()}
}
function sync(){ if(!vids.length) return; const m=vids[0], t=m.currentTime||0;
  vids.slice(1).forEach(x=>{if(Math.abs(x.currentTime-t)>0.25) x.currentTime=t; if(m.paused!==x.paused) m.paused?x.pause():x.play().catch(()=>{})});
  const f=Math.min(n-1,Math.floor(t)), M=D.moment;
  D.views.forEach((v,i)=>{const card=document.getElementById('card-'+v.id); if(!card) return;
    card.classList.toggle('pick', M.cut[f]===v.id && M.track[v.id][f]>0 || (M.track[M.cut[f]][f]===0 && i===0));
    const ov=card.querySelector('.ov'), bx=v.boxes[f]||[];
    while(ov.children.length<bx.length){const d=document.createElement('div'); d.className='box'; ov.appendChild(d)}
    [...ov.children].forEach((d,j)=>{const b=bx[j]; d.style.display=b?'block':'none'; if(b){d.style.left=b[0]*100+'%'; d.style.top=b[1]*100+'%'; d.style.width=(b[2]-b[0])*100+'%'; d.style.height=(b[3]-b[1])*100+'%'}});
    const [hh,mm,ss]=M.start.split(':').map(Number), tot=hh*3600+mm*60+ss+Math.floor(t);
    card.querySelector('.ts').textContent=[Math.floor(tot/3600)%24,Math.floor(tot/60)%60,tot%60].map(z=>String(z).padStart(2,'0')).join(':');
  });
  const dur=m.duration||n; document.querySelectorAll('.head').forEach(h=>h.style.left=`calc(${Math.min(1,t/dur)*100}% - 1px)`);
}
document.getElementById('play').onclick=e=>{const m=vids[0]; if(!m) return; if(m.paused){vids.forEach(x=>x.play()); e.target.textContent='Pause'} else {vids.forEach(x=>x.pause()); e.target.textContent='Play all angles'}};
document.getElementById('replay').onclick=()=>{vids.forEach(x=>x.pause()); play()};
setTimeout(()=>document.getElementById('plan3d').style.transform='rotateX(30deg) scale(.96)',50);
play();
</script>
"""


def render(result):
    data = json.dumps(result).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data)
