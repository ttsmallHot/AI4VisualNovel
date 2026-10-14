/* A small browser player for Dashboard's parsed story format. */
class NovelPlayer {
  constructor(data) {
    this.nodes = new Map((data.story || []).map(node => [node.id, node.lines]));
    this.node = this.nodes.has('root') ? 'root' : this.nodes.keys().next().value;
    this.index = 0;
    this.scene = '';
    this.cg = '';
    this.cast = new Map();
    this.frame = {type:'title'};
  }
  advance(target) {
    if (target !== undefined) {
      if (!this.nodes.has(target)) return this.frame = {type:'error', text:`Target node ${target}  has no script yet.`};
      this.node = target;
      this.index = 0;
    }
    for (let step = 0; step < 1000; step++) {
      const lines = this.nodes.get(this.node) || [];
      if (this.index >= lines.length) return this.frame = {type:'end', text:'End of this story segment'};
      const line = lines[this.index++];
      if (line.type === 'scene') { this.scene = line.value; this.cg = ''; this.cast.clear(); }
      else if (line.type === 'image') {
        this.cg = '';
        // Match Pygame's single current_character_image, not a persistent cast.
        this.cast.clear();
        this.cast.set(line.speaker, line.expression);
      }
      else if (line.type === 'cg') { this.cg = line.id; this.cast.clear(); }
      else if (line.type === 'jump') {
        if (!this.nodes.has(line.target)) return this.frame = {type:'error', text:`Target node ${line.target}  has no script yet.`};
        this.node = line.target; this.index = 0;
      } else if (line.type === 'choice') {
        const choices = [line];
        while (lines[this.index]?.type === 'choice') choices.push(lines[this.index++]);
        return this.frame = {type:'choice', choices};
      } else if (['dialogue','narration'].includes(line.type)) {
        if (line.type === 'narration') this.cast.clear();
        return this.frame = line;
      }
      else if (line.type === 'raw' && /^\[(IF|ELSE|ENDIF)/.test(line.text)) {
        return this.frame = {type:'error', text:'This script uses conditional commands, which the browser player does not yet support.'};
      }
    }
    return this.frame = {type:'error', text:'A loop was detected in the script. Check the node connections.'};
  }
}
if (typeof module !== 'undefined') module.exports = {NovelPlayer};

if (typeof document !== 'undefined') {
  let player, dataRef;
  const stem = asset => asset.name.replace(/\.[^.]+$/, '');
  function assetFor(category, names, group) {
    const stems = names.filter(Boolean).flatMap(name => [name, name.replace(/[^\p{L}\p{N}_\s-]/gu, '').trim().replaceAll(' ', '_')]);
    return (state.data.assets || []).find(asset => asset.category === category && stems.includes(stem(asset)) && (!group || group.includes(asset.group)));
  }
  function makeImage(asset, className, alt) {
    const img = document.createElement('img');
    img.className = className; img.src = asset.url; img.alt = alt;
    img.addEventListener('error', () => img.remove());
    return img;
  }
  window.renderGame = function() {
    if (!state.data) return;
    if (dataRef !== state.data) { dataRef = state.data; player = new NovelPlayer(state.data); }
    const stage = document.getElementById('game-stage');
    stage.replaceChildren();
    const frame = player.frame, design = state.data.design || {};
    stage.classList.toggle('vn-title-stage', frame.type === 'title');
    if (frame.type === 'title') {
      const openingScene = (player.nodes.get(player.node) || []).find(line => line.type === 'scene')?.value;
      const setting = (design.scenes || []).find(scene => scene.name === openingScene || scene.id === openingScene);
      const cover = assetFor('scene',[openingScene,setting?.id,setting?.name]) || (state.data.assets || []).find(asset => asset.category === 'scene');
      if (cover) stage.appendChild(makeImage(cover,'vn-background','Game cover'));
      const screen = document.createElement('div'); screen.className = 'vn-title-screen';
      const label = document.createElement('div'); label.className = 'vn-title-label'; label.textContent = 'VISUAL NOVEL';
      const title = document.createElement('h2'); title.className = 'vn-title-name';
      title.textContent = design.title || state.data.metadata?.title || state.project;
      const rule = document.createElement('div'); rule.className = 'vn-title-rule'; rule.setAttribute('aria-hidden','true');
      const intro = document.createElement('p'); intro.className = 'vn-title-intro';
      intro.textContent = player.nodes.size ? (design.background || state.data.metadata?.description || 'Every choice leads to a different story.') : 'This project has no playable script yet.';
      screen.append(label,title,rule,intro);
      if (player.nodes.size) {
        const start = document.createElement('button'); start.className = 'vn-title-start'; start.type = 'button'; start.textContent = 'Start Game';
        start.onclick = () => {player.advance();renderGame();}; screen.appendChild(start);
      }
      stage.appendChild(screen);
      document.getElementById('game-progress').textContent = 'Title screen';
      return;
    }
    const scene = (design.scenes || []).find(item => item.name === player.scene || item.id === player.scene);
    const background = player.cg ? assetFor('cg',[player.cg]) : assetFor('scene',[player.scene,scene?.id,scene?.name]);
    if (background) stage.appendChild(makeImage(background,'vn-background',player.cg || player.scene));
    const cast = document.createElement('div'); cast.className = 'vn-cast';
    for (const [name, expression] of player.cast) {
      const character = (design.characters || []).find(item => item.name === name || item.id === name);
      const groups = [name,character?.id];
      const asset = assetFor('character',[expression],groups) || assetFor('character',['neutral'],groups);
      if (asset) cast.appendChild(makeImage(asset,'vn-character',name));
    }
    stage.appendChild(cast);
    const box = document.createElement('div'); box.className = frame.type === 'choice' ? 'vn-choice-menu' : 'vn-dialogue';
    if (frame.type === 'choice') { box.setAttribute('role','group'); box.setAttribute('aria-label','Story choices'); }
    const heading = document.createElement('div'); heading.className = 'vn-speaker';
    heading.textContent = frame.speaker || (frame.type === 'choice' ? 'Make a choice' : '');
    box.appendChild(heading);
    const text = document.createElement('div'); text.className = 'vn-text';
    text.textContent = frame.text || '';
    box.appendChild(text);
    const controls = document.createElement('div'); controls.className = 'vn-controls';
    function button(label, action) { const el = document.createElement('button'); el.className='btn'; el.textContent=label; el.onclick=action;controls.appendChild(el); }
    if (frame.type === 'choice') {
      for (const choice of frame.choices) button(choice.text, () => {player.advance(choice.target); renderGame();});
    } else if (['dialogue','narration'].includes(frame.type) && player.nodes.size) {
      box.classList.add('vn-can-advance');
      const advance = () => {player.advance();renderGame();};
      const next = document.createElement('button'); next.type = 'button'; next.className = 'vn-advance';
      next.textContent = 'Click to continue'; next.setAttribute('aria-label','Continue');
      next.onclick = event => {
        event.stopPropagation(); advance();
        if (event.detail === 0) stage.querySelector('.vn-advance, .vn-choice-menu button')?.focus({preventScroll:true});
      };
      controls.appendChild(next);
      let down;
      box.addEventListener('pointerdown', event => {down = {x:event.clientX,y:event.clientY};});
      box.addEventListener('click', event => {
        if (event.target.closest('button') || window.getSelection()?.toString()) return;
        if (!down || Math.abs(event.clientX-down.x)+Math.abs(event.clientY-down.y)>8) return;
        advance();
      });
    }
    box.appendChild(controls); stage.appendChild(box);
    document.getElementById('game-progress').textContent = `${player.node || ''} · ${player.scene || 'Story'}`;
  };
  window.restartGame = function() {
    if (!state.data || !confirm('Restart this game?')) return;
    player = new NovelPlayer(state.data); dataRef = state.data; renderGame();
  };
}
