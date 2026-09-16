// 《诡秘世界》（World of Mysteries）设计稿生成器插件 v1.1
// 运行环境：Figma 桌面版 → Plugins → Development → World of Mysteries Design Kit
// 架构遵循：figma-to-macos 技能规范与离线门禁

const SCREEN_EXPORT_SCALE = 4;
const VARIABLE_COLLECTION = 'Design Tokens';
const DARK_VARIABLE_COLLECTION = 'Design Tokens Dark';

const PAGE_BUDGET = 3;
const BOARD_GAP = 400;
const PAGE_LAYOUT = [
  { name: '01 Design Tokens', groups: ['foundations'] },
  { name: '02 Components', groups: ['components'] },
];
const PAGES = PAGE_LAYOUT.map((p) => p.name);

const COLORS = {
  obsidianBase: { r: 0.051, g: 0.059, b: 0.071 },
  obsidianElevated: { r: 0.078, g: 0.094, b: 0.114 },
  obsidianCard: { r: 0.106, g: 0.125, b: 0.149 },
  abyssVoid: { r: 0.031, g: 0.035, b: 0.043 },
  brassGoldPrimary: { r: 0.773, g: 0.627, b: 0.349 },
  brassGoldHover: { r: 0.831, g: 0.698, b: 0.435 },
  brassGoldMuted: { r: 0.549, g: 0.451, b: 0.243 },
  brassGoldBorder: { r: 0.290, g: 0.243, b: 0.145 },
  spiritualBlue: { r: 0.290, g: 0.565, b: 0.886 },
  spiritualGlow: { r: 0.392, g: 0.710, b: 0.965 },
  crimsonStar: { r: 0.902, g: 0.224, b: 0.275 },
  crimsonThread: { r: 0.718, g: 0.110, b: 0.110 },
  parchmentBase: { r: 0.918, g: 0.859, b: 0.714 },
  parchmentBorder: { r: 0.784, g: 0.698, b: 0.510 },
  parchmentInk: { r: 0.169, g: 0.129, b: 0.094 },
  textPrimary: { r: 0.953, g: 0.957, b: 0.965 },
  textSecondary: { r: 0.612, g: 0.639, b: 0.686 },
  textTertiary: { r: 0.420, g: 0.447, b: 0.502 },
  textGoldAccent: { r: 0.886, g: 0.769, b: 0.522 },
  statusOnline: { r: 0.180, g: 0.769, b: 0.714 },
  statusWarning: { r: 1.000, g: 0.624, b: 0.110 },
  statusDanger: { r: 0.906, g: 0.114, b: 0.212 },
  statusImmutable: { r: 0.282, g: 0.584, b: 0.937 },
  pathwayFool: { r: 0.482, g: 0.173, b: 0.749 },
  pathwayDoor: { r: 0.000, g: 0.467, b: 0.714 },
  pathwayError: { r: 0.831, g: 0.639, b: 0.451 },
  pathwayDarkness: { r: 0.227, g: 0.047, b: 0.639 },
  pathwaySun: { r: 0.984, g: 0.522, b: 0.000 },
  pathwayVisionary: { r: 0.914, g: 0.847, b: 0.651 },
};

const DARK_COLORS = {
  obsidianBase: { r: 0.035, g: 0.040, b: 0.050 },
  obsidianElevated: { r: 0.060, g: 0.075, b: 0.090 },
  obsidianCard: { r: 0.085, g: 0.100, b: 0.125 },
  abyssVoid: { r: 0.020, g: 0.025, b: 0.030 },
  brassGoldPrimary: { r: 0.773, g: 0.627, b: 0.349 },
  brassGoldHover: { r: 0.831, g: 0.698, b: 0.435 },
  brassGoldMuted: { r: 0.549, g: 0.451, b: 0.243 },
  brassGoldBorder: { r: 0.290, g: 0.243, b: 0.145 },
  spiritualBlue: { r: 0.290, g: 0.565, b: 0.886 },
  spiritualGlow: { r: 0.392, g: 0.710, b: 0.965 },
  crimsonStar: { r: 0.902, g: 0.224, b: 0.275 },
  crimsonThread: { r: 0.718, g: 0.110, b: 0.110 },
  parchmentBase: { r: 0.850, g: 0.790, b: 0.650 },
  parchmentBorder: { r: 0.700, g: 0.620, b: 0.450 },
  parchmentInk: { r: 0.169, g: 0.129, b: 0.094 },
  textPrimary: { r: 0.953, g: 0.957, b: 0.965 },
  textSecondary: { r: 0.612, g: 0.639, b: 0.686 },
  textTertiary: { r: 0.420, g: 0.447, b: 0.502 },
  textGoldAccent: { r: 0.886, g: 0.769, b: 0.522 },
  statusOnline: { r: 0.180, g: 0.769, b: 0.714 },
  statusWarning: { r: 1.000, g: 0.624, b: 0.110 },
  statusDanger: { r: 0.906, g: 0.114, b: 0.212 },
  statusImmutable: { r: 0.282, g: 0.584, b: 0.937 },
  pathwayFool: { r: 0.482, g: 0.173, b: 0.749 },
  pathwayDoor: { r: 0.000, g: 0.467, b: 0.714 },
  pathwayError: { r: 0.831, g: 0.639, b: 0.451 },
  pathwayDarkness: { r: 0.227, g: 0.047, b: 0.639 },
  pathwaySun: { r: 0.984, g: 0.522, b: 0.000 },
  pathwayVisionary: { r: 0.914, g: 0.847, b: 0.651 },
};

