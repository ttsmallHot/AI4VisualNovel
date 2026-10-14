/* Graph planning editor. Script text is deliberately not rewritten here. */
let graphEditor = null;
const graphEditDialog = document.createElement('dialog');
graphEditDialog.className = 'graph-edit-dialog';
graphEditDialog.setAttribute('aria-labelledby', 'graph-edit-title');
graphEditDialog.innerHTML = `
  <form class="graph-edit-form">
    <header class="graph-edit-header"><h2 id="graph-edit-title">Edit Story Graph</h2>
      <p class="graph-edit-notice">Edit the story outline and branches, then save to apply your changes. Update existing dialogue and playable choices separately in Story & Script.</p>
    </header>
    <fieldset class="graph-edit-fields">
      <aside class="graph-edit-sidebar"><button type="button" class="btn" id="graph-add-node">＋ Add Node</button><nav class="graph-edit-node-list" aria-label="Select a node to edit"></nav></aside>
      <div class="graph-edit-body"></div>
    </fieldset>
    <p class="graph-edit-error" role="alert"></p>
    <footer class="graph-edit-footer"><button type="button" class="btn" id="graph-edit-cancel">Cancel</button><button type="submit" class="btn primary" id="graph-edit-save">Save Story Graph</button></footer>
  </form>`;
document.body.appendChild(graphEditDialog);
const graphEditButton = document.createElement('button');
graphEditButton.className = 'btn primary';
graphEditButton.textContent = 'Edit Story Graph';
graphEditButton.addEventListener('click', () => openGraphEditor(state.selectedNode));
document.querySelector('.graph-toolbar').appendChild(graphEditButton);

// Reuse the canvas selection and give each node a direct editing entry point.
const showGraphDetailReadOnly = showGraphDetail;
showGraphDetail = function(id) {
  showGraphDetailReadOnly(id);
  if (!graphNodes()[id]) return;
  const button = document.createElement('button');
  button.className = 'btn';
  button.style.cssText = 'width:100%;margin-top:10px';
  button.textContent = 'Edit Node & Branches';
  button.addEventListener('click', () => openGraphEditor(id));
  $('graph-detail').appendChild(button);
};

function openGraphEditor(id) {
  if (!state.data || !state.project) return;
  const draft = structuredClone(state.data.graph || {});
  draft.nodes ||= {};
  draft.edges ||= [];
  const original = JSON.stringify(draft);
  if (!Object.keys(draft.nodes).length) draft.nodes.root = {id:'root',summary:'',type:'normal'};
  graphEditor = {project:state.project, revision:state.data.graph_revision, draft, original,
    selected:Object.hasOwn(draft.nodes,id) ? id : Object.keys(draft.nodes)[0], saving:false};
  graphEditDialog.querySelector('.graph-edit-error').textContent = '';
  renderGraphEditor();
  graphEditDialog.showModal();
}

function renderGraphEditor() {
  const {draft, selected} = graphEditor;
  const nav = graphEditDialog.querySelector('.graph-edit-node-list');
  nav.replaceChildren();
  for (const id of Object.keys(draft.nodes)) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'btn'; button.textContent = id;
    button.setAttribute('aria-pressed', String(id === selected));
    button.onclick = () => { graphEditor.selected = id; renderGraphEditor(); };
    nav.appendChild(button);
  }
  const node = draft.nodes[selected];
  const body = graphEditDialog.querySelector('.graph-edit-body');
  body.innerHTML = `<div class="graph-edit-node-head"><h3>${escapeHtml(selected)}</h3><button type="button" class="btn graph-edit-danger" id="graph-delete-node" ${selected==='root'?'disabled':''}>Delete Node</button></div>
    <small>Node IDs stay fixed to preserve script references. The root node is the starting point and cannot be deleted.</small>
    <label style="margin-top:14px">Node Type<select id="graph-node-type"><option value="normal">Standard</option><option value="merge">Merge</option></select></label>
    <label>Summary<textarea id="graph-node-summary" required placeholder="Describe what happens in this node"></textarea></label>
    <div class="graph-edit-node-head"><h3>Outgoing Nodes & Branches</h3><button class="btn" type="button" id="graph-add-edge">＋ Add Connection</button></div>
    <small>Choice text is optional for a single connection and required for branching paths. A node with no outgoing connections is an endpoint.</small><div class="graph-edit-edges"></div>`;
  body.querySelector('#graph-node-type').value = node.type;
  body.querySelector('#graph-node-type').onchange = event => { node.type = event.target.value; };
  body.querySelector('#graph-node-summary').value = node.summary;
  body.querySelector('#graph-node-summary').oninput = event => { node.summary = event.target.value; };
  body.querySelector('#graph-delete-node').onclick = deleteGraphEditorNode;
  body.querySelector('#graph-add-edge').onclick = () => {
    const target = Object.keys(draft.nodes).find(id => id !== selected && id !== 'root' && !draft.edges.some(e => e.from === selected && e.to === id));
    if (!target) { graphEditDialog.querySelector('.graph-edit-error').textContent = 'Add another node before creating a connection.'; return; }
    draft.edges.push({from:selected,to:target,choice_text:null});
    renderGraphEditorEdges();
  };
  renderGraphEditorEdges();
}

