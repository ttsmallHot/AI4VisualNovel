const {test} = require('node:test');
const assert = require('node:assert/strict');
const {NovelPlayer} = require('../dashboard/static/player.js');
test('scene, sprites, dialogue, choices and jumps', () => {
  const p = new NovelPlayer({story:[{id:'root',lines:[
    {type:'scene',value:'天台'}, {type:'image',speaker:'甲',expression:'happy'},
    {type:'dialogue',speaker:'甲',text:'你好'},
    {type:'choice',text:'继续',target:'next'}, {type:'choice',text:'缺失',target:'missing'}
  ]},{id:'next',lines:[{type:'cg',id:'event'}, {type:'narration',text:'结尾'}]}]});
  assert.equal(p.advance().text,'你好'); assert.equal(p.scene,'天台'); assert.equal(p.cast.get('甲'),'happy');
  assert.equal(p.advance().choices.length,2);
  assert.equal(p.advance('next').text,'结尾'); assert.equal(p.cg,'event'); assert.equal(p.cast.size,0);
  assert.equal(p.advance().type,'end');
});
test('missing targets and jump loops report errors', () => {
  const p = new NovelPlayer({story:[{id:'root',lines:[{type:'jump',target:'root'}]}]});
  assert.equal(p.advance().type,'error');
  assert.equal(p.advance('missing').type,'error');
});
test('empty stories and unsupported conditions are explicit', () => {
  assert.equal(new NovelPlayer({}).nodes.size,0);
  const p = new NovelPlayer({story:[{id:'root',lines:[{type:'raw',text:'[IF: 甲 >= 3]'}]}]});
  assert.equal(p.advance().type,'error');
});
test('Pygame semantics: replace portraits, hide for narration, preserve CG', () => {
  const p = new NovelPlayer({story:[{id:'root',lines:[
    {type:'image',speaker:'甲',expression:'happy'}, {type:'dialogue',speaker:'甲',text:'甲说话'},
    {type:'image',speaker:'乙',expression:'neutral'}, {type:'dialogue',speaker:'乙',text:'乙说话'},
    {type:'image',speaker:'乙',expression:'sad'}, {type:'dialogue',speaker:'乙',text:'换表情'},
    {type:'narration',text:'旁白'}, {type:'dialogue',speaker:'甲',text:'无新立绘指令'},
    {type:'image',speaker:'甲',expression:'happy'}, {type:'dialogue',speaker:'甲',text:'再次出现'},
    {type:'cg',id:'event'}, {type:'dialogue',speaker:'甲',text:'CG对白'},
    {type:'narration',text:'CG旁白'},
    {type:'image',speaker:'乙',expression:'neutral'}, {type:'dialogue',speaker:'乙',text:'回到立绘'}
  ]}]});
  p.advance(); assert.deepEqual([...p.cast], [['甲','happy']]);
  p.advance(); assert.deepEqual([...p.cast], [['乙','neutral']]);
  p.advance(); assert.deepEqual([...p.cast], [['乙','sad']]);
  p.advance(); assert.equal(p.cast.size,0);
  p.advance(); assert.equal(p.cast.size,0);
  p.advance(); assert.deepEqual([...p.cast], [['甲','happy']]);
  p.advance(); assert.equal(p.cast.size,0); assert.equal(p.cg,'event');
  p.advance(); assert.equal(p.cast.size,0); assert.equal(p.cg,'event');
  p.advance(); assert.deepEqual([...p.cast], [['乙','neutral']]); assert.equal(p.cg,'');
});