const RADII = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
};

const TEXT_STYLES = {
  'Title/Display': { family: 'Inter', style: 'Semi Bold', size: 28, lineHeight: 34 },
  'Title/Medium': { family: 'Inter', style: 'Semi Bold', size: 18, lineHeight: 24 },
  'Title/Small': { family: 'Inter', style: 'Semi Bold', size: 15, lineHeight: 20 },
  'Body/Large': { family: 'Inter', style: 'Regular', size: 14, lineHeight: 22 },
  'Body/Medium': { family: 'Inter', style: 'Regular', size: 13, lineHeight: 18 },
  'Label/Caption': { family: 'Inter', style: 'Medium', size: 11, lineHeight: 14 },
  'Label/MonoBadge': { family: 'Inter', style: 'Medium', size: 11, lineHeight: 14 },
  'Parchment/Cursive': { family: 'Inter', style: 'Regular', size: 13, lineHeight: 19 },
  'Narrative/Subtitle': { family: 'Inter', style: 'Medium', size: 16, lineHeight: 26 },
};

const PLACEHOLDER_GRAY = { r: 0.5, g: 0.5, b: 0.5 };
const CJK_FAMILIES = ['PingFang SC', 'Hiragino Sans GB', 'Noto Sans SC', 'Source Han Sans SC'];
const CJK_STYLE_ORDER = ['Regular', 'W3', 'Medium', 'W6', 'Semibold', 'Bold'];
let CJK_FONT = null;

// ---------- 运行期状态 ----------

const varIndex = {};
const darkVarIndex = {};
const varNameById = {};
const styleIndex = {};
const iconIndex = {};
const boardCursor = {};
const builtBoards = [];
const setCursor = {};
const EXPORT_ERRORS = [];
const BIND_ERRORS = [];
const LINKS = { ok: 0, failed: 0 };
const PENDING_LAYOUT = new WeakMap();

const SET_W = 740;
const SET_GAP = 24;
const SET_ROW_GAP = 48;
const DARK_SUFFIX = ' · Dark';
const SET_TOP = 140;

// ---------- 取值 ----------

function color(name) {
  const c = COLORS[name];
  if (!c) throw new Error(`unknown color: ${name}`);
  return { type: 'SOLID', color: { r: c.r, g: c.g, b: c.b } };
}

function textStyle(name) {
  const id = styleIndex[name];
  if (!id) throw new Error(`unknown text style: ${name}`);
  return id;
}

function variablePaint(name) {
  const v = varIndex[name];
  if (!v) throw new Error(`unbound variable: ${name}`);
  try {
    return figma.variables.setBoundVariableForPaint(color(name), 'color', v);
  } catch (err) {
    BIND_ERRORS.push(`${name}: ${err && err.message ? err.message : String(err)}`);
    return color(name);
  }
}

// ---------- 构造 ----------

function applyAxisSizing(node, w, h) {
  const vertical = node.layoutMode === 'VERTICAL';
  node[vertical ? 'primaryAxisSizingMode' : 'counterAxisSizingMode'] = h == null ? 'AUTO' : 'FIXED';
  node[vertical ? 'counterAxisSizingMode' : 'primaryAxisSizingMode'] = w == null ? 'AUTO' : 'FIXED';
}

function frame(name, opts = {}) {
  const f = figma.createFrame();
  f.name = name;
  f.layoutMode = opts.absolute ? 'NONE' : opts.direction === 'row' ? 'HORIZONTAL' : 'VERTICAL';
  f.clipsContent = opts.clip === true;
  if (f.layoutMode !== 'NONE') {
    f.itemSpacing = opts.gap == null ? 12 : opts.gap;
    const pad = opts.pad == null ? 0 : opts.pad;
    f.paddingLeft = f.paddingRight = opts.padX == null ? pad : opts.padX;
    f.paddingTop = f.paddingBottom = opts.padY == null ? pad : opts.padY;
    f.primaryAxisAlignItems = opts.justify || 'MIN';
    f.counterAxisAlignItems = opts.align || 'MIN';
    if (opts.wrap) f.layoutWrap = 'WRAP';
    applyAxisSizing(f, opts.w, opts.h);
    if (opts.w != null || opts.h != null) {
      f.resize(opts.w == null ? f.width : opts.w, opts.h == null ? f.height : opts.h);
    }
  }
  f.cornerRadius = opts.radius == null ? RADII.md : opts.radius;
  f.fills = opts.fill ? [variablePaint(opts.fill)] : [];
  return f;
}

function intent(node, patch) {
  const pending = PENDING_LAYOUT.get(node) || {};
  Object.assign(pending, patch);
  PENDING_LAYOUT.set(node, pending);
  return node;
}

function stretch(node) {
  return intent(node, { layoutAlign: 'STRETCH' });
}

function grow(node, value) {
  return intent(node, { layoutGrow: value == null ? 1 : value });
}