function renderGraphEditorEdges() {
  const {draft, selected} = graphEditor;
  const container = graphEditDialog.querySelector('.graph-edit-edges');
  container.replaceChildren();
  for (const edge of draft.edges.filter(e => e.from === selected)) {
    const row = document.createElement('div'); row.className = 'graph-edit-edge';
    row.innerHTML = '<label>Target node<select></select></label><label>Choice text<input placeholder="Leave blank for a direct transition"></label><button class="btn graph-edit-danger" type="button" aria-label="Delete connection">×</button>';
    const select = row.querySelector('select');
    for (const id of Object.keys(draft.nodes).filter(id => id !== selected && id !== 'root')) {
      const option = document.createElement('option'); option.value = id; option.textContent = id; select.appendChild(option);
    }
    select.value = edge.to;
    select.onchange = () => { edge.to = select.value; };
    const input = row.querySelector('input'); input.value = edge.choice_text || '';
    input.oninput = () => { edge.choice_text = input.value || null; };
    row.querySelector('button').onclick = () => { draft.edges.splice(draft.edges.indexOf(edge),1); renderGraphEditorEdges(); };
    container.appendChild(row);
  }
}

function deleteGraphEditorNode() {
  const {draft,selected} = graphEditor;
  if (selected === 'root' || !confirm(`Delete ${selected}  and its connections? Existing scripts and assets will be kept.`)) return;
  delete draft.nodes[selected];
  draft.edges = draft.edges.filter(edge => edge.from !== selected && edge.to !== selected);
  graphEditor.selected = 'root'; renderGraphEditor();
}

graphEditDialog.querySelector('#graph-add-node').onclick = () => {
  const {draft, selected} = graphEditor;
  let number = 1;
  while (Object.hasOwn(draft.nodes,`node${number}`) || (state.data.story || []).some(node => node.id === `node${number}`)) number++;
  const id = `node${number}`;
  draft.nodes[id] = {id,summary:'',type:'normal'};
  draft.edges.push({from:selected,to:id,choice_text:null});
  graphEditor.selected = id; renderGraphEditor();
  graphEditDialog.querySelector('#graph-node-summary').focus();
};

function closeGraphEditor() {
  if (graphEditor?.saving) return;
  if (graphEditor && JSON.stringify(graphEditor.draft) !== graphEditor.original && !confirm('Discard unsaved changes to the story graph?')) return;
  graphEditDialog.close(); graphEditor = null;
}
graphEditDialog.querySelector('#graph-edit-cancel').onclick = closeGraphEditor;
graphEditDialog.addEventListener('cancel', event => { event.preventDefault(); closeGraphEditor(); });
window.addEventListener('beforeunload', event => {
  if (graphEditor && JSON.stringify(graphEditor.draft) !== graphEditor.original) { event.preventDefault(); event.returnValue = ''; }
});

graphEditDialog.querySelector('form').onsubmit = async event => {
  event.preventDefault();
  const editor = graphEditor;
  if (!editor || editor.saving) return;
  const error = graphEditDialog.querySelector('.graph-edit-error');
  error.textContent = '';
  editor.saving = true;
  graphEditDialog.querySelector('fieldset').disabled = true;
  graphEditDialog.querySelectorAll('footer button').forEach(button => button.disabled = true);
  try {
    await api('/api/graph', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project:editor.project,graph:editor.draft,revision:editor.revision})});
    graphEditDialog.close(); graphEditor = null;
    if (state.project === editor.project) {
      await loadProject();
      selectGraphNode(editor.selected);
    }
    toast('Story graph saved and backed up. Existing scripts are unchanged.');
  } catch (exception) {
    if (graphEditor) error.textContent = exception.message;
    else toast(`Story graph saved, but refresh failed: ${exception.message}`);
  } finally {
    editor.saving = false;
    graphEditDialog.querySelector('fieldset').disabled = false;
    graphEditDialog.querySelectorAll('footer button').forEach(button => button.disabled = false);
  }
};
