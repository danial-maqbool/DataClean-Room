/* Local UI helpers. All runtime requests stay on this app's loopback origin. */
export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export const E = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const token = document.querySelector('meta[name="local-session"]').content;
export const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${({
  grid:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  search:'<circle cx="10.7" cy="10.7" r="7.2"/><path d="m16 16 5 5"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  file:'<path d="M14 2H5v20h14V7Z"/><path d="M14 2v6h5M8 13h8M8 17h6"/>',
  flow:'<rect x="2" y="3" width="7" height="6" rx="1.5"/><rect x="15" y="15" width="7" height="6" rx="1.5"/><path d="M5.5 9v9H15M9 6h9v9"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  shield:'<path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6Z"/><path d="m8 12 3 3 5-6"/>',
  tools:'<path d="m14 6 4-4a6 6 0 0 0-7 7L3 17a2.8 2.8 0 0 0 4 4l8-8a6 6 0 0 0 7-7l-4 4Z"/>',
  graph:'<circle cx="12" cy="4" r="2.5"/><circle cx="4" cy="18" r="2.5"/><circle cx="20" cy="18" r="2.5"/><path d="m11 6-6 10m8-10 6 10M7 18h10"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload:'<path d="M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  play:'<path d="m7 4 14 8-14 8Z"/>',
  pause:'<path d="M8 4v16M16 4v16"/>',
  check:'<path d="m4 12 5 5L20 6"/>',
  copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  bookmark:'<path d="M6 3h12v19l-6-5-6 5Z"/>',
  settings:'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="7" cy="18" r="2"/>',
  help:'<circle cx="12" cy="12" r="9"/><path d="M9 8a3 3 0 0 1 6 0c0 2-3 2-3 5m0 4h.01"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
  trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  alert:'<path d="m12 3 10 18H2Z"/><path d="M12 9v5m0 3h.01"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>',
  refresh:'<path d="M20 4v6h-6M4 20v-6h6M20 10a8 8 0 0 0-13-6M4 14a8 8 0 0 0 13 6"/>'
})[name] || '<circle cx="12" cy="12" r="8"/>'}</svg>`;

export async function api(action, body = null, query = {}) {
  const suffix = new URLSearchParams(Object.entries(query).filter(([,v]) => v !== '' && v != null)).toString();
  const response = await fetch(`/api/${action}${suffix ? '?' + suffix : ''}`, {
    method: body === null ? 'GET' : 'POST',
    headers: {'X-Local-Token': token, ...(body === null ? {} : {'Content-Type':'application/json'})},
    body: body === null ? undefined : JSON.stringify(body), cache:'no-store', credentials:'same-origin'
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('The app returned an unreadable response.'); }
  if (!response.ok) throw new Error(result.error || `The operation failed (${response.status}).`);
  return result;
}
export const get = (action, query = {}) => api(action, null, query);
export const post = (action, body = {}) => api(action, body);

export function listen(selector, event, handler, root = document) {
  $$(selector, root).forEach(node => node.addEventListener(event, async e => {
    const button = node.tagName === 'BUTTON';
    if (button) node.disabled = true;
    try { await handler(e, node); }
    catch (error) { toast(error.message || String(error), 'error'); }
    finally { if (button && node.isConnected) node.disabled = false; }
  }));
}

export function toast(message, type = 'success') {
  const node = document.createElement('div');
  node.className = `toast ${type}`; node.setAttribute('role', type === 'error' ? 'alert' : 'status');
  node.textContent = message; $('#toasts').append(node);
  setTimeout(() => node.remove(), type === 'error' ? 9000 : 4200);
}
export function bytes(value) {
  const n = Number(value || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n/1024).toFixed(1)} KiB`;
  if (n < 1024 ** 3) return `${(n/1024**2).toFixed(1)} MiB`;
  return `${(n/1024**3).toFixed(2)} GiB`;
}
export function when(value) {
  if (!value) return 'Not yet';
  const d = new Date(value);
  return Number.isNaN(d.valueOf()) ? String(value) : new Intl.DateTimeFormat(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d);
}
export const badge = (text, kind = '') => `<span class="badge ${kind}">${E(text)}</span>`;
export const fileIcon = name => `<span class="file-tile">${E(String(name).split('.').pop().slice(0,5).toUpperCase())}</span>`;
export const empty = (title, text, symbol='folder') => `<div class="empty">${icon(symbol)}<h3>${E(title)}</h3><p>${E(text)}</p></div>`;
export const stats = rows => `<div class="stats">${rows.map(([label,value,note,symbol]) => `<div class="stat"><div class="stat-label">${E(label)}${icon(symbol || 'grid')}</div><div class="stat-value">${E(value)}</div><div class="stat-note">${E(note || '')}</div></div>`).join('')}</div>`;
export const pageHead = (label,title,text,actions='') => `<div class="page-head"><div><div class="eyebrow">${E(label)}</div><h1>${E(title)}</h1><p>${E(text)}</p></div><div class="head-actions">${actions}</div></div>`;
export const button = (id,label,symbol='',kind='secondary',extra='') => `<button type="button" id="${E(id)}" class="btn ${kind}" ${extra}>${symbol ? icon(symbol):''}${E(label)}</button>`;