function applyLayout(node) {
  const patch = PENDING_LAYOUT.get(node);
  if (!patch) return;
  if (patch.layoutAlign) node.layoutAlign = patch.layoutAlign;
  if (patch.layoutGrow != null) node.layoutGrow = patch.layoutGrow;
  PENDING_LAYOUT.delete(node);
}

function add(parent, child) {
  parent.appendChild(child);
  applyLayout(child);
  return child;
}

function spacer(parent) {
  const s = frame('spacer', { w: 1, h: 1 });
  s.fills = [];
  add(parent, grow(s));
  return s;
}

function size(node, w, h) {
  node.resize(w, h);
  return node;
}

function isCjk(code) {
  return (
    (code >= 0x4e00 && code <= 0x9fff) ||
    (code >= 0x3400 && code <= 0x4dbf) ||
    (code >= 0x3000 && code <= 0x303f) ||
    (code >= 0xff00 && code <= 0xffef)
  );
}

async function pickCjkFont() {
  for (const family of CJK_FAMILIES) {
    for (const style of CJK_STYLE_ORDER) {
      try {
        await figma.loadFontAsync({ family, style });
        return { family, style };
      } catch (err) {}
    }
  }
  return null;
}

function text(content, styleName, colorName) {
  const t = figma.createText();
  t.textStyleId = textStyle(styleName);
  t.characters = content;
  if (CJK_FONT) {
    let runStart = -1;
    for (let i = 0; i < content.length; i += 1) {
      const cjk = isCjk(content.charCodeAt(i));
      if (cjk && runStart === -1) runStart = i;
      else if (!cjk && runStart !== -1) {
        t.setRangeFontName(runStart, i, CJK_FONT);
        runStart = -1;
      }
    }
    if (runStart !== -1) t.setRangeFontName(runStart, content.length, CJK_FONT);
  }
  t.fills = [variablePaint(colorName == null ? 'textPrimary' : colorName)];
  return t;
}

function collectIcons() {
  for (const name of Object.keys(ICONS)) iconIndex[name] = ICONS[name];
}

function drawIcon(name, tint) {
  const shapes = iconIndex[name];
  if (!shapes) throw new Error(`unknown icon: ${name}`);
  const box = frame(`Icon/${name}`, { absolute: true, radius: 0 });
  box.fills = [];
  for (const s of shapes) {
    let node;
    if (s.type === 'ellipse') node = figma.createEllipse();
    else if (s.type === 'rect') node = figma.createRectangle();
    else node = figma.createVector();
    if (s.type === 'path') {
      node.vectorPaths = [{ windingRule: 'NONZERO', data: s.d }];
      node.strokeCap = 'ROUND';
    }
    if (s.type === 'ellipse') {
      node.x = s.cx - s.rx;
      node.y = s.cy - s.ry;
      node.resize(s.rx * 2, s.ry * 2);
    } else if (s.type === 'rect') {
      node.x = s.x;
      node.y = s.y;
      node.resize(s.w, s.h);
      node.cornerRadius = s.r || 0;
    }
    node.fills = [];
    node.strokes = [variablePaint(tint)];
    node.strokeWeight = 1.5;
    add(box, node);
  }
  box.resize(24, 24);
  return box;
}

// ---------- 页面 ----------

async function goto(page) {
  if (typeof figma.setCurrentPageAsync === 'function') await figma.setCurrentPageAsync(page);
  else figma.currentPage = page;
}

function pageByName(name) {
  const p = figma.root.children.find((x) => x.name === name);
  if (!p) throw new Error(`missing page: ${name}`);
  return p;
}

async function ensurePages() {
  if (PAGES.length > PAGE_BUDGET) {
    throw new Error(`页预算超了：声明 ${PAGES.length} 页，免费版每文件上限 ${PAGE_BUDGET}`);
  }
  const owned = [];
  for (const name of PAGES) {
    let page = figma.root.children.find((p) => p.name === name && owned.indexOf(p) === -1);
    if (!page) {
      const spare = figma.root.children.find(
        (p) => owned.indexOf(p) === -1 && PAGES.indexOf(p.name) === -1 && p.children.length === 0,
      );
      if (spare) {
        page = spare;
      } else if (figma.root.children.length >= PAGE_BUDGET) {
        throw new Error(
          `没有可用页位：文件已有 ${figma.root.children.length} 页（上限 ${PAGE_BUDGET}）。` +
            '腾一张空页或删掉不再需要的页再重跑；生成器不会替你动有内容的页。',
        );
      } else {
        page = figma.createPage();
      }
    }
    page.name = name;
    owned.push(page);
  }
  for (const page of owned) {
    await goto(page);
    for (const child of [...page.children]) child.remove();
  }
}

// ---------- 变量与样式 ----------

async function ensureVariables() {
  await ensureCollection(VARIABLE_COLLECTION, COLORS, varIndex);
  await ensureCollection(DARK_VARIABLE_COLLECTION, DARK_COLORS, darkVarIndex);
}

