'use strict';
const $=s=>document.querySelector(s);
let sessionId=sessionStorage.getItem('courtlab-session'),busy=false,controller;
const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Escape all model text first. Only create allowlisted links; never render model HTML.
function inline(s){return escapeHtml(s).replace(/\[([^\]]+)\]\(([^\s)]+)\)/g,(m,label,url)=>{
 const decoded=url.replace(/&amp;/g,'&');
 if(!/^https?:\/\//.test(decoded)&&!/^\/evidence\/[A-Za-z0-9_-]+$/.test(decoded))return label;
 return `<a href="${url}"${decoded.startsWith('/')?'':' target="_blank" rel="noopener noreferrer"'}>${label}</a>`;
}).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');}
function markdown(text){let out='',list=false;for(const line of text.split('\n')){
 const item=/^(?:- |\d+\. )(.*)/.exec(line);
 if(item){if(!list){out+='<ul>';list=true;}out+='<li>'+inline(item[1])+'</li>';continue;}
 if(list){out+='</ul>';list=false;}
 const heading=/^(#{1,3}) (.*)/.exec(line);
 out+=heading?`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`:line.trim()?'<p>'+inline(line)+'</p>':'';
 }return out+(list?'</ul>':'');}
function userMessage(text){const el=document.createElement('article');el.className='message';el.innerHTML='<div class="message-label">YOUR QUESTION</div><div class="user-message"></div>';el.lastElementChild.textContent=text;$('#conversation').append(el);}
let diagramSequence=0;
function renderTacticsDiagram(d,parent,citations=[]){
 if(!d||!Array.isArray(d.players)||!Array.isArray(d.motions))return;
 const citationNumbers=new Map(citations.map(c=>[c.source_id,c.number]));
 const ns='http://www.w3.org/2000/svg',uid='court-diagram-'+(++diagramSequence);
 const svgNode=(tag,attrs={},text)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;};
 const point=(x,y)=>[30+Number(x)*5.4,20+Number(y)*5.04];
 const fig=document.createElement('figure');fig.className='tactics-diagram';
 const title=document.createElement('h3');title.textContent=d.title;fig.append(title);
 const badge=document.createElement('p');badge.className='diagram-badge';badge.textContent=d.kind==='proposed_adaptation'?'PROPOSED ADAPTATION · STATIC DIAGRAM':'CONCEPT ILLUSTRATION · STATIC DIAGRAM';fig.append(badge);
 const svg=svgNode('svg',{viewBox:'0 0 600 560',role:'img','aria-labelledby':uid+'-title '+uid+'-desc'});
 svg.append(svgNode('title',{id:uid+'-title'},d.title),svgNode('desc',{id:uid+'-desc'},d.caption+' '+d.disclaimer));
 const defs=svgNode('defs');
 for(const [key,color] of [['pass','#b56329'],['cut','#274d3a'],['screen','#274d3a']]){
  const m=svgNode('marker',{id:uid+'-'+key,viewBox:'0 0 12 12',refX:10,refY:6,markerWidth:7,markerHeight:7,orient:'auto',markerUnits:'strokeWidth'});
  m.append(svgNode('path',{d:key==='screen'?'M9 1V11':'M1 1L11 6L1 11',fill:'none',stroke:color,'stroke-width':2}));defs.append(m);
 }
 svg.append(defs,svgNode('rect',{x:0,y:0,width:600,height:560,rx:12,fill:'#f7f1e5'}));
 const court=svgNode('g',{fill:'none',stroke:'#9b9c86','stroke-width':1.5});
 for(const dpath of ['M30 524V20H570V524Z','M210 20V207H390V20','M210 207A90 90 0 0 0 390 207','M58 20V78C58 358 542 358 542 78V20','M255 50H345','M300 50V64','M230 524A70 70 0 0 1 370 524'])court.append(svgNode('path',{d:dpath}));
 court.append(svgNode('circle',{cx:300,cy:74,r:10}));svg.append(court);
 const positions=new Map(d.players.map(p=>[p.id,p]));
 d.motions.forEach((m,i)=>{
  const from=positions.get(m.start);if(!from)return;
  const a=point(from.x,from.y),b=point(m.end_x,m.end_y),dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy);if(len<32)return;
  const endsAtPlayer=d.players.some(p=>Math.hypot(p.x-m.end_x,p.y-m.end_y)<3);
  const start=[a[0]+dx/len*19,a[1]+dy/len*19],end=[b[0]-dx/len*(endsAtPlayer?20:0),b[1]-dy/len*(endsAtPlayer?20:0)];
  svg.append(svgNode('path',{d:`M${start[0]} ${start[1]}L${end[0]} ${end[1]}`,fill:'none',stroke:m.kind==='pass'?'#b56329':'#274d3a','stroke-width':3,'stroke-dasharray':m.kind==='pass'?'8 6':'none','marker-end':`url(#${uid}-${m.kind})`}));
  svg.append(svgNode('text',{x:(start[0]+end[0])/2-dy/len*13,y:(start[1]+end[1])/2+dx/len*13,'text-anchor':'middle','dominant-baseline':'central',fill:'#26342b',stroke:'#f7f1e5','stroke-width':5,'paint-order':'stroke','font-family':'sans-serif','font-size':13,'font-weight':700},String.fromCharCode(65+i)));
 });
 for(const p of d.players){const [x,y]=point(p.x,p.y),off=p.id.startsWith('O');svg.append(svgNode('circle',{cx:x,cy:y,r:17,fill:off?'#e4ae58':'#f7f1e5',stroke:off?'#26342b':'#7a8076','stroke-width':2}));svg.append(svgNode('text',{x,y:y+1,'text-anchor':'middle','dominant-baseline':'central',fill:'#26342b','font-family':'sans-serif','font-size':off?15:12,'font-weight':700},off?p.id.slice(1):p.id));}
 fig.append(svg);
 const caption=document.createElement('figcaption');
 const description=document.createElement('p');description.textContent=d.caption;caption.append(description);
 const key=document.createElement('p');key.className='diagram-key';key.textContent='1–5: Offense · X1–X5: Defense · Dashed arrow: Pass · Solid arrow: Run · End bar: Screen';caption.append(key);
 const steps=document.createElement('ul');steps.className='diagram-steps';d.motions.forEach((m,i)=>{const li=document.createElement('li');li.textContent=String.fromCharCode(65+i)+'. '+m.label;steps.append(li);});caption.append(steps);
 const limit=document.createElement('p');limit.className='diagram-limit';limit.textContent=d.disclaimer;caption.append(limit);
 const sources=document.createElement('p');sources.className='diagram-sources';sources.append(document.createTextNode('Principles: '));for(const [i,sid] of (d.source_ids||[]).entries()){const a=document.createElement('a');a.href='/evidence/'+encodeURIComponent(sid);a.textContent='['+(citationNumbers.get(sid)||(i+1))+']';sources.append(a,document.createTextNode(' '));}caption.append(sources);
 fig.append(caption);parent.append(fig);
}