export function highlight(text, query) {
  const words = String(query).match(/[\p{L}\p{N}]+/gu) || [];
  if (!words.length) return E(text);
  const expression = new RegExp('(' + words.slice(0,20).map(s => s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|') + ')', 'gi');
  return String(text).split(expression).map((part,index) => index%2 ? `<mark>${E(part)}</mark>` : E(part)).join('');
}

export function modal(title, content, footer='') {
  const dialog = $('#modal');
  if (dialog.open) dialog.close();
  dialog.innerHTML = `<div class="modal-head"><h2>${E(title)}</h2><button class="icon-btn" id="modal-close" aria-label="Close dialog">${icon('close')}</button></div><div class="modal-body">${content}</div>${footer ? `<div class="modal-foot">${footer}</div>` : ''}`;
  $('#modal-close').onclick = () => dialog.close();
  dialog.showModal();
  return dialog;
}
export function ask(title, label, value = '', {multiline=false, confirm='Save'}={}) {
  return new Promise(resolve => {
    const content = `<label class="field">${E(label)}${multiline ? `<textarea id="ask-value" rows="7">${E(value)}</textarea>` : `<input id="ask-value" value="${E(value)}">`}</label>`;
    const dialog = modal(title, content, button('ask-save',confirm,'check','primary'));
    let done = false;
    $('#ask-save').onclick = () => { done = true; const v = $('#ask-value').value; dialog.close(); resolve(v); };
    dialog.addEventListener('close', () => { if(!done) resolve(null); }, {once:true});
    $('#ask-value').focus();
  });
}
export function showJSON(title, value) { return modal(title, `<pre class="code-block">${E(JSON.stringify(value,null,2))}</pre>`); }

export async function download(artifact) {
  if (!artifact?.path) throw new Error('The output file is not available.');
  const response = await fetch('/api/download?' + new URLSearchParams({path:artifact.path}), {headers:{'X-Local-Token':token}});
  if (!response.ok) { const data = await response.json(); throw new Error(data.error || 'The file could not be opened.'); }
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a'); a.href=url; a.download=artifact.name || 'output'; a.click();
  setTimeout(() => URL.revokeObjectURL(url),30000);
}
export function artifactsHTML(items) {
  return `<div class="artifact-list">${items.map((a,i) => `<button class="artifact" data-artifact="${i}">${icon('download')}<span>${E(a.name)}<small>${bytes(a.size)}</small></span>${icon('arrow')}</button>`).join('')}</div>`;
}
export function bindArtifacts(items, root=document) { listen('[data-artifact]','click',(_,node) => download(items[Number(node.dataset.artifact)]),root); }

let activeJob = null;
export async function runJob(action, body, onDone = null) {
  const response = await post(action, body);
  const ident = response.job_id;
  if (!ident) return response;
  activeJob=ident;
  const bar = $('#job-bar');
  bar.hidden=false;
  bar.innerHTML=`<div class="job-line"><span class="spinner"></span><strong id="job-name">Starting local job</strong><span id="job-message"></span><button id="cancel-job" class="text-btn">Cancel</button></div><div class="progress"><span id="job-progress"></span></div>`;
  listen('#cancel-job','click',() => post('cancel',{id:ident}));
  while (true) {
    const job = await get('jobs/'+ident);
    if (activeJob===ident && $('#job-name')) {
      $('#job-name').textContent=job.kind; $('#job-message').textContent=job.message || job.status;
      $('#job-progress').style.width=job.progress+'%';
    }
    if (['done','failed','cancelled','interrupted'].includes(job.status)) {
      if (activeJob===ident) { activeJob=null; bar.hidden=true; }
      if (job.status!=='done') throw new Error(job.error || `The job is ${job.status}.`);
      if (onDone) await onDone(job.result);
      return job.result;
    }
    await new Promise(resolve=>setTimeout(resolve,250));
  }
}

export async function uploadFiles(files) {
  if (!files.length || files.length>20) throw new Error('Choose between 1 and 20 files.');
  const output=[];
  for (const file of files) {
    if (file.size>25*1024**2) throw new Error(`${file.name} exceeds 25 MiB.`);
    const data=await new Promise((resolve,reject)=>{
      const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('The file could not be read.'));reader.readAsDataURL(file);
    });
    output.push(await post('upload',{name:file.name,content:data}));
  }
  return output;
}
export function dropZone(id='drop-zone',text='Choose files or drop them here') {
  return `<div class="drop-zone" id="${E(id)}" tabindex="0" role="button" aria-label="Choose local files">${icon('upload')}<strong>${E(text)}</strong><span>Up to 20 files. 25 MiB per file. Nothing leaves this PC.</span><input type="file" id="${E(id)}-input" multiple hidden></div>`;
}
export function bindDrop(id, callback) {
  const zone=$('#'+id), input=$('#'+id+'-input');
  zone.addEventListener('click',e=>{if(e.target!==input)input.click();});
  zone.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();input.click();}});
  const invoke=async files=>{try {await callback(await uploadFiles([...files]));}catch(error){toast(error.message,'error');}finally{input.value='';}};
  input.addEventListener('change',()=>invoke(input.files));
  zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('over');});
  zone.addEventListener('dragleave',()=>zone.classList.remove('over'));
  zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('over');invoke(e.dataTransfer.files);});
}

