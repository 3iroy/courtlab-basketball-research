'use strict';
const $=s=>document.querySelector(s);
let sessionId=sessionStorage.getItem('courtlab-session'),busy=false,controller;
const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Escape all model text first. Only create allowlisted links; never render model HTML.
function inline(s){return escapeHtml(s).replace(/\[([^\]]+)\]\(([^\s)]+)\)/g,(m,label,url)=>{
 const decoded=url.replace(/&amp;/g,'&');
 if(!/^https?:\/\//.test(decoded)&&!/^\/evidence\/[A-Za-z0-9-]+$/.test(decoded))return label;
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
function answerMessage(data){const el=document.createElement('article');el.className='message';const label=document.createElement('div');label.className='message-label';label.textContent=data.research?.status==='clarification'?'BEFORE WE RESEARCH / CLARIFY THE QUESTION':'COURTLAB / RESEARCH BRIEF';el.append(label);
 const report=document.createElement('div');report.className='report';report.innerHTML=markdown(data.response||'No response.');el.append(report);
 if(data.research){const meta=document.createElement('div');meta.className='report-meta';for(const t of [data.research.status,`${data.research.rounds||0} research rounds`,`${data.research.researchers||0} researchers`,`${data.research.citations?.length||0} citations`]){const span=document.createElement('span');span.textContent=t;meta.append(span);}el.append(meta);}
 if(data.tool_calls?.length){const details=document.createElement('details');details.className='trace';const summary=document.createElement('summary');summary.textContent=`Research trace · ${data.tool_calls.length} calls, including sub-agents`;details.append(summary);
 for(const trace of data.tool_calls){const row=document.createElement('div');row.className='trace-entry';const name=document.createElement('strong');name.textContent=trace.agent+' → '+trace.name;const pre=document.createElement('pre');pre.textContent=JSON.stringify({args:trace.args,result:trace.result},null,2);row.append(name,pre);details.append(row);}el.append(details);}
 $('#conversation').append(el);return el;}
function openDrawer(title){$('#drawer-title').textContent=title;$('#drawer-body').replaceChildren();if(!$('#drawer').open)$('#drawer').showModal();}
function paragraph(text,parent=$('#drawer-body')){const p=document.createElement('p');p.textContent=text;parent.append(p);return p;}
async function fetchJson(url){const r=await fetch(url);const data=await r.json();if(!r.ok)throw new Error(data.error||data.response||'Could not load data.');return data;}
document.addEventListener('click',async e=>{const a=e.target.closest('a[href^="/evidence/"]');if(!a)return;e.preventDefault();openDrawer('Loading evidence…');try{const d=await fetchJson(a.getAttribute('href'));$('#drawer-title').textContent=d.title;paragraph(d.locator||'');const source=document.createElement('a');source.href=d.url;source.target='_blank';source.rel='noopener noreferrer';source.textContent='Open original source ↗';$('#drawer-body').append(source);if(d.kind==='film_study')paragraph('This is an article excerpt. The app does not automatically analyze video.');const text=document.createElement('div');text.className='evidence-text';text.textContent=d.text;$('#drawer-body').append(text);}catch(err){paragraph(err.message);}});
$('#close-drawer').onclick=()=>$('#drawer').close();
$('#catalog-button').onclick=async()=>{openDrawer('Evidence library');try{const [c,m]=await Promise.all([fetchJson('/catalog'),fetchJson('/manifest')]);paragraph(`${m.game_count} games · ${m.event_count.toLocaleString()} events · ${m.passage_count} passages`);paragraph('Retrieved: '+m.retrieved_at);paragraph(c.scope);for(const d of c.documents){const item=document.createElement('div');item.className='source-card';const a=document.createElement('a');a.textContent=d.title;a.href=d.url;a.target='_blank';a.rel='noopener noreferrer';const small=document.createElement('small');small.textContent=[d.kind,d.team,d.season].filter(Boolean).join(' · ');item.append(a,small);$('#drawer-body').append(item);}paragraph('Play-by-play does not contain complete tactical labels. Selected film studies cannot establish season-wide tactical frequency.');}catch(err){paragraph(err.message);}};
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
(async()=>{try{const m=await fetchJson('/manifest');$('#corpus-count').textContent=`${m.game_count} games · ${m.event_count.toLocaleString()} events\n${m.passage_count} citable passages`;}catch{$('#corpus-count').textContent='Evidence library unavailable';}
 if(sessionId){try{const h=await fetchJson('/sessions/'+encodeURIComponent(sessionId));if(h.messages.length)$('#intro').hidden=true;for(const m of h.messages){if(m.role==='user')userMessage(m.content);else answerMessage({response:m.content,tool_calls:m.tool_calls,research:m.research});}}catch{sessionId=null;sessionStorage.removeItem('courtlab-session');}}})();
