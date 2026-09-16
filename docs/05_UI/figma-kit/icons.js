// 图标几何：从图标源固化后写进仓库，不在插件运行时下载。
// 约定：每个条目是 24×24 viewBox 下的形状数组；只放真正用得到的图标。
// 约定：形状只画描边（drawIcon 恒把 fills 清空、用 tint 写 strokes）。

const ICONS = {
  dot: [{ type: 'ellipse', cx: 12, cy: 12, rx: 4, ry: 4 }],
  check: [{ type: 'path', d: 'M5 12.5 L10 17.5 L19 7.5' }],
  mic: [
    { type: 'rect', x: 9, y: 4, w: 6, h: 10, r: 3 },
    { type: 'path', d: 'M5 10 A7 7 0 0 0 19 10' },
    { type: 'path', d: 'M12 17 L12 21' },
    { type: 'path', d: 'M8 21 L16 21' }
  ],
  eye: [
    { type: 'path', d: 'M2 12 C5 6 19 6 22 12 C19 18 5 18 2 12 Z' },
    { type: 'ellipse', cx: 12, cy: 12, rx: 3, ry: 3 }
  ],
  sparkle: [
    { type: 'path', d: 'M12 2 L13.5 9 L20.5 10.5 L13.5 12 L12 19 L10.5 12 L3.5 10.5 L10.5 9 Z' }
  ],
  book: [
    { type: 'path', d: 'M4 19.5 A2.5 2.5 0 0 1 6.5 17 H20' },
    { type: 'path', d: 'M6.5 2 H20 V22 H6.5 A2.5 2.5 0 0 1 4 19.5 V4.5 A2.5 2.5 0 0 1 6.5 2 Z' }
  ],
  reload: [
    { type: 'path', d: 'M21 12 A9 9 0 1 1 18.3 5.7 L21 3 V9 H15' }
  ],
  clock: [
    { type: 'ellipse', cx: 12, cy: 12, rx: 9, ry: 9 },
    { type: 'path', d: 'M12 7 L12 12 L15 15' }
  ],
  quote: [
    { type: 'path', d: 'M3 21 C3 14 7 10 11 10 L11 4 C5 4 1 9 1 17 Z' },
    { type: 'path', d: 'M15 21 C15 14 19 10 23 10 L23 4 C17 4 13 9 13 17 Z' }
  ],
  pin: [
    { type: 'ellipse', cx: 12, cy: 7, rx: 4, ry: 4 },
    { type: 'path', d: 'M12 11 L12 21' }
  ]
};
