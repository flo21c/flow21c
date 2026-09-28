/* =========================================================
   FlowMind - 마인드맵 노트
   Electron 안에서도, 브라우저에서 그냥 열어도 동일하게 동작한다.
   ========================================================= */
'use strict';

/* ---------- 상수 ---------- */
const PALETTE = ['#e05252', '#e0873f', '#d9b23c', '#4ec98a', '#3fb6c9', '#5b8cff', '#a06bdc', '#d95f9a'];
const FONT_STACK = '"Pretendard","Malgun Gothic","맑은 고딕",-apple-system,"Segoe UI",sans-serif';
const MAX_TEXT_W = 220;
const GAP_X = 64;   // 단계 사이 가로 간격 (메인 → 서브)
const GAP_Y = 18;   // 같은 단계 노드 사이 세로 간격
const AUTOSAVE_KEY = 'flowmind:doc';
const VIEW_KEY = 'flowmind:view';
const THEME_KEY = 'flowmind:theme';

/* ---------- DOM ---------- */
const $ = (s) => document.querySelector(s);
const stage = $('#stage');
const world = $('#world');
const edgesSvg = $('#edges');
const nodesLayer = $('#nodes');
const zoomBadge = $('#zoomBadge');
const toastEl = $('#toast');
const fileNameEl = $('#fileName');
const saveStateEl = $('#saveState');

/* ---------- 상태 ---------- */
let doc = null;            // { rootId, nodes: {id: node} }
let selected = null;       // 선택된 노드 id
let editing = null;        // 편집 중인 노드 id
let fileName = '제목 없음';
const view = { tx: 0, ty: 0, s: 1 };
const elMap = new Map();   // id -> DOM element
const undoStack = [];
const redoStack = [];

let uid = 1;
const newId = () => 'n' + (uid++);

/* =========================================================
   1. 문서 모델
   ========================================================= */
function makeNode(text, parent) {
  return { id: newId(), text, parent: parent || null, children: [], x: 0, y: 0, color: 0, collapsed: false, note: '' };
}

/** 주석에 실제 내용(글자 또는 사진)이 있는지 */
function hasNote(n) {
  if (!n || !n.note) return false;
  if (/<img\b/i.test(n.note)) return true;
  return n.note.replace(/<[^>]*>/g, '').replace(/[\s​ ]/g, '') !== '';
}

function blankDoc() {
  const nodes = {};
  const rootNode = makeNode('중심 주제', null);
  nodes[rootNode.id] = rootNode;
  ['첫 번째 가지', '두 번째 가지', '세 번째 가지'].forEach((t, i) => {
    const c = makeNode(t, rootNode.id);
    c.color = i + 4;
    nodes[c.id] = c;
    rootNode.children.push(c.id);
  });
  return { rootId: rootNode.id, nodes };
}

const node = (id) => doc.nodes[id];
const root = () => doc.nodes[doc.rootId];

/** 접힌 조상이 없어 화면에 보이는 노드들 */
function visibleNodes() {
  const out = [];
  (function walk(id) {
    const n = node(id);
    if (!n) return;
    out.push(n);
    if (!n.collapsed) n.children.forEach(walk);
  })(doc.rootId);
  return out;
}

/** 자기 자신과 모든 하위 노드 */
function descendants(id, includeSelf) {
  const out = [];
  (function walk(i) {
    const n = node(i);
    if (!n) return;
    out.push(n);
    n.children.forEach(walk);
  })(id);
  return includeSelf ? out : out.slice(1);
}

/* =========================================================
   2. 텍스트 측정 / 크기 계산
   ========================================================= */
const measureCtx = document.createElement('canvas').getContext('2d');

function fontOf(n) {
  return n.id === doc.rootId ? '700 16px ' + FONT_STACK : '400 14px ' + FONT_STACK;
}

function metricsOf(n) {
  const isRoot = n.id === doc.rootId;
  return { lh: isRoot ? 22 : 20, padX: isRoot ? 18 : 14, padY: isRoot ? 10 : 8, minW: isRoot ? 110 : 80 };
}

/** 최대 폭에 맞춰 줄을 나눈다. 공백 없는 한글 문장도 글자 단위로 끊어준다. */
function wrapText(text, font) {
  measureCtx.font = font;
  const lines = [];
  for (const para of String(text).split('\n')) {
    if (para === '') { lines.push(''); continue; }
    let line = '';
    for (const ch of para) {
      const test = line + ch;
      if (line !== '' && measureCtx.measureText(test).width > MAX_TEXT_W) {
        const sp = line.lastIndexOf(' ');
        if (sp > 0 && measureCtx.measureText(line.slice(sp + 1) + ch).width <= MAX_TEXT_W) {
          lines.push(line.slice(0, sp));
          line = line.slice(sp + 1) + ch;
        } else {
          lines.push(line);
          line = ch;
        }
      } else {
        line = test;
      }
    }
    lines.push(line);
  }
  return lines;
}

/** n.lines / n.w / n.h 를 채운다 (저장 대상이 아니라 매번 다시 계산) */
function measure(n) {
  const font = fontOf(n);
  const m = metricsOf(n);
  const lines = wrapText(n.text || ' ', font);
  measureCtx.font = font;
  let w = 0;
  for (const l of lines) w = Math.max(w, measureCtx.measureText(l).width);
  n.lines = lines;
  // border-box 기준이라 좌우 테두리(1.5px)와 반올림 오차만큼 여유를 더한다.
  n.w = Math.max(m.minW, Math.ceil(w) + m.padX * 2 + 5);
  n.h = lines.length * m.lh + m.padY * 2;
}

function measureAll() { Object.values(doc.nodes).forEach(measure); }

/* =========================================================
   3. 배치
   ========================================================= */
/** 전체 자동 정렬 (오른쪽으로 뻗는 트리) */
function autoLayout() {
  measureAll();
  const r = root();
  const subH = new Map();

  (function height(n) {
    if (n.collapsed || !n.children.length) { subH.set(n.id, n.h); return n.h; }
    let t = 0;
    n.children.forEach((cid, i) => { t += height(node(cid)) + (i ? GAP_Y : 0); });
    const v = Math.max(n.h, t);
    subH.set(n.id, v);
    return v;
  })(r);

  (function place(n, x, cy) {
    n.x = x;
    n.y = cy - n.h / 2;
    if (n.collapsed || !n.children.length) return;
    let tot = 0;
    n.children.forEach((cid, i) => { tot += subH.get(cid) + (i ? GAP_Y : 0); });
    let y = cy - tot / 2;
    for (const cid of n.children) {
      const c = node(cid);
      const ch = subH.get(cid);
      place(c, x + n.w + GAP_X, y + ch / 2);
      y += ch + GAP_Y;
    }
  })(r, 0, 0);
}

/** 새 노드가 기존 노드와 겹치지 않을 때까지 아래로 밀어낸다. */
function resolveOverlap(target) {
  const others = visibleNodes().filter((n) => n.id !== target.id);
  for (let guard = 0; guard < 300; guard++) {
    let hit = null;
    for (const o of others) {
      if (target.x < o.x + o.w + 10 && target.x + target.w + 10 > o.x &&
          target.y < o.y + o.h + 8 && target.y + target.h + 8 > o.y) { hit = o; break; }
    }
    if (!hit) return;
    target.y = hit.y + hit.h + GAP_Y;
  }
}

/* =========================================================
   4. 렌더링
   ========================================================= */
function applyView() {
  world.style.transform = 'translate(' + view.tx + 'px,' + view.ty + 'px) scale(' + view.s + ')';
  zoomBadge.textContent = Math.round(view.s * 100) + '%';
}

function render() {
  measureAll();
  nodesLayer.textContent = '';
  elMap.clear();

  for (const n of visibleNodes()) {
    const el = document.createElement('div');
    el.className = 'node'
      + (n.id === doc.rootId ? ' root' : '')
      + (n.color ? ' colored' : '')
      + (n.id === selected ? ' selected' : '');
    el.dataset.id = n.id;
    el.style.left = n.x + 'px';
    el.style.top = n.y + 'px';
    el.style.width = n.w + 'px';
    if (n.color) {
      el.style.background = PALETTE[n.color - 1];
      el.style.borderColor = PALETTE[n.color - 1];
    }

    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = n.text;
    el.appendChild(label);

    if (hasNote(n)) {
      const mark = document.createElement('span');
      mark.className = 'note-mark';
      mark.title = '주석이 있습니다';
      el.appendChild(mark);
    }

    if (n.children.length) {
      const tg = document.createElement('button');
      tg.className = 'toggle' + (n.collapsed ? ' count' : '');
      tg.textContent = n.collapsed ? String(descendants(n.id).length) : '−';
      tg.title = n.collapsed ? '펴기 (Space)' : '접기 (Space)';
      tg.addEventListener('mousedown', (e) => e.stopPropagation());
      tg.addEventListener('click', (e) => { e.stopPropagation(); toggleCollapse(n.id); });
      el.appendChild(tg);
    }

    nodesLayer.appendChild(el);
    elMap.set(n.id, el);
  }
  drawEdges();
  syncNotePanel();
}