async function ensureCollection(collectionName, table, index) {
  let coll = figma.variables.getLocalVariableCollections().find((c) => c.name === collectionName);
  if (!coll) coll = figma.variables.createVariableCollection(collectionName);
  const modeId = coll.modes[0].modeId;

  const existing = new Map();
  for (const v of await figma.variables.getLocalVariablesAsync()) {
    if (v.variableCollectionId === coll.id) existing.set(v.name, v);
  }

  for (const [name, value] of Object.entries(table)) {
    let v = existing.get(name);
    if (!v) {
      v = figma.variables.createVariable(name, coll, 'COLOR');
      existing.set(name, v);
    }
    v.setValueForMode(modeId, value);
    index[name] = v;
    varNameById[v.id] = name;
  }
}

async function ensureTextStyles() {
  for (const [name, spec] of Object.entries(TEXT_STYLES)) {
    await figma.loadFontAsync({ family: spec.family, style: spec.style });
    const found = figma.getLocalTextStyles().find((s) => s.name === name);
    const style = found || figma.createTextStyle();
    style.name = name;
    style.fontName = { family: spec.family, style: spec.style };
    style.fontSize = spec.size;
    style.lineHeight = { unit: 'PIXELS', value: spec.lineHeight };
    styleIndex[name] = style.id;
  }
}

// ---------- 画板与组件集 ----------

function setBoardExportSettings(node) {
  try {
    node.exportSettings = [
      { format: 'PNG', constraint: { type: 'SCALE', value: SCREEN_EXPORT_SCALE } },
      { format: 'SVG', svgOutlineText: false },
    ];
  } catch (err) {
    EXPORT_ERRORS.push(`${node.name}: ${err && err.message ? err.message : String(err)}`);
  }
}

function placeBoard(group, name, board) {
  const spec = PAGE_LAYOUT.find((p) => p.groups.indexOf(group) !== -1);
  if (!spec) throw new Error(`unknown board group: ${group}`);
  const page = pageByName(spec.name);
  page.appendChild(board);
  board.name = name;
  board.x = boardCursor[page.id] == null ? 0 : boardCursor[page.id];
  board.y = 0;
  setBoardExportSettings(board);
  boardCursor[page.id] = board.x + board.width + BOARD_GAP;
  builtBoards.push({ group, name, board });
  return board;
}

function walk(node, visit) {
  visit(node);
  if ('children' in node) for (const c of node.children) walk(c, visit);
}

function darkClone(board, name) {
  const clone = board.clone();
  clone.name = name;
  walk(clone, (node) => {
    for (const field of ['fills', 'strokes']) {
      const paints = node[field];
      if (!Array.isArray(paints) || paints.length === 0) continue;
      try {
        node[field] = paints.map((paint) => {
          const bound = paint.boundVariables && paint.boundVariables.color;
          const target = bound ? darkVarIndex[varNameById[bound.id]] : null;
          return target ? figma.variables.setBoundVariableForPaint(paint, 'color', target) : paint;
        });
      } catch (err) {
        BIND_ERRORS.push(`${name} · ${node.name}.${field}: ${err && err.message ? err.message : String(err)}`);
      }
    }
  });
  return clone;
}

function buildDark() {
  for (const entry of [...builtBoards]) {
    placeBoard(entry.group, `${entry.name}${DARK_SUFFIX}`, darkClone(entry.board, `${entry.name}${DARK_SUFFIX}`));
  }
}

function fitBoard(board, width, contentBottom) {
  size(board, width, board.paddingTop + contentBottom + board.paddingBottom);
  return board;
}

function comp(name, opts = {}) {
  const c = figma.createComponent();
  c.name = name;
  c.fills = [];
  c.clipsContent = false;
  c.layoutMode = opts.absolute ? 'NONE' : opts.direction === 'row' ? 'HORIZONTAL' : 'VERTICAL';
  if (c.layoutMode !== 'NONE') {
    c.itemSpacing = opts.gap == null ? 0 : opts.gap;
    const pad = opts.pad == null ? 0 : opts.pad;
    c.paddingLeft = c.paddingRight = opts.padX == null ? pad : opts.padX;
    c.paddingTop = c.paddingBottom = opts.padY == null ? pad : opts.padY;
    c.primaryAxisAlignItems = opts.justify || 'MIN';
    c.counterAxisAlignItems = opts.align || 'MIN';
    if (opts.wrap) c.layoutWrap = 'WRAP';
    applyAxisSizing(c, opts.w, opts.h);
    if (opts.w != null || opts.h != null) {
      c.resize(opts.w == null ? c.width : opts.w, opts.h == null ? c.height : opts.h);
    }
  }
  c.cornerRadius = opts.radius == null ? RADII.md : opts.radius;
  if (opts.fill) c.fills = [variablePaint(opts.fill)];
  return c;
}

