// 离屏冒烟用的最小 Figma API 替身（配合 smoke.js，不需要打开 Figma）。
//
// 只实现骨架用到的那部分 API，**不模拟布局引擎**：尺寸只在 resize() / 显式赋值时变化，auto-layout 不会
// 重算几何。所以它能抓的是拼装层面的错误——未定义引用、调用顺序、页面预算、导出设置、深色改绑，
// 以及"漏 add() 导致节点游离"。它**不能**替代在 Figma 里实跑：摆位、换行、轴 sizing、字体渲染都不在这里。

let idSeq = 0;
const nextId = () => `node:${(idSeq += 1)}`;

class Node {
  constructor(type) {
    this.id = nextId();
    this.type = type;
    this.name = '';
    this.children = [];
    this.parent = null;
    this.x = 0;
    this.y = 0;
    this.width = 100;
    this.height = 100;
    this.fills = [];
    this.strokes = [];
    this.strokeWeight = 1;
    this.strokeCap = 'NONE';
    this.layoutMode = 'NONE';
    this.layoutWrap = 'NO_WRAP';
    this.layoutAlign = 'INHERIT';
    this.layoutGrow = 0;
    this.layoutPositioning = 'AUTO';
    this.itemSpacing = 0;
    this.paddingLeft = 0;
    this.paddingRight = 0;
    this.paddingTop = 0;
    this.paddingBottom = 0;
    this.primaryAxisSizingMode = 'AUTO';
    this.counterAxisSizingMode = 'AUTO';
    this.primaryAxisAlignItems = 'MIN';
    this.counterAxisAlignItems = 'MIN';
    this.cornerRadius = 0;
    this.clipsContent = false;
    this.exportSettings = [];
    this.reactions = [];
    this.annotations = [];
  }

  get removed() {
    return this.parent === null && this.type !== 'PAGE';
  }

  get absoluteBoundingBox() {
    return { x: this.x, y: this.y, width: this.width, height: this.height };
  }

  resize(w, h) {
    if (typeof w === 'number') this.width = w;
    if (typeof h === 'number') this.height = h;
  }

  appendChild(node) {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1);
    node.parent = this;
    this.children.push(node);
    return node;
  }

  remove() {
    if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }

  clone() {
    const copy = new Node(this.type);
    copy.name = this.name;
    copy.x = this.x;
    copy.y = this.y;
    copy.width = this.width;
    copy.height = this.height;
    copy.fills = this.fills.map((p) => ({ ...p, boundVariables: p.boundVariables ? { ...p.boundVariables } : undefined }));
    copy.strokes = this.strokes.map((p) => ({ ...p, boundVariables: p.boundVariables ? { ...p.boundVariables } : undefined }));
    copy.strokeWeight = this.strokeWeight;
    copy.layoutMode = this.layoutMode;
    copy.itemSpacing = this.itemSpacing;
    copy.exportSettings = [];
    for (const child of this.children) copy.appendChild(child.clone());
    return copy;
  }
}

class TextNode extends Node {
  constructor() {
    super('TEXT');
    this.characters = '';
    this.textStyleId = '';
    this.fontRanges = [];
  }

  setRangeFontName(start, end, font) {
    if (start < 0 || end > this.characters.length || start >= end) {
      throw new Error(`bad range ${start}-${end} of ${this.characters.length}`);
    }
    this.fontRanges.push({ start, end, font });
  }
}

class Variable {
  constructor(name, collection) {
    this.id = `var:${(idSeq += 1)}`;
    this.name = name;
    this.variableCollectionId = collection.id;
    this.valuesByMode = {};
  }

  setValueForMode(modeId, value) {
    this.valuesByMode[modeId] = value;
  }
}

class VariableCollection {
  constructor(name) {
    this.id = `coll:${(idSeq += 1)}`;
    this.name = name;
    this.modes = [{ modeId: 'mode:1', name: 'Mode 1' }];
    this.variableIds = [];
  }

  // 真运行时里这个属性是 undefined（2026-09-16 在 Figma 桌面版实测）：集合内变量只能靠
  // variableIds + figma.variables.getLocalVariablesAsync() 取，getVariablesAsync 也不存在。
  // 替身必须照真机返回 undefined，否则"读了 coll.variables"这类 bug 在冒烟里看不见。
  get variables() {
    return undefined;
  }
}

function createFigmaStub() {
  const pages = [];
  const collections = [];
  const variables = [];
  const textStyles = [];
  const log = { notify: [], closed: null, console: [] };

  const root = new Node('DOCUMENT');
  root.type = 'DOCUMENT';

  const createPage = () => {
    const page = new Node('PAGE');
    page.type = 'PAGE';
    page.parent = root;
    pages.push(page);
    root.children.push(page);
    return page;
  };

  const page1 = createPage();
  page1.name = 'Page 1'; // 新文件自带的空页，用来验证"收养空页"这条路径

  const figma = {
    root,
    currentPage: page1,
    createFrame: () => new Node('FRAME'),
    createComponent: () => new Node('COMPONENT'),
    createRectangle: () => new Node('RECTANGLE'),
    createEllipse: () => new Node('ELLIPSE'),
    createVector: () => new Node('VECTOR'),
    createText: () => new TextNode(),
    createPage,
    async setCurrentPageAsync(page) {
      figma.currentPage = page;
    },
    combineAsVariants(nodes, parent) {
      const set = new Node('COMPONENT_SET');
      set.layoutMode = 'NONE';
      parent.appendChild(set);
      for (const n of nodes) set.appendChild(n);
      return set;
    },
    variables: {
      getLocalVariableCollections: () => collections,
      createVariableCollection(name) {
        const coll = new VariableCollection(name);
        collections.push(coll);
        return coll;
      },
      createVariable(name, collection) {
        const v = new Variable(name, collection);
        variables.push(v);
        collection.variableIds.push(v.id);
        return v;
      },
      async getLocalVariablesAsync() {
        return variables.slice();
      },
      getVariableById(id) {
        return variables.find((v) => v.id === id) || null;
      },
      // 真 API 返回带绑定信息的新 paint；这里照做，深色改绑才会可验证。
      setBoundVariableForPaint(paint, field, variable) {
        return { ...paint, boundVariables: { ...(paint.boundVariables || {}), [field]: variable } };
      },
    },
    getLocalTextStyles: () => textStyles,
    createTextStyle() {
      const style = { id: `style:${(idSeq += 1)}`, name: '' };
      textStyles.push(style);
      return style;
    },
    async loadFontAsync() {},
    async listAvailableFontsAsync() {
      return [
        { fontName: { family: 'Inter', style: 'Regular' } },
        { fontName: { family: 'PingFang SC', style: 'Regular' } },
        { fontName: { family: 'PingFang SC', style: 'Medium' } },
      ];
    },
    notify(message) {
      log.notify.push(message);
    },
    closePlugin(message) {
      log.closed = message;
    },
  };

  return { figma, log, collections, variables, textStyles, pages };
}

module.exports = { createFigmaStub, Node };
