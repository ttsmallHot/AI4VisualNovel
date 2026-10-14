(() => {
  const dialog = document.getElementById('regenerate-dialog');
  let context = null, timer = null, serial = 0, busy = false;
  const el = name => document.getElementById('regenerate-' + name);
  const active = token => token === serial && dialog.open;
  const running = request => ['queued','running'].includes(request?.status);
  function paint() {
    const request = context?.request, pending = running(request), ready = request?.status === 'ready';
    el('start').hidden = ready;
    el('start').disabled = busy || pending;
    el('start').textContent = pending ? 'Generating…' : request?.status === 'failed' ? 'Try Again' : 'Generate';
    el('accept').hidden = !ready;
    el('discard').hidden = !ready;
    el('accept').disabled = el('discard').disabled = busy;
    el('feedback').disabled = busy || pending || ready;
    const messages = {queued:'Queued…',running:'Generating may take a few minutes. You can close this window while it runs.',ready:'Your new image is ready. Compare it with the original before applying it.',failed:'Generation failed. The original image is unchanged.',accepted:'New image applied. The original has been backed up.',discarded:'Original image kept.'};
    el('status').textContent = messages[request?.status] || '';
    el('placeholder').textContent = pending ? 'Generating a new image…' : 'The generated image will appear here';
    const candidate = ready ? request.candidate_url : null;
    el('candidate').hidden = !candidate;
    el('placeholder').hidden = !!candidate;
    if (candidate) { if(el('candidate').getAttribute('src') !== candidate) el('candidate').src = candidate; }
    else el('candidate').removeAttribute('src');
    el('original').src = request?.status === 'accepted' ? context.assetUrl : request?.original_url || context.assetUrl;
    if (request?.status === 'failed') el('error').textContent = request.error || 'Image generation failed. Please try again.';
  }
  async function poll(token) {
    const {project,path} = context;
    try {
      const result = await api(`/api/assets/regeneration?project=${encodeURIComponent(project)}&path=${encodeURIComponent(path)}`);
      if (!active(token)) return;
      context.request = result.request;
      if(result.request) el('feedback').value = result.request.feedback || '';
      busy = false; el('error').textContent = ''; paint();
      if(running(result.request)) timer = setTimeout(() => poll(token), 2000);
    } catch(error) {
      if(!active(token)) return;
      busy = false; paint();
      el('error').textContent = 'Unable to fetch status. Retrying: ' + error.message;
      // Keep generation disabled until the server confirms the current state.
      el('start').disabled = true;
      timer = setTimeout(() => poll(token), 4000);
    }
  }
  document.getElementById('asset-groups').addEventListener('click', event => {
    const button = event.target.closest('[data-regenerate]');
    if(!button) return;
    clearTimeout(timer); const token = ++serial;
    const asset = state.data.assets.find(item => item.path === button.dataset.regenerate);
    if(!asset) return;
    context = {project:state.project,path:asset.path,assetUrl:asset.url,request:null}; busy = true;
    el('name').textContent = asset.name;
    el('original').src = asset.url;
    el('feedback').value = ''; el('error').textContent = '';
    dialog.showModal(); paint(); poll(token);
  });
  function close() { dialog.close(); }
  el('close').onclick = close;
  dialog.addEventListener('close', () => { ++serial; clearTimeout(timer); });
  async function action(type) {
    if(busy || !context) return;
    const token = serial, {project,path,request} = context;
    busy = true; el('error').textContent = ''; paint();
    try {
      const url = type === 'start' ? '/api/assets/regenerate' : `/api/assets/regeneration/${type}`;
      const body = type === 'start' ? {project,path,feedback:el('feedback').value.trim()} : {project,id:request.id};
      const result = await api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(type === 'accept') {
        if(state.project === project) await loadProject();
        await refreshLibrary(); toast('New image applied. The original has been backed up.');
      }
      if(!active(token)) return;
      context.request = result.request; busy = false; paint();
      if(type === 'accept' || type === 'discard') close();
      else if(running(result.request)) timer = setTimeout(() => poll(token), 1200);
    } catch(error) {
      if(!active(token)) return;
      busy = false; paint(); el('error').textContent = error.message;
      if(type === 'start') timer = setTimeout(() => poll(token), 2000);
    }
  }
  el('form').addEventListener('submit', event => { event.preventDefault(); if(!running(context?.request)) action('start'); });
  el('accept').onclick = () => action('accept');
  el('discard').onclick = () => action('discard');
})();
