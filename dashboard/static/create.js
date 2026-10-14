const $ = id => document.getElementById(id);
const images = new WeakMap();
let submitting = false;
if (localStorage.getItem('a4vn-theme') === 'dark') document.documentElement.dataset.theme = 'dark';
$('theme').onclick = () => { const dark = document.documentElement.dataset.theme !== 'dark'; document.documentElement.dataset.theme = dark ? 'dark' : ''; localStorage.setItem('a4vn-theme', dark ? 'dark' : 'light'); };
function updateCharacters() {
  const rows = [...$('characters').children];
  rows.forEach((row, index) => row.querySelector('h3').textContent = `Character ${index + 1}`);
  $('add-character').disabled = rows.length >= 20;
}
$('add-character').onclick = () => {
  if ($('characters').children.length >= 20) return;
  const row = $('character-template').content.firstElementChild.cloneNode(true);
  row.dataset.id = `oc_${crypto.randomUUID().replaceAll('-', '')}`;
  const input = row.querySelector('.image'), preview = row.querySelector('img'), clear = row.querySelector('.clear-image'), error = row.querySelector('.image-error');
  function clearImage(resetInput = true) { images.delete(row); preview.removeAttribute('src'); preview.hidden = true; clear.hidden = true; row.querySelector('.upload-placeholder').hidden = false; if(resetInput) input.value = ''; error.textContent = ''; }
  clear.onclick = () => clearImage();
  input.onchange = () => {
    const file = input.files[0];
    clearImage(false);
    if (!file) return;
    if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 8 * 1024 * 1024) { error.textContent = 'Choose a PNG, JPEG, or WebP image up to 8 MB.'; return; }
    images.set(row, file); preview.src = URL.createObjectURL(file); preview.hidden = false; clear.hidden = false; row.querySelector('.upload-placeholder').hidden = true;
    preview.onload = () => URL.revokeObjectURL(preview.src);
    preview.onerror = () => { URL.revokeObjectURL(preview.src); clearImage(); error.textContent = 'Unable to read this image. Please choose another file.'; };
  };
  row.querySelector('.remove').onclick = () => { clearImage(); row.remove(); updateCharacters(); };
  $('characters').appendChild(row);
  if ($('characters').children.length > Number($('character-count').value)) $('character-count').value = $('characters').children.length;
  if ($('characters').children.length === 1) row.querySelector('.protagonist').checked = true;
  updateCharacters(); row.querySelector('.name').focus();
};
function dataUrl(file) { return new Promise((resolve,reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('Unable to read this image. Please choose another file.')); reader.readAsDataURL(file); }); }
$('create-form').onsubmit = async event => {
  event.preventDefault(); if (submitting) return;
  const rows = [...$('characters').children], count = Number($('character-count').value);
  $('error').textContent = '';
  if (rows.length > count) { $('error').textContent = 'Increase the total character count to include all added characters.'; return; }
  if (rows.reduce((sum,row) => sum + (images.get(row)?.size || 0), 0) > 24 * 1024 * 1024) { $('error').textContent = 'Character images must total no more than 24 MB.'; return; }
  submitting = true; $('submit').disabled = true; $('submit').textContent = 'Saving game and characters…';
  try {
    const characters = await Promise.all(rows.map(async row => {
      const item = {id:row.dataset.id, is_protagonist:row.querySelector('.protagonist').checked};
      for (const key of ['name','gender','personality','appearance','background']) item[key] = row.querySelector('.'+key).value.trim();
      if (images.has(row)) item.neutral_image_data = await dataUrl(images.get(row));
      return item;
    }));
    const response = await fetch('/api/projects', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:$('title').value.trim(),story_requirements:$('story').value.trim(),character_count:count,characters})});
    const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Unable to create game');
    location.href = `/#project=${encodeURIComponent(result.project)}&view=overview`;
  } catch (error) { $('error').textContent = error.message; submitting = false; $('submit').disabled = false; $('submit').textContent = 'Create Game'; }
};