/** 드래그 중에는 위치만 갱신해 성능을 지킨다. */
function updatePositions() {
  for (const [id, el] of elMap) {
    const n = node(id);
    if (!n) continue;
    el.style.left = n.x + 'px';
    el.style.top = n.y + 'px';
  }
  drawEdges();
}

function edgePath(p, c) {
  const x1 = p.x + p.w, y1 = p.y + p.h / 2;
  const x2 = c.x, y2 = c.y + c.h / 2;
  const dx = Math.max(28, Math.abs(x2 - x1) / 2);
  return 'M ' + x1 + ' ' + y1 + ' C ' + (x1 + dx) + ' ' + y1 + ', ' + (x2 - dx) + ' ' + y2 + ', ' + x2 + ' ' + y2;
}

function drawEdges() {
  const css = getComputedStyle(document.documentElement);
  const base = css.getPropertyValue('--edge').trim() || '#4a5165';
  let out = '';
  for (const p of visibleNodes()) {
    if (p.collapsed) continue;
    for (const cid of p.children) {
      const c = node(cid);
      if (!c) continue;
      const color = c.color ? PALETTE[c.color - 1] : base;
      const wdt = p.id === doc.rootId ? 2.4 : 1.8;
      out += '<path d="' + edgePath(p, c) + '" fill="none" stroke="' + color
           + '" stroke-width="' + wdt + '" stroke-linecap="round" opacity="0.9"/>';
    }
  }
  edgesSvg.innerHTML = out;
}

/* =========================================================
   5. 편집 동작
   ========================================================= */
function snapshot() {
  return JSON.stringify({ rootId: doc.rootId, nodes: doc.nodes, uid: uid });
}

function pushHistory() {
  undoStack.push(snapshot());
  if (undoStack.length > 120) undoStack.shift();
  redoStack.length = 0;
}

function restore(json) {
  const d = JSON.parse(json);
  doc = { rootId: d.rootId, nodes: d.nodes };
  uid = d.uid || uid;
  if (!doc.nodes[selected]) selected = doc.rootId;
  noteNodeId = null;          // 되돌린 주석이 편집기에 다시 실리도록
}

function undo() {
  if (!undoStack.length) { toast('되돌릴 작업이 없습니다'); return; }
  redoStack.push(snapshot());
  restore(undoStack.pop());
  render();
  scheduleSave();
}

function redo() {
  if (!redoStack.length) { toast('다시 실행할 작업이 없습니다'); return; }
  undoStack.push(snapshot());
  restore(redoStack.pop());
  render();
  scheduleSave();
}

function select(id) {
  selected = id;
  for (const [nid, el] of elMap) el.classList.toggle('selected', nid === id);
  syncNotePanel();
}

/** 화면에서 말하는 "서브 노드" 추가 - 선택한 노드의 한 단계 아래에 붙는다 */
function addChild(parentId) {
  const p = node(parentId);
  if (!p) return;
  pushHistory();
  if (p.collapsed) p.collapsed = false;
  const n = makeNode('새 노드', p.id);
  n.color = p.id === doc.rootId ? 0 : p.color;
  doc.nodes[n.id] = n;
  measure(p); measure(n);
  n.x = p.x + p.w + GAP_X;
  const last = p.children.length ? node(p.children[p.children.length - 1]) : null;
  if (last) { measure(last); n.y = last.y + last.h + GAP_Y; }
  else n.y = p.y + p.h / 2 - n.h / 2;
  p.children.push(n.id);
  resolveOverlap(n);
  selected = n.id;
  render();
  startEdit(n.id, true);
  scheduleSave();
}

/** 화면에서 말하는 "메인 노드" 추가 - 선택한 노드와 같은 단계에 나란히 붙는다 */
function addSibling(id) {
  const cur = node(id);
  if (!cur) return;
  if (!cur.parent) { addChild(id); return; }   // 중심 노드에서는 서브 노드 추가로 동작
  const p = node(cur.parent);
  pushHistory();
  const n = makeNode('새 노드', p.id);
  n.color = cur.color;
  doc.nodes[n.id] = n;
  measure(cur); measure(n);
  n.x = cur.x;
  n.y = cur.y + cur.h + GAP_Y;
  p.children.splice(p.children.indexOf(id) + 1, 0, n.id);
  resolveOverlap(n);
  selected = n.id;
  render();
  startEdit(n.id, true);
  scheduleSave();
}

function removeNode(id) {
  const n = node(id);
  if (!n) return;
  if (id === doc.rootId) { toast('중심 노드는 삭제할 수 없습니다'); return; }
  pushHistory();
  const p = node(n.parent);
  const idx = p.children.indexOf(id);
  descendants(id, true).forEach((d) => { delete doc.nodes[d.id]; });
  p.children.splice(idx, 1);
  selected = p.children[Math.min(idx, p.children.length - 1)] || p.id;
  render();
  scheduleSave();
}

function toggleCollapse(id) {
  const n = node(id);
  if (!n || !n.children.length) return;
  pushHistory();
  n.collapsed = !n.collapsed;
  render();
  scheduleSave();
}

function setColor(id, color) {
  const n = node(id);
  if (!n) return;
  pushHistory();
  n.color = color;
  render();
  scheduleSave();
}

/* ---------- 인라인 편집 ---------- */
function startEdit(id, selectAll) {
  const el = elMap.get(id);
  if (!el) return;
  editing = id;
  const before = snapshot();
  el.classList.add('editing');
  const label = el.querySelector('.label');
  label.contentEditable = 'true';
  label.focus();

  const range = document.createRange();
  range.selectNodeContents(label);
  const sel = window.getSelection();
  sel.removeAllRanges();
  if (!selectAll) range.collapse(false);
  sel.addRange(range);

  function finish(cancel) {
    if (editing !== id) return;
    editing = null;
    label.contentEditable = 'false';
    el.classList.remove('editing');
    label.removeEventListener('keydown', onKey);
    label.removeEventListener('blur', onBlur);
    const n = node(id);
    if (!n) return;
    if (cancel) {
      label.textContent = n.text;
    } else {
      const txt = label.innerText.replace(/ /g, ' ').replace(/\n+$/, '').trim();
      if (txt !== n.text) {
        undoStack.push(before);
        redoStack.length = 0;
        n.text = txt || '새 노드';
      }
    }
    render();
    scheduleSave();
  }

  function onKey(e) {
    e.stopPropagation();
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); finish(false); }
    else if (e.key === 'Escape') { e.preventDefault(); finish(true); }
    else if (e.key === 'Tab') { e.preventDefault(); finish(false); addChild(id); }
  }
  function onBlur() { finish(false); }

  label.addEventListener('keydown', onKey);
  label.addEventListener('blur', onBlur);
}

/* ---------- 방향키 이동 ---------- */
function navigate(dir) {
  const cur = node(selected);
  if (!cur) return;
  if (dir === 'left' && cur.parent) { select(cur.parent); return; }
  if (dir === 'right') {
    if (cur.collapsed && cur.children.length) { toggleCollapse(cur.id); return; }
    if (cur.children.length) select(cur.children[0]);
    return;
  }
  const list = visibleNodes().filter((n) => n.id !== cur.id);
  const cx = cur.x + cur.w / 2, cy = cur.y + cur.h / 2;
  let best = null, bestScore = Infinity;
  for (const n of list) {
    const dy = (n.y + n.h / 2) - cy;
    const dx = (n.x + n.w / 2) - cx;
    if (dir === 'up' && dy >= -4) continue;
    if (dir === 'down' && dy <= 4) continue;
    const score = Math.abs(dy) + Math.abs(dx) * 1.6;
    if (score < bestScore) { bestScore = score; best = n; }
  }
  if (best) select(best.id);
}

/* =========================================================
   6. 마우스 조작 (드래그 / 화면 이동 / 확대·축소)
   ========================================================= */
let drag = null;

stage.addEventListener('mousedown', (e) => {
  if (e.button !== 0 && e.button !== 1) return;
  const nodeEl = e.target.closest ? e.target.closest('.node') : null;

  if (nodeEl && e.button === 0) {
    const id = nodeEl.dataset.id;
    if (editing === id) return;                       // 편집 중이면 텍스트 선택 우선
    if (editing && document.activeElement) document.activeElement.blur();
    select(id);
    const moving = descendants(id, true);
    drag = {
      type: 'node',
      id: id,
      sx: e.clientX, sy: e.clientY, moved: false,
      start: moving.map((n) => ({ n: n, x: n.x, y: n.y })),
      before: snapshot()
    };
  } else {
    if (editing && document.activeElement) document.activeElement.blur();
    drag = { type: 'pan', sx: e.clientX, sy: e.clientY, tx: view.tx, ty: view.ty, moved: false };
    stage.classList.add('panning');
  }
  e.preventDefault();
});