export async function pickPath(start='', file=false) {
  return new Promise(async resolve => {
    let current=start, chosen='', finished=false;
    const dialog=modal(file?'Choose a local file':'Choose a local folder', '<div id="browser-body"></div>',button('pick-use',file?'Use selected file':'Use this folder','check','primary'));
    dialog.addEventListener('close',()=>{if(!finished)resolve(null);},{once:true});
    async function load(path) {
      try {
        const result=await get('browse',{path});current=result.path;
        $('#browser-body').innerHTML=`<div class="input-row"><input id="browse-path" aria-label="Folder path" value="${E(current)}">${button('browse-go','Open','','secondary')}</div><button class="text-btn" id="browse-up">${icon('folder')} Parent folder</button><div class="folder-list">${result.entries.map((e,i)=>`<button class="folder-entry" data-entry="${i}">${icon(e.directory?'folder':'file')}<span>${E(e.name)}</span>${e.directory?icon('arrow'):''}</button>`).join('')}</div>${result.limited?'<p class="muted">Only the first 1,500 entries are listed. Enter a more specific path.</p>':''}`;
        listen('#browse-go','click',()=>load($('#browse-path').value));
        listen('#browse-up','click',()=>load(result.parent));
        listen('[data-entry]','click',(_,node)=>{const item=result.entries[Number(node.dataset.entry)];if(item.directory)return load(item.path);if(file){chosen=item.path;$$('.folder-entry').forEach(x=>x.classList.remove('selected'));node.classList.add('selected');}});
      }catch(error){toast(error.message,'error');}
    }
    $('#pick-use').onclick=()=>{if(file&&!chosen){toast('Select a file first.','error');return;}finished=true;dialog.close();resolve(file?chosen:current);};
    await load(current);
  });
}