function answerMessage(data){const el=document.createElement('article');el.className='message';const label=document.createElement('div');label.className='message-label';label.textContent=data.research?.status==='clarification'?'BEFORE WE RESEARCH / CLARIFY THE QUESTION':'COURTLAB / RESEARCH BRIEF';el.append(label);
 const report=document.createElement('div');report.className='report';const [body,sources]=String(data.response||'No response.').split('\n\n## Sources\n\n');report.innerHTML=markdown(body);el.append(report);
 if(data.research?.diagram){try{renderTacticsDiagram(data.research.diagram,el,data.research.citations||[]);}catch{console.warn('The optional diagram could not be rendered.');}}
 if(sources){const details=document.createElement('details');details.className='trace';const summary=document.createElement('summary');summary.textContent='Sources';const content=document.createElement('div');content.innerHTML=markdown(sources);details.append(summary,content);el.append(details);}
 if(data.research){const meta=document.createElement('div');meta.className='report-meta';for(const t of [data.research.status,`${data.research.rounds||0} research rounds`,`${data.research.researchers||0} researchers`,`${data.research.citations?.length||0} citations`]){const span=document.createElement('span');span.textContent=t;meta.append(span);}el.append(meta);}
 if(data.tool_calls?.length){const details=document.createElement('details');details.className='trace';const summary=document.createElement('summary');summary.textContent=`Research trace · ${data.tool_calls.length} calls, including sub-agents`;details.append(summary);
 for(const trace of data.tool_calls){const row=document.createElement('div');row.className='trace-entry';const name=document.createElement('strong');name.textContent=trace.agent+' → '+trace.name;const pre=document.createElement('pre');pre.textContent=JSON.stringify({args:trace.args,result:trace.result},null,2);row.append(name,pre);details.append(row);}el.append(details);}
 $('#conversation').append(el);return el;}