function componentSet(board, setName, defs, x, y) {
  const nodes = defs.map((d) => {
    const c = comp(`${setName}/${d.prop}`, d.opts || {});
    d.build(c);
    return c;
  });
  const set = figma.combineAsVariants(nodes, board);
  set.name = setName;
  if (set.layoutMode !== 'NONE') {
    try {
      set.layoutMode = 'NONE';
    } catch (err) {}
  }
  if (set.layoutMode === 'NONE') {
    let cx = 0;
    let cy = 0;
    let rowH = 0;
    let rowW = 0;
    let maxW = 0;
    nodes.forEach((n) => {
      if (cx > 0 && cx + n.width > SET_W) {
        cy += rowH + SET_GAP;
        cx = 0;
        rowH = 0;
        rowW = 0;
      }
      n.x = cx;
      n.y = cy;
      cx += n.width + SET_GAP;
      rowW = cx - SET_GAP;
      rowH = Math.max(rowH, n.height);
      maxW = Math.max(maxW, rowW);
    });
    set.resize(Math.max(maxW, 1), Math.max(cy + rowH, 1));
  } else {
    set.itemSpacing = SET_GAP;
    set.counterAxisSpacing = SET_GAP;
    set.layoutWrap = 'WRAP';
    set.counterAxisSizingMode = 'AUTO';
    set.primaryAxisSizingMode = 'FIXED';
    set.resize(SET_W, set.height);
  }
  const top = Math.max(y, setCursor[x] == null ? 0 : setCursor[x]);
  set.layoutPositioning = 'ABSOLUTE';
  set.x = x;
  set.y = top;
  const box = set.absoluteBoundingBox;
  const origin = board.absoluteBoundingBox;
  if (box && origin) {
    const offX = Math.round(box.x - origin.x - x);
    const offY = Math.round(box.y - origin.y - top);
    if (offX === board.paddingLeft && offY === board.paddingTop) {
      set.x = x - offX;
      set.y = top - offY;
    }
  }
  setCursor[x] = top + set.height + SET_ROW_GAP;
  return set;
}

// ---------- 01 Design Tokens (Foundations) ----------

function buildFoundations() {
  const board = frame('Design Tokens', { gap: 28, padX: 48, padY: 48, fill: 'obsidianBase', w: 1280 });
  add(board, text('World of Mysteries · Design Tokens v1.1', 'Title/Display', 'textGoldAccent'));
  add(board, text('维多利亚蒸汽暗金 × 克苏鲁超凡神秘主义跨端单一事实源（色彩、途径专属色、排版、网格与同心圆角）。', 'Body/Large', 'textSecondary'));

  // 色彩调色板
  add(board, text('Color Palette (语义色与途径专属色)', 'Title/Medium', 'textPrimary'));
  const swatches = frame('swatches', { direction: 'row', gap: 14, wrap: true, w: 1184 });
  for (const name of Object.keys(COLORS)) {
    const cell = frame(`Swatch/${name}`, { gap: 8, padX: 12, padY: 12, radius: RADII.sm, fill: 'obsidianCard', w: 180 });
    const chip = add(cell, frame(`Chip/${name}`, { radius: RADII.xs, fill: name }));
    size(chip, 156, 44);
    add(cell, text(name, 'Label/MonoBadge', 'textPrimary'));
    add(swatches, cell);
  }
  add(board, swatches);

  // 排版阶梯
  add(board, text('Typography Scale (排版层级阶梯)', 'Title/Medium', 'textPrimary'));
  const typoBox = frame('typoBox', { gap: 12, padX: 20, padY: 20, radius: RADII.md, fill: 'obsidianElevated', w: 1184 });
  add(typoBox, text('Title/Display · 28pt Bold · 页面核心大标题', 'Title/Display', 'textGoldAccent'));
  add(typoBox, text('Title/Medium · 18pt SemiBold · 模块标题与卷宗大类', 'Title/Medium', 'textPrimary'));
  add(typoBox, text('Title/Small · 15pt SemiBold · 卡片标题与关键实体', 'Title/Small', 'brassGoldPrimary'));
  add(typoBox, text('Narrative/Subtitle · 16pt Medium · 沉浸剧情与旁白字幕', 'Narrative/Subtitle', 'textGoldAccent'));
  add(typoBox, text('Body/Large · 14pt Regular · 沉浸剧情对白与世界脉搏正文', 'Body/Large', 'textSecondary'));
  add(typoBox, text('Body/Medium · 13pt Regular · 标准卷宗内容与线索描述', 'Body/Medium', 'textSecondary'));
  add(typoBox, text('Label/Caption · 11pt Medium · 状态说明与操作提示', 'Label/Caption', 'textTertiary'));
  add(typoBox, text('Parchment/Cursive · 13pt Serif · 复古羊皮纸与手写钢笔日记', 'Parchment/Cursive', 'parchmentInk'));
  add(board, typoBox);

  // 同心圆角几何体系
  add(board, text('Concentric Radii (同心圆角几何体系)', 'Title/Medium', 'textPrimary'));
  const radiiRow = frame('radiiRow', { direction: 'row', gap: 20, align: 'CENTER' });
  for (const [name, value] of Object.entries(RADII)) {
    const cell = frame(`Radius/${name}`, { gap: 8, align: 'CENTER' });
    add(cell, frame(`Radius/${name}/box`, { radius: value, fill: 'obsidianCard', w: 100, h: 64 }));
    add(cell, text(`${name} · ${value}px`, 'Label/MonoBadge', 'textSecondary'));
    add(radiiRow, cell);
  }
  add(board, radiiRow);

  placeBoard('foundations', 'Design Tokens', board);
}

// ---------- 02 Components (组件设计稿) ----------