window.addEventListener('mousemove', (e) => {
  if (!drag) return;
  const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
  if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 3) return;
  drag.moved = true;

  if (drag.type === 'pan') {
    view.tx = drag.tx + dx;
    view.ty = drag.ty + dy;
    applyView();
  } else {
    const wx = dx / view.s, wy = dy / view.s;
    for (const s of drag.start) { s.n.x = s.x + wx; s.n.y = s.y + wy; }
    updatePositions();
  }
});

window.addEventListener('mouseup', () => {
  if (!drag) return;
  if (drag.type === 'node' && drag.moved) {
    undoStack.push(drag.before);
    redoStack.length = 0;
    scheduleSave();
  }
  if (drag.type === 'pan' && drag.moved) saveView();
  stage.classList.remove('panning');
  drag = null;
});

stage.addEventListener('dblclick', (e) => {
  const nodeEl = e.target.closest ? e.target.closest('.node') : null;
  if (nodeEl) startEdit(nodeEl.dataset.id, true);
});

stage.addEventListener('wheel', (e) => {
  e.preventDefault();
  const rect = stage.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  const ns = Math.min(3, Math.max(0.2, view.s * Math.exp(-e.deltaY * 0.0015)));
  view.tx = mx - (mx - view.tx) * (ns / view.s);
  view.ty = my - (my - view.ty) * (ns / view.s);
  view.s = ns;
  applyView();
  saveView();
}, { passive: false });

/* ---------- 화면 맞춤 ---------- */
function bbox(margin) {
  const list = visibleNodes();
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const n of list) {
    x1 = Math.min(x1, n.x); y1 = Math.min(y1, n.y);
    x2 = Math.max(x2, n.x + n.w); y2 = Math.max(y2, n.y + n.h);
  }
  const m = margin || 0;
  return { x: x1 - m, y: y1 - m, w: (x2 - x1) + m * 2, h: (y2 - y1) + m * 2 };
}

function fitToScreen() {
  measureAll();
  const b = bbox(50);
  const W = stage.clientWidth, H = stage.clientHeight;
  if (!W || !H || !isFinite(b.w) || b.w <= 0) return;
  view.s = Math.min(W / b.w, H / b.h, 1.3);
  view.tx = (W - b.w * view.s) / 2 - b.x * view.s;
  view.ty = (H - b.h * view.s) / 2 - b.y * view.s;
  applyView();
  saveView();
}

/* =========================================================
   7. 키보드
   ========================================================= */
window.addEventListener('keydown', (e) => {
  if (editing) return;
  if (licBlocked) return;                    // 체험 기간이 끝나면 아무 조작도 받지 않는다
  if (pngOpen) return;                       // 주석 고르기 창이 떠 있는 동안에는 양보한다
  const tag = (e.target.tagName || '').toLowerCase();
  const inNote = !!(e.target.closest && e.target.closest('#notePanel'));

  // 주석창 안에서는 파일 단축키만 통과시키고, 나머지는 글 작성에 양보한다
  if (inNote) {
    if (!(e.ctrlKey || e.metaKey)) return;
    const nk = e.key.toLowerCase();
    if (nk === 's') { e.preventDefault(); saveToFile(); }
    else if (nk === 'o') { e.preventDefault(); openFromFile(); }
    else if (nk === 'n') { e.preventDefault(); newDoc(); }
    else if (nk === 'e') { e.preventDefault(); requestPng(); }
    else if (nk === 'm') { e.preventDefault(); toggleNotePanel(); }
    return;
  }

  if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;

  if (e.ctrlKey || e.metaKey) {
    const k = e.key.toLowerCase();

    // Ctrl + =         서브 노드 추가 (한 단계 아래)
    // Ctrl + Shift + = 메인 노드 추가 (같은 단계)
    // e.code 로 보면 자판 배열이 달라도 같은 자리를 인식한다. 숫자패드 + 도 함께 받는다.
    if (e.code === 'Equal' || e.code === 'NumpadAdd' || k === '=' || k === '+') {
      e.preventDefault();
      if (e.shiftKey) addSibling(selected);
      else addChild(selected);
      return;
    }

    if (k === 'm') { e.preventDefault(); toggleNotePanel(); return; }
    if (k === 's') { e.preventDefault(); saveToFile(); return; }
    if (k === 'o') { e.preventDefault(); openFromFile(); return; }
    if (k === 'n') { e.preventDefault(); newDoc(); return; }
    if (k === 'e') { e.preventDefault(); requestPng(); return; }
    if (k === 'l') { e.preventDefault(); pushHistory(); autoLayout(); render(); fitToScreen(); scheduleSave(); return; }
    if (k === '0') { e.preventDefault(); fitToScreen(); return; }
    if (k === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return; }
    if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); redo(); return; }
    return;
  }

  switch (e.key) {
    case 'Tab':        e.preventDefault(); addChild(selected); break;
    case 'Enter':      e.preventDefault(); addSibling(selected); break;
    case 'F2':         e.preventDefault(); startEdit(selected, true); break;
    case 'Delete':
    case 'Backspace':  e.preventDefault(); removeNode(selected); break;
    case ' ':          e.preventDefault(); toggleCollapse(selected); break;
    case 'ArrowUp':    e.preventDefault(); navigate('up'); break;
    case 'ArrowDown':  e.preventDefault(); navigate('down'); break;
    case 'ArrowLeft':  e.preventDefault(); navigate('left'); break;
    case 'ArrowRight': e.preventDefault(); navigate('right'); break;
    default:
      if (/^[0-8]$/.test(e.key)) { e.preventDefault(); setColor(selected, Number(e.key)); }
  }
});

/* =========================================================
   8. 저장 / 열기 / 내보내기
   ========================================================= */
const bridge = window.flowmind || null;   // Electron이면 preload가 넣어준다

function serialize() {
  const clean = {};
  for (const id of Object.keys(doc.nodes)) {
    const n = doc.nodes[id];
    clean[id] = {
      id: n.id, text: n.text, parent: n.parent, children: n.children,
      x: n.x, y: n.y, color: n.color, collapsed: n.collapsed, note: n.note || ''
    };
  }
  return JSON.stringify({ app: 'flowmind', version: 1, rootId: doc.rootId, uid: uid, nodes: clean }, null, 2);
}

function deserialize(json) {
  const d = JSON.parse(json);
  if (!d || !d.rootId || !d.nodes || !d.nodes[d.rootId]) throw new Error('형식이 올바르지 않은 파일입니다');
  doc = { rootId: d.rootId, nodes: d.nodes };
  let maxN = 0;
  for (const id of Object.keys(d.nodes)) {
    if (typeof d.nodes[id].note !== 'string') d.nodes[id].note = '';  // 예전 파일 호환
    const m = /^n(\d+)$/.exec(id);
    if (m) maxN = Math.max(maxN, Number(m[1]));
  }
  uid = Math.max(d.uid || 1, maxN + 1);
  selected = doc.rootId;
  noteNodeId = null;
  undoStack.length = 0;
  redoStack.length = 0;
}

/* ---------- 자동 저장 ---------- */
let saveTimer = null;
function scheduleSave() {
  saveStateEl.textContent = '';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(AUTOSAVE_KEY, serialize());
      saveStateEl.textContent = '· 자동 저장됨';
      saveStateEl.className = 'saved';
    } catch (err) {
      console.warn('자동 저장 실패', err);
      saveStateEl.textContent = '· 자동 저장 실패';
      saveStateEl.className = '';
      // 사진이 많으면 브라우저 저장 용량(약 5MB)을 넘길 수 있다
      if (!quotaWarned) {
        quotaWarned = true;
        toast('자동 저장 용량을 넘었습니다. Ctrl+S로 파일에 저장해 주세요.');
      }
    }
  }, 400);
}

function saveView() {
  try { localStorage.setItem(VIEW_KEY, JSON.stringify(view)); } catch (e) { /* 무시 */ }
}

/* ---------- 파일로 저장 ---------- */
async function saveToFile() {
  const json = serialize();
  const base = (fileName === '제목 없음') ? sanitize(root().text) : fileName.replace(/\.json$/i, '');
  const suggested = base + '.json';
  try {
    if (bridge) {
      const r = await bridge.saveFile(json, suggested);
      if (r && r.ok) { fileName = r.name; fileNameEl.textContent = fileName; toast('저장했습니다'); }
      return;
    }
    if (window.showSaveFilePicker) {
      const handle = await window.showSaveFilePicker({
        suggestedName: suggested,
        types: [{ description: 'FlowMind 파일', accept: { 'application/json': ['.json'] } }]
      });
      const w = await handle.createWritable();
      await w.write(json);
      await w.close();
      fileName = handle.name;
      fileNameEl.textContent = fileName;
      toast('저장했습니다');
      return;
    }
    downloadBlob(new Blob([json], { type: 'application/json' }), suggested);
    toast('다운로드 폴더에 저장했습니다');
  } catch (err) {
    if (err && err.name === 'AbortError') return;
    toast('저장 실패: ' + err.message);
  }
}