function openDrawer(title){$('#drawer-title').textContent=title;$('#drawer-body').replaceChildren();if(!$('#drawer').open)$('#drawer').showModal();}
function paragraph(text,parent=$('#drawer-body')){const p=document.createElement('p');p.textContent=text;parent.append(p);return p;}
async function fetchJson(url){const r=await fetch(url);const data=await r.json();if(!r.ok)throw new Error(data.error||data.response||'Could not load data.');return data;}
document.addEventListener('click',async e=>{const a=e.target.closest('a[href^="/evidence/"]');if(!a)return;e.preventDefault();openDrawer('Loading evidence…');try{const d=await fetchJson(a.getAttribute('href'));$('#drawer-title').textContent=d.title;paragraph(d.locator||'');const source=document.createElement('a');source.href=d.url;source.target='_blank';source.rel='noopener noreferrer';source.textContent='Open original source ↗';$('#drawer-body').append(source);if(d.kind==='film_study')paragraph('This is an article excerpt. The app does not automatically analyze video.');const text=document.createElement('div');text.className='evidence-text';text.textContent=d.text;$('#drawer-body').append(text);}catch(err){paragraph(err.message);}});
$('#close-drawer').onclick=()=>$('#drawer').close();
$('#catalog-button').onclick=async()=>{openDrawer('Evidence library');try{const [c,m]=await Promise.all([fetchJson('/catalog'),fetchJson('/manifest')]);paragraph(`${m.acb_game_count} annotated ACB games · ${m.acb_action_count.toLocaleString()} actions · ${m.acb_aggregate_game_count} games in season aggregates · ${m.game_count} NBA games · ${m.passage_count} passages`);paragraph('Retrieved: '+m.retrieved_at);paragraph(c.scope);for(const d of c.documents){const item=document.createElement('div');item.className='source-card';const a=document.createElement('a');a.textContent=d.title;a.href=d.url;a.target='_blank';a.rel='noopener noreferrer';const small=document.createElement('small');small.textContent=[d.kind,d.team,d.season].filter(Boolean).join(' · ');item.append(a,small);$('#drawer-body').append(item);}for(const limit of m.limitations)paragraph(limit);}catch(err){paragraph(err.message);}};
$('#context-button').onclick=()=>{if(sessionId&&typeof showContext==='function')showContext(sessionId);else{openDrawer('Agent contexts');paragraph('Start a research run to inspect the actual context supplied to each agent.');}};
async function submitQuestion(text){if(busy)return;busy=true;$('#intro').hidden=true;userMessage(text);$('#question').value='';$('#send').disabled=true;$('#progress').hidden=false;$('#activities').replaceChildren();controller=new AbortController();const start=Date.now();const timer=setInterval(()=>$('#elapsed').textContent=Math.floor((Date.now()-start)/1000)+'s',1000);let received=false;
 try{const sendRequest=()=>fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,session_id:sessionId}),signal:controller.signal});let r=await sendRequest();
 if(r.status===404&&sessionId){sessionId=null;sessionStorage.removeItem('courtlab-session');$('#conversation').replaceChildren();answerMessage({response:'Your previous session expired. This request starts a new chat; include any earlier roster or practice constraints.'});userMessage(text);r=await sendRequest();}
 if(!r.ok){const d=await r.json();throw new Error(d.response||'Request failed.');}
 const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';
 while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let end;while((end=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,end);buffer=buffer.slice(end+2);const raw=frame.split('\n').find(x=>x.startsWith('data: '));if(!raw)continue;const event=JSON.parse(raw.slice(6));if(event.type==='start'){if(typeof resetContext==='function')resetContext();sessionId=event.session_id;sessionStorage.setItem('courtlab-session',sessionId);}else if(event.type==='activity'||event.type==='tool'){const line=document.createElement('div');const b=document.createElement('b');b.textContent=event.agent+' · ';line.append(b,document.createTextNode(event.type==='tool'?event.name:event.text));$('#activities').append(line);$('#activities').scrollTop=$('#activities').scrollHeight;}else if(event.type==='done'){received=true;answerMessage(event);if(event.status_code>=400)$('#question').value=text;}}
 if(done)break;}
 if(!received)throw new Error('The connection ended before a report arrived. Please retry.');
 }catch(err){$('#question').value=text;answerMessage({response:err.name==='AbortError'?'Research stopped.':err instanceof TypeError?'Cannot reach CourtLab. Check the server and retry. Your question has been kept in the input.':err.message});}
 finally{clearInterval(timer);busy=false;$('#send').disabled=false;$('#progress').hidden=true;$('#question').focus();}}
$('#question-form').onsubmit=e=>{e.preventDefault();const text=$('#question').value.trim();if(text)submitQuestion(text);};
$('#question').onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){$('#question-form').requestSubmit();}};
for(const b of document.querySelectorAll('.sample'))b.onclick=()=>{if(!busy){$('#question').value=b.dataset.query;$('#question').focus();}};
$('#cancel').onclick=()=>controller?.abort();
$('#new-chat').onclick=()=>{if(busy)return;if(typeof resetContext==='function')resetContext();sessionId=null;sessionStorage.removeItem('courtlab-session');$('#conversation').replaceChildren();$('#intro').hidden=false;$('#question').value='';window.scrollTo({top:0,behavior:'smooth'});};
(async()=>{try{const m=await fetchJson('/manifest');$('#corpus-count').textContent=`${m.acb_game_count} ACB games · ${m.acb_action_count.toLocaleString()} labeled actions\n${m.acb_aggregate_game_count}-game season aggregates · WABC Levels 1–3\n${m.game_count} NBA games · ${m.passage_count} passages`;}catch{$('#corpus-count').textContent='Evidence library unavailable';}
 if(sessionId){try{const h=await fetchJson('/sessions/'+encodeURIComponent(sessionId));if(h.messages.length)$('#intro').hidden=true;for(const m of h.messages){if(m.role==='user')userMessage(m.content);else answerMessage({response:m.content,tool_calls:m.tool_calls,research:m.research});}}catch{sessionId=null;sessionStorage.removeItem('courtlab-session');}}})();