const RING_DEFS = [
  {
    prop: 'State=Idle',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 16, padY: 10, radius: RADII.sm, fill: 'obsidianCard' },
    build: (c) => {
      add(c, drawIcon('mic', 'brassGoldPrimary'));
      add(c, text('待命 · 世界正在聆听', 'Label/Caption', 'brassGoldPrimary'));
    },
  },
  {
    prop: 'State=Listening',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 16, padY: 10, radius: RADII.sm, fill: 'obsidianCard' },
    build: (c) => {
      add(c, drawIcon('sparkle', 'spiritualBlue'));
      add(c, text('聆听 · 正在倾听 Advice...', 'Label/Caption', 'spiritualBlue'));
    },
  },
  {
    prop: 'State=Deciding',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 16, padY: 10, radius: RADII.sm, fill: 'obsidianCard' },
    build: (c) => {
      add(c, drawIcon('clock', 'brassGoldHover'));
      add(c, text('权衡 · 人物正在权衡动机...', 'Label/Caption', 'brassGoldHover'));
    },
  },
  {
    prop: 'State=Speaking',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 16, padY: 10, radius: RADII.sm, fill: 'obsidianCard' },
    build: (c) => {
      add(c, drawIcon('dot', 'textGoldAccent'));
      add(c, text('回应 · 克莱恩正在表达...', 'Label/Caption', 'textGoldAccent'));
    },
  },
];

const SIDEBAR_DEFS = [
  {
    prop: 'Selection=Default',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 14, padY: 8, radius: RADII.sm, fill: 'obsidianElevated', w: 220 },
    build: (c) => {
      add(c, drawIcon('book', 'textSecondary'));
      add(c, text('故事书 (Story Book)', 'Body/Medium', 'textSecondary'));
    },
  },
  {
    prop: 'Selection=Selected',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 14, padY: 8, radius: RADII.sm, fill: 'obsidianCard', w: 220 },
    build: (c) => {
      add(c, drawIcon('sparkle', 'brassGoldPrimary'));
      add(c, text('命运干预 (Fate)', 'Body/Medium', 'textGoldAccent'));
      spacer(c);
      add(c, drawIcon('dot', 'brassGoldPrimary'));
    },
  },
];

const CARD_DEFS = [
  {
    prop: 'Style=ObsidianGlass',
    opts: { gap: 10, padX: 18, padY: 18, radius: RADII.lg, fill: 'obsidianCard', w: 340 },
    build: (c) => {
      add(c, text('局势卷宗 (Current Situation)', 'Title/Small', 'brassGoldPrimary'));
      add(c, text('韦尔奇卧室内的枪声打破了红月的静谧，安提哥努斯家族笔记已被神秘人带走。', 'Body/Medium', 'textSecondary'));
    },
  },
  {
    prop: 'Style=Parchment',
    opts: { gap: 10, padX: 18, padY: 18, radius: RADII.md, fill: 'parchmentBase', w: 340 },
    build: (c) => {
      add(c, text('侦探线索笔记 · #1349', 'Title/Small', 'parchmentInk'));
      add(c, text('“所有人都会死，包括我。”——遗留信件', 'Parchment/Cursive', 'parchmentInk'));
    },
  },
  {
    prop: 'Style=BrassFramed',
    opts: { gap: 10, padX: 18, padY: 18, radius: RADII.lg, fill: 'obsidianElevated', w: 340 },
    build: (c) => {
      add(c, text('序列 9：占卜家 (Seer)', 'Title/Small', 'textGoldAccent'));
      add(c, text('魔药消化度: 68% · 灵视完全就绪', 'Body/Medium', 'statusOnline'));
    },
  },
];

const GAUGE_DEFS = [
  {
    prop: 'Level=Abundant',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 14, padY: 10, radius: RADII.sm, fill: 'obsidianCard' },
    build: (c) => {
      add(c, drawIcon('eye', 'spiritualBlue'));
      add(c, text('灵性充盈 · 85%', 'Label/MonoBadge', 'spiritualBlue'));
    },
  },
  {
    prop: 'Level=Moderate',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 14, padY: 10, radius: RADII.sm, fill: 'obsidianCard' },
    build: (c) => {
      add(c, drawIcon('eye', 'statusWarning'));
      add(c, text('灵性适中 · 55%', 'Label/MonoBadge', 'statusWarning'));
    },
  },
  {
    prop: 'Level=Critical',
    opts: { direction: 'row', gap: 12, align: 'CENTER', padX: 14, padY: 10, radius: RADII.sm, fill: 'obsidianCard' },
    build: (c) => {
      add(c, drawIcon('eye', 'statusDanger'));
      add(c, text('失控警告 · 15%', 'Label/MonoBadge', 'statusDanger'));
    },
  },
];

const DB_DEFS = [
  {
    prop: 'Type=Canon',
    opts: { gap: 8, padX: 16, padY: 14, radius: RADII.md, fill: 'obsidianCard', w: 320 },
    build: (c) => {
      const h = frame('h', { direction: 'row', gap: 8, align: 'CENTER' });
      add(c, stretch(h));
      add(h, drawIcon('dot', 'statusImmutable'));
      add(h, text('canon.db', 'Title/Small', 'statusImmutable'));
      spacer(h);
      add(h, text('38.2 MB', 'Label/MonoBadge', 'textTertiary'));
      add(c, text('正典历史底座 · 强只读锁定', 'Label/Caption', 'textSecondary'));
    },
  },
  {
    prop: 'Type=Retrieval',
    opts: { gap: 8, padX: 16, padY: 14, radius: RADII.md, fill: 'obsidianCard', w: 320 },
    build: (c) => {
      const h = frame('h', { direction: 'row', gap: 8, align: 'CENTER' });
      add(c, stretch(h));
      add(h, drawIcon('dot', 'statusOnline'));
      add(h, text('retrieval.db', 'Title/Small', 'textGoldAccent'));
      spacer(h);
      add(h, drawIcon('reload', 'brassGoldHover'));
      add(c, text('异步投影 · 100% 幂等可重建', 'Label/Caption', 'textSecondary'));
    },
  },
];