export function jobsHTML(jobs) {
  if(!jobs.length)return empty('No jobs yet','Run an operation to see its status and result here.','clock');
  return `<div class="table-wrap"><table><thead><tr><th>Operation</th><th>Status</th><th>Started</th><th>Details</th></tr></thead><tbody>${jobs.map(j=>`<tr><td><strong>${E(j.kind)}</strong><small>${E(j.message||'')}</small></td><td>${badge(j.status,j.status==='done'?'good':j.status==='failed'?'bad':'')}</td><td>${E(when(j.created))}</td><td><button class="text-btn" data-job="${E(j.id)}">View result ${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div>`;
}
export function bindJobs(){listen('[data-job]','click',async(_,node)=>showJSON('Job result',await get('jobs/'+node.dataset.job)));}

export function mount(info, navigation, route, help='') {
  document.title=info.name;document.documentElement.style.setProperty('--accent',info.color);
  const theme=localStorage.getItem('localdesk-theme') || 'light';document.documentElement.dataset.theme=theme;
  const initials=info.name.split(' ').map(x=>x[0]).join('').slice(0,2);
  $('#app').innerHTML=`<aside class="sidebar"><a class="brand" href="#${E(navigation[0][0])}"><span class="brand-mark">${E(initials)}</span><span>${E(info.name)}<small>LOCAL WORKSPACE</small></span></a><div class="nav-label">WORKSPACE</div><nav>${navigation.map(([id,label,symbol])=>`<a href="#${E(id)}" class="nav-link" data-nav="${E(id)}">${icon(symbol)}<span>${E(label)}</span></a>`).join('')}</nav><div class="side-bottom"><div class="local-proof">${icon('lock')}<div><strong>On your device</strong><span>No account. No cloud calls.</span></div></div><div class="side-version"><span>v${E(info.version)}</span><span class="online-dot"></span> Local only</div></div></aside><div class="main-shell"><header class="topbar"><div class="breadcrumb">${E(info.name)} <span>/</span> <strong id="crumb">Workspace</strong></div><div class="top-actions"><span class="local-pill"><span class="online-dot"></span> Offline ready</span><button id="theme-button" class="icon-btn" aria-label="Switch color theme" title="Switch color theme">${icon('sun')}</button><button id="settings-button" class="icon-btn" aria-label="Local settings" title="Local settings">${icon('settings')}</button><button id="help-button" class="icon-btn" aria-label="App help" title="App help">${icon('help')}</button></div></header><main id="view" tabindex="-1"></main><div id="job-bar" class="job-bar" hidden></div><footer class="page-footer"><span>${icon('shield')} Your input stays local.</span><span>Source code and documentation are included.</span></footer></div>`;
  listen('#theme-button','click',()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=next;localStorage.setItem('localdesk-theme',next);});
  listen('#help-button','click',()=>modal('Use '+info.name,help || `<p>${E(info.tagline)}</p><p>Start with the included demo files. Read README.md and docs/USER_GUIDE.md for complete instructions.</p>`));
  listen('#settings-button','click',()=>{
    const c=info.capabilities;
    modal('Local settings',`<p>All app data stays in this folder:</p><pre class="path-box">${E(info.data_path)}</pre><div class="notice">Backups can contain private file names, extracted text, and reports. Keep backups private.</div><h3>Local capabilities</h3><div class="key-values">${Object.entries(c).map(([k,v])=>`<span>${E(k.toUpperCase())}</span><strong>${E(typeof v === 'boolean' ? (v ? 'Available' : 'Not enabled') : String(v))}</strong>`).join('')}</div><p class="muted">Run setup once to install the local dependencies. Tesseract needs a separate OS installation. Database backups are encrypted. Source files and exported files are not encrypted.</p>`,button('backup-db','Export database backup','download','primary'));
    listen('#backup-db','click',async()=>download(await post('backup')));
  });
  async function dispatch(){
    const id=location.hash.slice(1)||navigation[0][0];
    const tab=navigation.find(n=>n[0]===id)||navigation[0];
    $$('.nav-link').forEach(n=>n.classList.toggle('active',n.dataset.nav===tab[0]));$('#crumb').textContent=tab[1];
    try{await route(tab[0]);}catch(error){$('#view').innerHTML=empty('The view could not load',error.message,'alert');toast(error.message,'error');}
  }
  window.addEventListener('hashchange',dispatch);dispatch();
}