/* ---------- 파일 열기 ---------- */
async function openFromFile() {
  try {
    if (bridge) {
      const r = await bridge.openFile();
      if (r && r.ok) loadJson(r.data, r.name);
      return;
    }
    if (window.showOpenFilePicker) {
      const picked = await window.showOpenFilePicker({
        types: [{ description: 'FlowMind 파일', accept: { 'application/json': ['.json'] } }]
      });
      const f = await picked[0].getFile();
      loadJson(await f.text(), f.name);
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.onchange = async () => {
      const f = input.files[0];
      if (f) loadJson(await f.text(), f.name);
    };
    input.click();
  } catch (err) {
    if (err && err.name === 'AbortError') return;
    toast('열기 실패: ' + err.message);
  }
}

function loadJson(text, name) {
  try {
    deserialize(text);
    fileName = name || '제목 없음';
    fileNameEl.textContent = fileName;
    render();
    fitToScreen();
    scheduleSave();
    toast('불러왔습니다');
  } catch (err) {
    toast('열기 실패: ' + err.message);
  }
}

function newDoc() {
  if (!confirm('새 마인드맵을 시작할까요? 저장하지 않은 내용은 사라집니다.')) return;
  uid = 1;
  doc = blankDoc();
  selected = doc.rootId;
  noteNodeId = null;
  fileName = '제목 없음';
  fileNameEl.textContent = fileName;
  undoStack.length = 0;
  redoStack.length = 0;
  autoLayout();
  render();
  fitToScreen();
  scheduleSave();
}

/* ---------- PNG 내보내기 ---------- */
function roundRect(ctx, x, y, w, h, r) {
  if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); return; }
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* ---------- 주석을 PNG에 담기 위한 준비 ---------- */
const NOTE_TITLE_H = 26;      // 주석 제목 줄 높이
const NOTE_LINE_H = 22;       // 본문 줄 높이
const NOTE_GAP = 22;          // 주석 사이 간격
const NOTE_IMG_MAX = 420;     // 사진 최대 폭

function loadImg(src) {
  return new Promise((res) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = () => res(null);
    i.src = src;
  });
}

/** 주석 HTML을 줄 단위 글로 바꾼다 (사진은 따로 뽑는다) */
function noteToLines(html) {
  const d = document.createElement('div');
  d.innerHTML = String(html || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<li[^>]*>/gi, '• ')
    .replace(/<\/(div|p|li|h[1-6])>/gi, '\n');
  d.querySelectorAll('img').forEach((im) => im.remove());
  return (d.textContent || '')
    .replace(/​/g, '')
    .split('\n')
    .map((s) => s.trim())
    .filter((s, i, a) => s !== '' || (i > 0 && a[i - 1] !== ''));
}

function noteImageSources(html) {
  const d = document.createElement('div');
  d.innerHTML = String(html || '');
  return Array.from(d.querySelectorAll('img')).map((im) => im.src);
}

/** 캔버스 폭에 맞춰 글을 접는다 */
function wrapForCanvas(ctx, text, maxW) {
  const out = [];
  let line = '';
  for (const ch of text) {
    const test = line + ch;
    if (line !== '' && ctx.measureText(test).width > maxW) {
      const sp = line.lastIndexOf(' ');
      if (sp > 0 && ctx.measureText(line.slice(sp + 1) + ch).width <= maxW) {
        out.push(line.slice(0, sp));
        line = line.slice(sp + 1) + ch;
      } else {
        out.push(line);
        line = ch;
      }
    } else line = test;
  }
  out.push(line);
  return out;
}

async function exportPng(noteIds) {
  measureAll();
  const b = bbox(48);
  const scale = 2;                                  // 고해상도

  const css = getComputedStyle(document.documentElement);
  const bg = css.getPropertyValue('--bg').trim() || '#14161c';
  const nodeBg = css.getPropertyValue('--node-bg').trim() || '#232733';
  const nodeBorder = css.getPropertyValue('--node-border').trim() || '#3a4152';
  const textCol = css.getPropertyValue('--text').trim() || '#e6e9f0';
  const dimCol = css.getPropertyValue('--text-dim').trim() || '#8b93a7';
  const edgeCol = css.getPropertyValue('--edge').trim() || '#4a5165';
  const lineCol = css.getPropertyValue('--border').trim() || '#2e3342';

  /* --- 담을 주석을 먼저 재어 전체 크기를 정한다 --- */
  const colW = Math.max(520, b.w - 96);
  const meas = document.createElement('canvas').getContext('2d');
  const blocks = [];
  let notesH = 0;

  if (noteIds && noteIds.size) {
    for (const n of visibleNodes()) {
      if (!noteIds.has(n.id) || !hasNote(n)) continue;
      const imgs = [];
      for (const src of noteImageSources(n.note)) {
        const im = await loadImg(src);
        if (im) imgs.push(im);
      }
      meas.font = '400 15px ' + FONT_STACK;
      const lines = [];
      for (const para of noteToLines(n.note)) {
        if (para === '') { lines.push(''); continue; }
        for (const l of wrapForCanvas(meas, para, colW)) lines.push(l);
      }
      let h = NOTE_TITLE_H + lines.length * NOTE_LINE_H;
      const drawn = imgs.map((im) => {
        const w = Math.min(NOTE_IMG_MAX, colW, im.naturalWidth);
        const ih = Math.round(im.naturalHeight * (w / im.naturalWidth));
        h += ih + 10;
        return { im, w, h: ih };
      });
      blocks.push({ node: n, lines, imgs: drawn, h });
      notesH += h + NOTE_GAP;
    }
    if (blocks.length) notesH += 42;               // 구분선과 제목 자리
  }

  const totalW = Math.max(b.w, blocks.length ? colW + 96 : 0);
  const totalH = b.h + notesH;

  const cv = document.createElement('canvas');
  cv.width = Math.ceil(totalW * scale);
  cv.height = Math.ceil(totalH * scale);
  const ctx = cv.getContext('2d');
  ctx.scale(scale, scale);

  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, totalW, totalH);

  ctx.save();
  ctx.translate(-b.x + (totalW - b.w) / 2, -b.y);

  const list = visibleNodes();

  // 연결선
  for (const p of list) {
    if (p.collapsed) continue;
    for (const cid of p.children) {
      const c = node(cid);
      if (!c) continue;
      const x1 = p.x + p.w, y1 = p.y + p.h / 2;
      const x2 = c.x, y2 = c.y + c.h / 2;
      const dx = Math.max(28, Math.abs(x2 - x1) / 2);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.bezierCurveTo(x1 + dx, y1, x2 - dx, y2, x2, y2);
      ctx.strokeStyle = c.color ? PALETTE[c.color - 1] : edgeCol;
      ctx.lineWidth = (p.id === doc.rootId) ? 2.4 : 1.8;
      ctx.lineCap = 'round';
      ctx.stroke();
    }
  }

  // 노드
  for (const n of list) {
    const m = metricsOf(n);
    const isRoot = n.id === doc.rootId;
    ctx.fillStyle = n.color ? PALETTE[n.color - 1] : nodeBg;
    roundRect(ctx, n.x, n.y, n.w, n.h, isRoot ? 12 : 10);
    ctx.fill();
    ctx.strokeStyle = n.color ? PALETTE[n.color - 1] : nodeBorder;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    ctx.fillStyle = n.color ? '#ffffff' : textCol;
    ctx.font = fontOf(n);
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    n.lines.forEach((line, i) => {
      ctx.fillText(line, n.x + m.padX, n.y + m.padY + m.lh * i + m.lh / 2);
    });
  }
  ctx.restore();

  /* --- 고른 주석을 마인드맵 아래에 붙인다 --- */
  if (blocks.length) {
    const left = (totalW - colW) / 2;
    let y = b.h + 6;

    ctx.strokeStyle = lineCol;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + colW, y);
    ctx.stroke();

    y += 26;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = dimCol;
    ctx.font = '600 13px ' + FONT_STACK;
    ctx.fillText('주석', left, y);
    y += 20;

    for (const blk of blocks) {
      // 제목 - 노드 색 점 + 노드 이름
      const dot = blk.node.color ? PALETTE[blk.node.color - 1] : edgeCol;
      ctx.fillStyle = dot;
      ctx.beginPath();
      ctx.arc(left + 5, y + 6, 5, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = textCol;
      ctx.font = '700 15px ' + FONT_STACK;
      ctx.fillText(blk.node.text, left + 18, y + 11);
      y += NOTE_TITLE_H;

      // 본문
      ctx.fillStyle = textCol;
      ctx.font = '400 15px ' + FONT_STACK;
      for (const line of blk.lines) {
        if (line !== '') ctx.fillText(line, left + 18, y + 15);
        y += NOTE_LINE_H;
      }

      // 사진
      for (const g of blk.imgs) {
        y += 10;
        ctx.drawImage(g.im, left + 18, y, g.w, g.h);
        ctx.strokeStyle = lineCol;
        ctx.lineWidth = 1;
        ctx.strokeRect(left + 18.5, y + 0.5, g.w - 1, g.h - 1);
        y += g.h;
      }

      y += NOTE_GAP;
    }
  }

  const suggested = sanitize(root().text) + '.png';
  try {
    if (bridge) {
      const r = await bridge.savePng(cv.toDataURL('image/png'), suggested);
      if (r && r.ok) toast('PNG로 내보냈습니다');
      return;
    }
    cv.toBlob((blob) => { downloadBlob(blob, suggested); toast('PNG를 다운로드했습니다'); });
  } catch (err) {
    toast('내보내기 실패: ' + err.message);
  }
}

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function sanitize(s) {
  const t = String(s || 'mindmap').trim().replace(/[\\/:*?"<>|\n]/g, '_').slice(0, 60);
  return t || 'mindmap';
}

/* =========================================================
   9. 툴바 / 기타 UI
   ========================================================= */
const palEl = $('#palette');
const noneBtn = document.createElement('button');
noneBtn.className = 'swatch none';
noneBtn.title = '색상 없음 (0)';
noneBtn.addEventListener('click', () => setColor(selected, 0));
palEl.appendChild(noneBtn);
PALETTE.forEach((c, i) => {
  const b = document.createElement('button');
  b.className = 'swatch';
  b.style.background = c;
  b.title = '색상 ' + (i + 1) + ' (' + (i + 1) + ')';
  b.addEventListener('click', () => setColor(selected, i + 1));
  palEl.appendChild(b);
});

document.querySelectorAll('button[data-act]').forEach((btn) => {
  btn.addEventListener('click', () => {
    switch (btn.dataset.act) {
      case 'new': newDoc(); break;
      case 'open': openFromFile(); break;
      case 'save': saveToFile(); break;
      case 'png': requestPng(); break;
      case 'child': addChild(selected); break;
      case 'sibling': addSibling(selected); break;
      case 'delete': removeNode(selected); break;
      case 'undo': undo(); break;
      case 'redo': redo(); break;
      case 'layout': pushHistory(); autoLayout(); render(); fitToScreen(); scheduleSave(); break;
      case 'fit': fitToScreen(); break;
      case 'theme': toggleTheme(); break;
      case 'csv-out': exportAllCsv(); break;
      case 'csv-in': importAllCsv(); break;
      case 'note-toggle': toggleNotePanel(); break;
    }
    btn.blur();
  });
});

function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* 무시 */ }
  drawEdges();
}