const ADVICE_DEFS = [
  {
    prop: 'State=Empty',
    opts: { gap: 6, padX: 16, padY: 12, radius: RADII.sm, fill: 'obsidianCard', w: 420 },
    build: (c) => {
      add(c, text('Advice to 克莱恩 · 决策权归人物所有', 'Label/Caption', 'textSecondary'));
      const input = frame('input', { direction: 'row', gap: 8, align: 'CENTER' });
      add(c, stretch(input));
      add(input, text('轻声提供你的建议...', 'Body/Medium', 'textTertiary'));
      spacer(input);
      add(input, drawIcon('mic', 'brassGoldPrimary'));
    },
  },
  {
    prop: 'State=Drafting',
    opts: { gap: 6, padX: 16, padY: 12, radius: RADII.sm, fill: 'obsidianCard', w: 420 },
    build: (c) => {
      add(c, text('Advice to 克莱恩 · 决策权归人物所有', 'Label/Caption', 'brassGoldPrimary'));
      const input = frame('input', { direction: 'row', gap: 8, align: 'CENTER' });
      add(c, stretch(input));
      add(input, text('“不要回头看镜子，立刻离开房间。”', 'Body/Medium', 'textPrimary'));
      spacer(input);
      add(input, drawIcon('check', 'brassGoldPrimary'));
    },
  },
];

const TAROT_DEFS = [
  {
    prop: 'Discovery=Identified',
    opts: { gap: 8, padX: 14, padY: 14, radius: RADII.md, fill: 'obsidianCard', w: 200, h: 280 },
    build: (c) => {
      const topRow = frame('topRow', { direction: 'row', gap: 4, align: 'CENTER' });
      add(c, stretch(topRow));
      add(topRow, text('Seq.9', 'Label/MonoBadge', 'textGoldAccent'));
      spacer(topRow);
      add(topRow, text('占卜家', 'Label/Caption', 'pathwayFool'));
      spacer(c);
      const iconWrap = frame('iconWrap', { direction: 'row', align: 'CENTER', justify: 'CENTER' });
      add(c, stretch(iconWrap));
      add(iconWrap, drawIcon('sparkle', 'pathwayFool'));
      spacer(c);
      add(c, text('正典已揭示', 'Label/Caption', 'statusOnline'));
    },
  },
  {
    prop: 'Discovery=Unknown',
    opts: { gap: 8, padX: 14, padY: 14, radius: RADII.md, fill: 'obsidianCard', w: 200, h: 280 },
    build: (c) => {
      const topRow = frame('topRow', { direction: 'row', gap: 4, align: 'CENTER' });
      add(c, stretch(topRow));
      add(topRow, text('Seq.？', 'Label/MonoBadge', 'textTertiary'));
      spacer(c);
      const iconWrap = frame('iconWrap', { direction: 'row', align: 'CENTER', justify: 'CENTER' });
      add(c, stretch(iconWrap));
      add(iconWrap, drawIcon('dot', 'textTertiary'));
      spacer(c);
      add(c, text('未知迷雾', 'Label/Caption', 'textTertiary'));
    },
  },
];

const NARRATIVE_DEFS = [
  {
    prop: 'Speaker=Character',
    opts: { gap: 8, padX: 18, padY: 16, radius: RADII.md, fill: 'obsidianCard', w: 420 },
    build: (c) => {
      const h = frame('h', { direction: 'row', gap: 8, align: 'CENTER' });
      add(c, stretch(h));
      add(h, drawIcon('quote', 'brassGoldPrimary'));
      add(h, text('克莱恩·莫雷蒂', 'Label/Caption', 'brassGoldPrimary'));
      spacer(h);
      add(h, text('1349-06-28', 'Label/MonoBadge', 'textTertiary'));
      add(c, text('“这不是梦境...那颗子弹确实穿过了我的太阳穴。”', 'Narrative/Subtitle', 'textPrimary'));
    },
  },
];

const CLUE_DEFS = [
  {
    prop: 'Type=ParchmentNote',
    opts: { gap: 6, padX: 14, padY: 12, radius: RADII.xs, fill: 'parchmentBase', w: 240 },
    build: (c) => {
      const h = frame('h', { direction: 'row', gap: 6, align: 'CENTER' });
      add(c, stretch(h));
      add(h, drawIcon('pin', 'crimsonThread'));
      add(h, text('自杀手枪弹壳', 'Title/Small', 'parchmentInk'));
      add(c, text('书桌右侧发现一枚缺少弹头的黄铜弹壳。', 'Parchment/Cursive', 'parchmentInk'));
    },
  },
];