const helpPanel = $('#helpPanel');
$('#helpBtn').addEventListener('click', () => { helpPanel.hidden = !helpPanel.hidden; });
$('#helpClose').addEventListener('click', () => { helpPanel.hidden = true; });

let toastTimer = null;
function toast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 1800);
}

/* =========================================================
   9-2. 주석창 (노드별 메모)
   ========================================================= */
const noteEditor = $('#noteEditor');
const noteTitleEl = $('#noteTitle');
const noteSwatch = $('#noteSwatch');
const noteInfoEl = $('#noteInfo');
const noteToggleBtn = $('#noteToggle');
const imageInput = $('#imageInput');
const NOTE_KEY = 'flowmind:notePanel';

let noteNodeId = null;     // 편집기에 올라와 있는 노드
let noteSaveTimer = null;
let savedRange = null;     // 툴바를 누르면 선택이 풀리므로 따로 보관한다
let quotaWarned = false;

/** 선택된 노드에 맞춰 주석창을 갱신한다 */
function syncNotePanel() {
  if (!doc || !selected) return;
  const n = node(selected);
  if (!n) return;
  noteTitleEl.textContent = n.text;
  noteTitleEl.title = n.text;
  noteSwatch.style.background = n.color ? PALETTE[n.color - 1] : 'var(--text-dim)';
  if (noteNodeId !== n.id) {
    flushNote();                       // 이전 노드의 주석을 먼저 확정
    noteNodeId = n.id;
    noteEditor.innerHTML = n.note || '';
    savedRange = null;
    pickImage(null);                   // 사진 조절 도구도 닫는다
  }
  updateNoteInfo();
}

/** 편집기 내용을 노드에 반영 */
function flushNote() {
  if (!noteNodeId) return;
  const n = node(noteNodeId);
  if (!n) return;
  const html = noteEditor.innerHTML;
  if (html === n.note) return;
  n.note = html;
  updateNoteMark(n);
  scheduleSave();
}

/** 주석이 있는 노드에 점 표시를 붙이거나 뗀다 */
function updateNoteMark(n) {
  const el = elMap.get(n.id);
  if (!el) return;
  const mark = el.querySelector('.note-mark');
  if (hasNote(n) && !mark) {
    const dot = document.createElement('span');
    dot.className = 'note-mark';
    dot.title = '주석이 있습니다';
    el.appendChild(dot);
  } else if (!hasNote(n) && mark) {
    mark.remove();
  }
}

function updateNoteInfo() {
  const text = (noteEditor.innerText || '').replace(/​/g, '').trim();
  const imgs = noteEditor.querySelectorAll('img').length;
  noteInfoEl.textContent = text.length + '자' + (imgs ? ' · 사진 ' + imgs + '장' : '');
}

function toggleNotePanel(force) {
  const collapsed = (typeof force === 'boolean') ? force : !document.body.classList.contains('note-collapsed');
  document.body.classList.toggle('note-collapsed', collapsed);
  noteToggleBtn.textContent = collapsed ? '«' : '»';
  noteToggleBtn.title = (collapsed ? '주석창 펴기' : '주석창 접기') + ' (Ctrl+M)';
  try { localStorage.setItem(NOTE_KEY, collapsed ? 'collapsed' : 'open'); } catch (e) { /* 무시 */ }
}

noteEditor.addEventListener('input', () => {
  clearTimeout(noteSaveTimer);
  noteSaveTimer = setTimeout(flushNote, 350);
  updateNoteInfo();
});
noteEditor.addEventListener('blur', () => { clearTimeout(noteSaveTimer); flushNote(); });

/* ---------- 선택 영역 보관 / 복원 ---------- */
document.addEventListener('selectionchange', () => {
  const sel = window.getSelection();
  if (sel && sel.rangeCount && noteEditor.contains(sel.anchorNode)) {
    savedRange = sel.getRangeAt(0).cloneRange();
  }
});

function restoreSelection() {
  noteEditor.focus();
  if (!savedRange) return;
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(savedRange);
}

/** 조각 안의 모든 텍스트를 style이 걸린 span으로 감싼다 (줄 구조는 그대로 둔다) */
function styleTextNodes(frag, prop, value) {
  const walker = document.createTreeWalker(frag, NodeFilter.SHOW_TEXT);
  const texts = [];
  let t;
  while ((t = walker.nextNode())) if (t.nodeValue !== '') texts.push(t);
  for (const tn of texts) {
    const span = document.createElement('span');
    span.style[prop] = value;
    tn.replaceWith(span);
    span.appendChild(tn);
  }
}

/**
 * 선택 영역에 CSS 한 가지를 입힌다.
 * execCommand로 처리하면 크기를 준 뒤 두께를 주는 순간 크기가 지워지므로,
 * 선택 부분을 떼어내 텍스트마다 span을 씌우고 제자리에 되돌린다.
 */
function applyCss(prop, value) {
  restoreSelection();
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return;

  if (sel.isCollapsed) {
    // 선택이 없으면 지금 커서 위치부터 새로 입력되는 글자에 적용되게 한다
    const span = document.createElement('span');
    span.style[prop] = value;
    span.appendChild(document.createTextNode('​'));
    sel.getRangeAt(0).insertNode(span);
    const r = document.createRange();
    r.setStart(span.firstChild, 1);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    savedRange = r.cloneRange();
  } else {
    const range = sel.getRangeAt(0);
    const frag = range.extractContents();
    styleTextNodes(frag, prop, value);
    const inserted = Array.from(frag.childNodes);
    range.insertNode(frag);
    if (inserted.length) {
      const r = document.createRange();
      r.setStartBefore(inserted[0]);
      r.setEndAfter(inserted[inserted.length - 1]);
      sel.removeAllRanges();
      sel.addRange(r);
      savedRange = r.cloneRange();
    }
  }
  flushNote();
}

$('#fontFamily').addEventListener('change', (e) => applyCss('fontFamily', e.target.value));
$('#fontSize').addEventListener('change', (e) => applyCss('fontSize', e.target.value + 'px'));
$('#fontWeight').addEventListener('change', (e) => applyCss('fontWeight', e.target.value));
$('#fontColor').addEventListener('change', (e) => applyCss('color', e.target.value));

document.querySelectorAll('.note-bar button[data-cmd]').forEach((b) => {
  b.addEventListener('mousedown', (e) => e.preventDefault());   // 선택이 풀리지 않게
  b.addEventListener('click', () => {
    restoreSelection();
    document.execCommand(b.dataset.cmd, false, null);
    flushNote();
    updateNoteInfo();
  });
});

/* ---------- 사진 삽입 ---------- */
/** 긴 변을 maxSide로 줄이고 JPEG로 다시 인코딩해 파일 용량을 억제한다 */
async function downscaleImage(file, maxSide, quality) {
  const dataUrl = await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = () => rej(new Error('파일을 읽지 못했습니다'));
    fr.readAsDataURL(file);
  });
  const img = await new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => rej(new Error('이미지를 해석하지 못했습니다'));
    im.src = dataUrl;
  });
  if (img.width <= maxSide && img.height <= maxSide && dataUrl.length < 300000) return dataUrl;

  const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
  const cv = document.createElement('canvas');
  cv.width = Math.max(1, Math.round(img.width * scale));
  cv.height = Math.max(1, Math.round(img.height * scale));
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#ffffff';                       // 투명 배경은 흰색으로
  ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.drawImage(img, 0, 0, cv.width, cv.height);
  return cv.toDataURL('image/jpeg', quality);
}

async function insertImageFile(file) {
  if (!file || !/^image\//.test(file.type)) { toast('이미지 파일만 넣을 수 있습니다'); return; }
  try {
    const url = await downscaleImage(file, 900, 0.85);
    restoreSelection();
    document.execCommand('insertHTML', false, '<img src="' + url + '" alt="">');
    flushNote();
    updateNoteInfo();
    toast('사진을 넣었습니다');
  } catch (err) {
    toast('사진 삽입 실패: ' + err.message);
  }
}

$('#noteImage').addEventListener('click', () => { imageInput.value = ''; imageInput.click(); });
imageInput.addEventListener('change', () => {
  const f = imageInput.files && imageInput.files[0];
  if (f) insertImageFile(f);
});

noteEditor.addEventListener('paste', (e) => {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  for (const it of items) {
    if (it.type && it.type.indexOf('image/') === 0) {
      e.preventDefault();
      insertImageFile(it.getAsFile());
      return;
    }
  }
});
noteEditor.addEventListener('dragover', (e) => { e.preventDefault(); noteEditor.classList.add('dragover'); });
noteEditor.addEventListener('dragleave', () => noteEditor.classList.remove('dragover'));
noteEditor.addEventListener('drop', (e) => {
  noteEditor.classList.remove('dragover');
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (f && /^image\//.test(f.type)) { e.preventDefault(); insertImageFile(f); }
});

/* =========================================================
   9-2-b. 주석창 사진 조절 (크기 드래그 / 90° 회전)
   ========================================================= */
const notePanelEl = $('#notePanel');
const imgTools = $('#imgTools');
const imgHandle = $('#imgHandle');
let pickedImg = null;      // 지금 고른 사진
let imgDrag = null;        // 크기 조절 중인 상태

function pickImage(img) {
  // 선택 표시는 겹쳐 놓는 도구(.img-outline)가 대신하므로
  // 저장되는 본문(innerHTML)에는 아무 흔적도 남기지 않는다.
  pickedImg = img || null;
  if (!pickedImg) { imgTools.hidden = true; return; }
  placeImgTools();
}

/** 고른 사진 위에 조절 도구를 겹쳐 놓는다 */
function placeImgTools() {
  if (!pickedImg || !noteEditor.contains(pickedImg)) { pickImage(null); return; }
  const r = pickedImg.getBoundingClientRect();
  const p = notePanelEl.getBoundingClientRect();
  const ed = noteEditor.getBoundingClientRect();
  // 스크롤로 편집기 밖에 나가면 도구를 숨긴다
  if (r.bottom < ed.top + 6 || r.top > ed.bottom - 6) { imgTools.hidden = true; return; }
  imgTools.hidden = false;
  imgTools.style.left = (r.left - p.left) + 'px';
  imgTools.style.top = (r.top - p.top) + 'px';
  imgTools.style.width = r.width + 'px';
  imgTools.style.height = r.height + 'px';
}

noteEditor.addEventListener('click', (e) => {
  pickImage(e.target && e.target.tagName === 'IMG' ? e.target : null);
});
noteEditor.addEventListener('scroll', placeImgTools);
noteEditor.addEventListener('input', () => setTimeout(placeImgTools, 0));
window.addEventListener('resize', placeImgTools);

/** 사진 조작 직전에 되돌리기 지점을 만든다 */
function markImageUndo() {
  flushNote();                 // 지금까지 친 글을 먼저 확정하고
  const before = snapshot();   // 그 상태를 되돌리기 지점으로 삼는다
  return () => { undoStack.push(before); redoStack.length = 0; };
}

/* ---------- 끌어서 크기 조절 ---------- */
imgHandle.addEventListener('mousedown', (e) => {
  if (!pickedImg) return;
  e.preventDefault();
  e.stopPropagation();
  const commitUndo = markImageUndo();
  imgDrag = {
    sx: e.clientX,
    w: pickedImg.getBoundingClientRect().width,
    commitUndo: commitUndo
  };
});

window.addEventListener('mousemove', (e) => {
  if (!imgDrag || !pickedImg) return;
  const maxW = Math.max(60, noteEditor.clientWidth - 34);
  const w = Math.max(40, Math.min(maxW, imgDrag.w + (e.clientX - imgDrag.sx)));
  pickedImg.style.width = Math.round(w) + 'px';
  pickedImg.style.height = 'auto';
  placeImgTools();
});

window.addEventListener('mouseup', () => {
  if (!imgDrag) return;
  imgDrag.commitUndo();
  imgDrag = null;
  flushNote();
});

/* ---------- 90° 회전 ----------
   CSS transform으로 돌리면 글 사이에서 자리를 제대로 차지하지 못하므로,
   canvas로 픽셀 자체를 돌려 새 이미지로 갈아 끼운다. */
async function rotatePicked(dir) {
  if (!pickedImg) return;
  const img = pickedImg;
  const src = img.src;
  const m = /^data:(image\/[a-z]+)/i.exec(src);
  const type = m ? m[1].toLowerCase() : 'image/jpeg';
  const hadWidth = !!img.style.width;
  const shownHeight = img.getBoundingClientRect().height;

  try {
    const bitmap = await new Promise((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = () => rej(new Error('사진을 읽지 못했습니다'));
      i.src = src;
    });

    const cv = document.createElement('canvas');
    cv.width = bitmap.height;
    cv.height = bitmap.width;
    const ctx = cv.getContext('2d');
    ctx.translate(cv.width / 2, cv.height / 2);
    ctx.rotate(dir * Math.PI / 2);
    ctx.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2);

    const commitUndo = markImageUndo();
    const next = (type === 'image/png')
      ? cv.toDataURL('image/png')
      : cv.toDataURL('image/jpeg', 0.92);

    await new Promise((res) => {
      img.onload = () => res();
      img.onerror = () => res();
      img.src = next;
      setTimeout(res, 400);        // onload가 안 오는 경우 대비
    });
    img.onload = null;

    // 폭을 지정해 둔 사진은 돌려도 화면에서 차지하는 크기가 비슷하게 유지되도록
    if (hadWidth) {
      const maxW = Math.max(60, noteEditor.clientWidth - 34);
      img.style.width = Math.round(Math.max(40, Math.min(maxW, shownHeight))) + 'px';
    }
    img.style.height = 'auto';

    commitUndo();
    placeImgTools();
    flushNote();
    updateNoteInfo();
  } catch (err) {
    toast('회전 실패: ' + err.message);
  }
}

$('#imgRotL').addEventListener('click', () => rotatePicked(-1));
$('#imgRotR').addEventListener('click', () => rotatePicked(1));

$('#imgReset').addEventListener('click', () => {
  if (!pickedImg) return;
  const commitUndo = markImageUndo();
  pickedImg.style.width = '';
  pickedImg.style.height = '';
  commitUndo();
  setTimeout(placeImgTools, 0);
  flushNote();
});

$('#imgDel').addEventListener('click', () => {
  if (!pickedImg) return;
  const commitUndo = markImageUndo();
  pickedImg.remove();
  pickImage(null);
  commitUndo();
  flushNote();
  updateNoteInfo();
  toast('사진을 지웠습니다');
});

/* =========================================================
   9-3. CSV (엑셀) 내보내기 / 불러오기
   ========================================================= */
function csvEscape(v) {
  const s = String(v == null ? '' : v);
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

/** 엑셀이 한글을 깨뜨리지 않도록 UTF-8 BOM을 앞에 붙인다 */
function toCsv(rows) {
  return '﻿' + rows.map((r) => r.map(csvEscape).join(',')).join('\r\n');
}

function parseCsv(text) {
  const s = String(text).replace(/^﻿/, '');
  const rows = [];
  let row = [], cell = '', quoted = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quoted) {
      if (c === '"') {
        if (s[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
      } else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

/** 엑셀이 CP949로 저장한 CSV도 읽을 수 있게 인코딩을 판별한다 */
function decodeCsvBytes(bytes) {
  if (bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF) {
    return new TextDecoder('utf-8').decode(bytes.subarray(3));
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch (e) {
    return new TextDecoder('euc-kr').decode(bytes);
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function noteToText(html) {
  const d = document.createElement('div');
  d.innerHTML = html || '';
  d.querySelectorAll('img').forEach((im) => im.replaceWith(document.createTextNode('[사진]')));
  return (d.innerText || '').replace(/​/g, '').replace(/\r/g, '').trim();
}

function textToNote(text) {
  return String(text || '').split('\n').map((line) => {
    const safe = escapeHtml(line);
    return '<div>' + (safe === '' ? '<br>' : safe) + '</div>';
  }).join('');
}

async function saveTextFile(text, suggested, kind) {
  try {
    if (bridge && bridge.saveText) {
      const r = await bridge.saveText(text, suggested, kind);
      if (r && r.ok) toast('저장했습니다: ' + r.name);
      return;
    }
    if (window.showSaveFilePicker) {
      const handle = await window.showSaveFilePicker({
        suggestedName: suggested,
        types: [{ description: 'CSV (Excel)', accept: { 'text/csv': ['.csv'] } }]
      });
      const w = await handle.createWritable();
      await w.write(text);
      await w.close();
      toast('저장했습니다: ' + handle.name);
      return;
    }
    downloadBlob(new Blob([text], { type: 'text/csv;charset=utf-8' }), suggested);
    toast('다운로드 폴더에 저장했습니다');
  } catch (err) {
    if (err && err.name === 'AbortError') return;
    toast('저장 실패: ' + err.message);
  }
}

async function openTextFile(kind) {
  try {
    if (bridge && bridge.openText) {
      const r = await bridge.openText(kind);
      if (!r || !r.ok) return null;
      const bin = atob(r.base64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return { name: r.name, data: decodeCsvBytes(bytes) };
    }
    if (window.showOpenFilePicker) {
      const picked = await window.showOpenFilePicker({
        types: [{ description: 'CSV (Excel)', accept: { 'text/csv': ['.csv'] } }]
      });
      const f = await picked[0].getFile();
      return { name: f.name, data: decodeCsvBytes(new Uint8Array(await f.arrayBuffer())) };
    }
    return await new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.csv,text/csv';
      input.onchange = async () => {
        const f = input.files && input.files[0];
        resolve(f ? { name: f.name, data: decodeCsvBytes(new Uint8Array(await f.arrayBuffer())) } : null);
      };
      input.click();
    });
  } catch (err) {
    if (err && err.name === 'AbortError') return null;
    toast('열기 실패: ' + err.message);
    return null;
  }
}

/* ---------- 전체 노드 + 주석 (앱 상단바) ---------- */
async function exportAllCsv() {
  flushNote();
  const rows = [['ID', '상위 ID', '노드', '주석']];
  (function walk(id) {
    const n = node(id);
    if (!n) return;
    rows.push([n.id, n.parent || '', n.text, noteToText(n.note)]);
    n.children.forEach(walk);
  })(doc.rootId);
  await saveTextFile(toCsv(rows), sanitize(root().text) + '.csv', 'csv');
}

async function importAllCsv() {
  const res = await openTextFile('csv');
  if (!res) return;
  const rows = parseCsv(res.data);
  if (rows.length < 2) { toast('내용이 없는 CSV입니다'); return; }

  const head = rows[0].map((h) => h.trim());
  const iId = head.findIndex((h) => /^id$/i.test(h));
  const iText = head.findIndex((h) => /노드|이름|title|name/i.test(h));
  const iNote = head.findIndex((h) => /주석|메모|note|comment/i.test(h));
  if (iId < 0 && iText < 0) { toast('머리글에서 ID 또는 노드 열을 찾지 못했습니다'); return; }
  if (!confirm('CSV 내용으로 노드 이름과 주석을 덮어씁니다.\n주석 안의 사진과 서식은 사라집니다. 계속할까요?')) return;

  pushHistory();
  let applied = 0, missed = 0;
  for (let r = 1; r < rows.length; r++) {
    const row = rows[r];
    if (!row.length || row.every((c) => c.trim() === '')) continue;
    let n = (iId >= 0) ? doc.nodes[(row[iId] || '').trim()] : null;
    if (!n && iText >= 0) {
      const t = (row[iText] || '').trim();
      n = Object.values(doc.nodes).find((x) => x.text === t);
    }
    if (!n) { missed++; continue; }
    if (iText >= 0 && (row[iText] || '').trim()) n.text = row[iText].trim();
    if (iNote >= 0) n.note = textToNote(row[iNote] || '');
    applied++;
  }
  noteNodeId = null;              // 편집기를 새 내용으로 강제 갱신
  render();
  scheduleSave();
  toast(applied + '개 노드에 적용했습니다' + (missed ? ' (' + missed + '개는 찾지 못함)' : ''));
}

/* ---------- 현재 노드의 주석만 (주석창 상단바) ---------- */
async function exportNoteCsv() {
  flushNote();
  const n = node(selected);
  if (!n) return;
  const rows = [['ID', '노드', '주석'], [n.id, n.text, noteToText(n.note)]];
  await saveTextFile(toCsv(rows), sanitize(n.text) + '-주석.csv', 'csv');
}

async function importNoteCsv() {
  const n = node(selected);
  if (!n) return;
  const res = await openTextFile('csv');
  if (!res) return;
  const rows = parseCsv(res.data);
  if (rows.length < 2) { toast('내용이 없는 CSV입니다'); return; }

  const head = rows[0].map((h) => h.trim());
  let iNote = head.findIndex((h) => /주석|메모|note|comment/i.test(h));
  if (iNote < 0) iNote = rows[0].length - 1;      // 머리글이 없으면 마지막 열로 간주

  const texts = [];
  for (let r = 1; r < rows.length; r++) {
    const v = rows[r][iNote];
    if (v != null && v.trim() !== '') texts.push(v);
  }
  if (!texts.length) { toast('불러올 주석 내용이 없습니다'); return; }
  if (!confirm('"' + n.text + '" 노드의 주석을 CSV 내용으로 바꿉니다.\n사진과 서식은 사라집니다. 계속할까요?')) return;

  pushHistory();
  n.note = textToNote(texts.join('\n'));
  noteNodeId = null;
  render();
  scheduleSave();
  toast('주석을 불러왔습니다');
}

$('#noteCsvOut').addEventListener('click', exportNoteCsv);
$('#noteCsvIn').addEventListener('click', importNoteCsv);

/* =========================================================
   10. 시작
   ========================================================= */
(function init() {
  try {
    const t = localStorage.getItem(THEME_KEY);
    if (t) document.documentElement.dataset.theme = t;
  } catch (e) { /* 무시 */ }

  let panelCollapsed = false;
  try { panelCollapsed = localStorage.getItem(NOTE_KEY) === 'collapsed'; } catch (e) { /* 무시 */ }
  toggleNotePanel(panelCollapsed);

  let restored = false;
  try {
    const saved = localStorage.getItem(AUTOSAVE_KEY);
    if (saved) { deserialize(saved); restored = true; }
  } catch (e) { console.warn('자동 저장 복구 실패', e); }

  if (!restored) {
    doc = blankDoc();
    selected = doc.rootId;
    autoLayout();
  }

  fileNameEl.textContent = fileName;
  render();

  let viewRestored = false;
  try {
    const v = JSON.parse(localStorage.getItem(VIEW_KEY) || 'null');
    if (v && typeof v.s === 'number' && isFinite(v.s)) {
      view.tx = v.tx; view.ty = v.ty; view.s = v.s;
      applyView();
      viewRestored = true;
    }
  } catch (e) { /* 무시 */ }
  if (!viewRestored) fitToScreen();

  if (restored) saveStateEl.textContent = '· 이어서 편집 중';
})();

window.addEventListener('resize', applyView);

/* =========================================================
   11. 사용 허가 (무료 체험 / 정품 인증)
   ========================================================= */
const gateEl = $('#gate');
const gateSerialEl = $('#gateSerial');
const gateMsgEl = $('#gateMsg');
const gateTitleEl = $('#gateTitle');
const gateDescEl = $('#gateDesc');
const gateCloseBtn = $('#gateClose');
const gateQuitBtn = $('#gateQuit');
const gateSaveBtn = $('#gateSave');
const licBadgeEl = $('#licBadge');

let licBlocked = false;    // true면 창이 덮여 있어 마인드맵을 만질 수 없다

async function showGate(blocking) {
  licBlocked = !!blocking;
  LICENSE.machineCode().then((c) => { $('#gateMachine').textContent = c; });
  gateCloseBtn.hidden = !!blocking;
  gateQuitBtn.hidden = !blocking;
  gateSaveBtn.hidden = !blocking;
  gateMsgEl.textContent = '';
  gateMsgEl.className = 'gate-msg';
  gateEl.hidden = false;
  setTimeout(() => gateSerialEl.focus(), 30);
}

function hideGate() {
  gateEl.hidden = true;
  licBlocked = false;
}

function updateLicBadge(st) {
  if (st.activated) {
    licBadgeEl.textContent = '정품 ' + LICENSE.mask(st.serial);
    licBadgeEl.className = 'paid';
    licBadgeEl.title = '정품 인증됨 - 기간 제한 없음';
  } else if (st.expired) {
    licBadgeEl.textContent = '체험 종료';
    licBadgeEl.className = 'warn';
    licBadgeEl.title = '정품 인증이 필요합니다';
  } else {
    licBadgeEl.textContent = '체험 ' + LICENSE.formatLeft(st.msLeft) + ' 남음';
    licBadgeEl.className = (st.msLeft < 3600000) ? 'warn' : '';
    licBadgeEl.title = '무료 체험 중 - 눌러서 정품 인증';
  }
}

async function checkLicense() {
  let st;
  try {
    st = await LICENSE.status();
  } catch (e) {
    console.warn('사용 허가 확인 실패', e);
    return null;
  }
  updateLicBadge(st);

  if (!st.activated && st.expired) {
    if (st.wrongMachine) {
      gateTitleEl.textContent = '다른 PC에서 인증된 정보입니다';
      gateDescEl.innerHTML = '이 인증 정보는 기기 코드 <b>' + LICENSE.group(st.boundTo || '') + '</b> 인 PC에<br>' +
        '묶여 있어 이 PC에서는 쓸 수 없습니다.<br>이 PC의 기기 코드로 새로 발급받은 인증키를 입력해 주세요.';
    } else {
      gateTitleEl.textContent = st.tampered ? '사용 기간을 확인할 수 없습니다' : '무료 체험 기간이 끝났습니다';
      gateDescEl.innerHTML = st.tampered
        ? '시스템 시계가 과거로 바뀐 것이 확인되었습니다.<br>아래 기기 코드를 구입처에 알려주고 받은 인증키(16자)를 입력하세요.'
        : 'FlowMind 무료 버전은 처음 실행한 때부터 24시간 동안 쓸 수 있습니다.<br>아래 기기 코드를 구입처에 알려주고 받은 인증키(16자)를 입력하세요.';
    }
    if (gateEl.hidden || !licBlocked) showGate(true);
  } else if (licBlocked) {
    hideGate();
  }
  return st;
}

async function doActivate() {
  const r = await LICENSE.activate(gateSerialEl.value);
  if (!r.ok) {
    gateMsgEl.textContent = r.reason;
    gateMsgEl.className = 'gate-msg';
    return;
  }
  gateMsgEl.textContent = '정품 인증이 완료되었습니다.';
  gateMsgEl.className = 'gate-msg ok';
  setTimeout(async () => {
    hideGate();
    await checkLicense();
    toast('정품 인증되었습니다. 기간 제한 없이 사용하실 수 있습니다.');
  }, 800);
}

gateSerialEl.addEventListener('input', () => {
  gateSerialEl.value = LICENSE.group(LICENSE.normalize(gateSerialEl.value).slice(0, 16));
  gateMsgEl.textContent = '';
  gateMsgEl.className = 'gate-msg';
});
gateSerialEl.addEventListener('keydown', (e) => {
  e.stopPropagation();
  if (e.key === 'Enter') { e.preventDefault(); doActivate(); }
});

$('#gateActivate').addEventListener('click', doActivate);
$('#gateCopy').addEventListener('click', async () => {
  const code = await LICENSE.machineCode();
  try {
    await navigator.clipboard.writeText(code);
    toast('기기 코드를 복사했습니다: ' + code);
  } catch (e) {
    toast('복사하지 못했습니다. 코드를 직접 적어 주세요: ' + code);
  }
});
gateCloseBtn.addEventListener('click', hideGate);
gateQuitBtn.addEventListener('click', () => window.close());
gateSaveBtn.addEventListener('click', () => saveToFile());

licBadgeEl.addEventListener('click', async () => {
  const st = await LICENSE.status();
  if (st.activated) {
    gateTitleEl.textContent = '정품 인증됨';
    gateDescEl.innerHTML = '인증키 <b>' + LICENSE.mask(st.serial) + '</b><br>기간 제한 없이 사용하실 수 있습니다.';
    gateSerialEl.value = '';
    showGate(false);
  } else if (st.expired) {
    await checkLicense();
  } else {
    gateTitleEl.textContent = '정품 인증';
    gateDescEl.innerHTML = '무료 체험이 <b>' + LICENSE.formatLeft(st.msLeft) + '</b> 남았습니다.<br>인증키(16자)를 넣으면 기간 제한이 사라집니다.';
    showGate(false);
  }
});

checkLicense();
setInterval(checkLicense, 30000);    // 사용 중에 기간이 끝나도 바로 막는다

/* =========================================================
   12. Ctrl 을 길게 누르면 단축키 안내 띄우기
   ========================================================= */
const cheatEl = $('#cheat');
const CHEAT_DELAY = 1000;          // 1초 이상 누르고 있어야 뜬다
let cheatTimer = null;

function hideCheat() {
  clearTimeout(cheatTimer);
  cheatTimer = null;
  cheatEl.classList.remove('show');
}

window.addEventListener('keydown', (e) => {
  if (e.key !== 'Control' || e.repeat) return;   // 자동 반복은 무시
  if (editing || licBlocked) return;             // 이름 편집 중이거나 잠겨 있으면 띄우지 않는다
  if (cheatTimer || cheatEl.classList.contains('show')) return;
  cheatTimer = setTimeout(() => cheatEl.classList.add('show'), CHEAT_DELAY);
});

window.addEventListener('keyup', (e) => {
  if (e.key === 'Control') hideCheat();
});

// 창이 포커스를 잃거나(대화상자 등) 다른 곳을 누르면 확실히 닫는다
window.addEventListener('blur', hideCheat);
window.addEventListener('mousedown', hideCheat);

/* =========================================================
   13. PNG 내보내기 - 담을 주석 고르기
   ========================================================= */
const pngDlg = $('#pngDlg');
const pngList = $('#pngList');
const pngCountEl = $('#pngCount');
let pngOpen = false;          // 창이 떠 있는 동안에는 마인드맵 단축키를 막는다

/** 주석이 들어 있는 노드들 (화면에 보이는 순서대로) */
function notedNodes() {
  return visibleNodes().filter(hasNote);
}

function pngUpdateCount() {
  const boxes = pngList.querySelectorAll('input[type="checkbox"]');
  const on = pngList.querySelectorAll('input[type="checkbox"]:checked').length;
  pngCountEl.textContent = on + ' / ' + boxes.length + ' 선택';
}

/** PNG 버튼과 Ctrl+E 가 부르는 진입점 */
function requestPng() {
  flushNote();
  const targets = notedNodes();
  if (!targets.length) { exportPng(null); return; }   // 주석이 없으면 바로 내보낸다

  pngList.textContent = '';
  for (const n of targets) {
    const row = document.createElement('label');
    row.className = 'png-item';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.dataset.id = n.id;
    cb.addEventListener('change', pngUpdateCount);

    const dot = document.createElement('span');
    dot.className = 'dot';
    dot.style.background = n.color ? PALETTE[n.color - 1] : 'var(--text-dim)';

    const txt = document.createElement('span');
    txt.className = 'txt';
    const nm = document.createElement('span');
    nm.className = 'nm';
    nm.textContent = n.text;
    const pv = document.createElement('span');
    pv.className = 'pv';
    const plain = noteToLines(n.note).join(' ');
    const shots = noteImageSources(n.note).length;
    pv.textContent = plain.slice(0, 60) + (plain.length > 60 ? '…' : '');
    if (shots) {
      const badge = document.createElement('b');
      badge.textContent = (plain ? '  ' : '') + '사진 ' + shots + '장';
      pv.appendChild(badge);
    }
    txt.append(nm, pv);
    row.append(cb, dot, txt);
    pngList.appendChild(row);
  }

  pngUpdateCount();
  pngOpen = true;
  pngDlg.hidden = false;
  setTimeout(() => $('#pngOk').focus(), 30);
}

function closePngDlg() {
  pngDlg.hidden = true;
  pngOpen = false;
}

$('#pngAll').addEventListener('click', () => {
  pngList.querySelectorAll('input[type="checkbox"]').forEach((c) => { c.checked = true; });
  pngUpdateCount();
});
$('#pngNone').addEventListener('click', () => {
  pngList.querySelectorAll('input[type="checkbox"]').forEach((c) => { c.checked = false; });
  pngUpdateCount();
});
$('#pngCancel').addEventListener('click', closePngDlg);
$('#pngOk').addEventListener('click', () => {
  const ids = new Set();
  pngList.querySelectorAll('input[type="checkbox"]:checked').forEach((c) => ids.add(c.dataset.id));
  closePngDlg();
  exportPng(ids);
});

// 창이 떠 있을 때 Esc 는 취소, Enter 는 확인
window.addEventListener('keydown', (e) => {
  if (!pngOpen) return;
  if (e.key === 'Escape') { e.preventDefault(); closePngDlg(); }
  else if (e.key === 'Enter') {
    const a = document.activeElement;
    if (a && a.tagName === 'BUTTON') return;   // 버튼에 초점이 있으면 버튼이 알아서 처리
    e.preventDefault();
    $('#pngOk').click();
  }
}, true);