function buildComponents() {
  const board = frame('Core Components', { gap: 28, padX: 48, padY: 48, fill: 'obsidianBase', w: 1640 });
  add(board, text('World of Mysteries · Core Components Kit v1.1', 'Title/Display', 'textGoldAccent'));
  add(board, text('全量绑定 15 种交互状态与 9 大核心组件变体矩阵（包含卡牌、编年史对白与线索节点）。', 'Body/Large', 'textSecondary'));

  componentSet(board, 'Listening Ring', RING_DEFS, 0, SET_TOP);
  componentSet(board, 'Sidebar Row', SIDEBAR_DEFS, 780, SET_TOP);
  
  const y2 = Math.max(setCursor[0] || SET_TOP, setCursor[780] || SET_TOP);
  componentSet(board, 'Victorian Card', CARD_DEFS, 0, y2);
  componentSet(board, 'Spirituality Gauge', GAUGE_DEFS, 780, y2);
  
  const y3 = Math.max(setCursor[0] || y2, setCursor[780] || y2);
  componentSet(board, 'Database HUD Card', DB_DEFS, 0, y3);
  componentSet(board, 'Advice Input', ADVICE_DEFS, 780, y3);

  const y4 = Math.max(setCursor[0] || y3, setCursor[780] || y3);
  componentSet(board, 'Tarot Card', TAROT_DEFS, 0, y4);
  componentSet(board, 'Narrative Chronicle', NARRATIVE_DEFS, 780, y4);

  const y5 = Math.max(setCursor[0] || y4, setCursor[780] || y4);
  componentSet(board, 'Clue Pinboard Node', CLUE_DEFS, 0, y5);

  fitBoard(board, 1640, Math.max(setCursor[0] || 0, setCursor[780] || 0));
  placeBoard('components', 'Core Components', board);
}

function isPlaceholder(node) {
  if (!Array.isArray(node.fills)) return false;
  return node.fills.some(
    (f) =>
      f.type === 'SOLID' &&
      Math.abs(f.color.r - PLACEHOLDER_GRAY.r) < 0.001 &&
      Math.abs(f.color.g - PLACEHOLDER_GRAY.g) < 0.001 &&
      Math.abs(f.color.b - PLACEHOLDER_GRAY.b) < 0.001,
  );
}

function overflowOf(node) {
  if (!('children' in node)) return 0;
  let max = 0;
  for (const c of node.children) {
    max = Math.max(max, c.x + c.width - node.width, c.y + c.height - node.height);
  }
  return max;
}

function auditReport() {
  const tally = { boards: 0, dark: 0, rootOverflow: 0, innerOverflow: 0, placeholders: 0, stray: 0 };
  for (const p of figma.root.children.filter((x) => PAGES.includes(x.name))) {
    for (const child of p.children) {
      if (child.type !== 'FRAME') {
        tally.stray += 1;
        continue;
      }
      tally.boards += 1;
      if (child.name.endsWith(DARK_SUFFIX)) tally.dark += 1;
      if (overflowOf(child) > 0.5) tally.rootOverflow += 1;
      walk(child, (n) => {
        if ('children' in n && n !== child && overflowOf(n) > 0.5) tally.innerOverflow += 1;
        if (isPlaceholder(n)) tally.placeholders += 1;
      });
    }
  }
  const clean =
    tally.rootOverflow === 0 &&
    tally.innerOverflow === 0 &&
    tally.placeholders === 0 &&
    tally.stray === 0 &&
    BIND_ERRORS.length === 0 &&
    EXPORT_ERRORS.length === 0 &&
    LINKS.failed === 0;
  const foreign = figma.root.children.filter((x) => !PAGES.includes(x.name)).map((x) => x.name);
  return [
    `AUDIT VERDICT: ${clean ? 'PASS' : 'FAIL'}`,
    `boards=${tally.boards}`,
    `dark boards=${tally.dark}`,
    `bind errors=${BIND_ERRORS.length}`,
    `prototype links=${LINKS.ok} (failed ${LINKS.failed})`,
    `root overflow=${tally.rootOverflow}`,
    `inner overflow=${tally.innerOverflow}`,
    `placeholder fill=${tally.placeholders}`,
    `stray top-level=${tally.stray}`,
    `export errors=${EXPORT_ERRORS.length}`,
    `cjk runs=${CJK_FONT ? CJK_FONT.family : 'none'}`,
    `foreign pages kept=${foreign.length ? foreign.join(', ') : 'none'}`,
  ].join('\n');
}

// ---------- 主入口 ----------

async function main() {
  CJK_FONT = await pickCjkFont();
  collectIcons();
  await ensurePages();
  await ensureVariables();
  await ensureTextStyles();

  buildFoundations();
  buildComponents();
  buildDark();

  await goto(pageByName(PAGES[0]));
  const report = auditReport();
  console.log(report);
  if (BIND_ERRORS.length) console.log(`bind detail:\n${BIND_ERRORS.slice(0, 10).join('\n')}`);
  if (EXPORT_ERRORS.length) console.log(`export detail:\n${EXPORT_ERRORS.slice(0, 10).join('\n')}`);
  try {
    figma.notify(report, { timeout: 60000 });
  } catch (err) {}
  return report;
}

main()
  .then((report) => {
    figma.closePlugin(report);
  })
  .catch((err) => {
    figma.closePlugin(`BUILD FAILED: ${err && err.message ? err.message : err}`);
  });
