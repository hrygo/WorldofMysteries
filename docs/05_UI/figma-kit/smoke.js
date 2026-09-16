#!/usr/bin/env node
// 离屏冒烟：在替身 API 上把生成器完整跑一遍，检查拼装层面的不变量（不需要打开 Figma）。
//
// 用法： node smoke.js
// 退出码非 0 = 有结构性问题。抓的是：跑不起来、页面超预算、画板不是页面顶层 FRAME、导出设置缺失、
// 深色克隆数量对不上或没改绑、游离节点、绑定/导出设置报错。
//
// **不检查几何**：替身没有布局引擎，报告里的 `root/inner overflow` 在这里没有意义，不要据此判断稿对不对。
// 与 audit.js 的分工：audit.js 静态看引用，smoke.js 动态看执行结果，两者都不替代在 Figma 里跑一次。

const fs = require('fs');
const path = require('path');
const { createFigmaStub } = require('./stub-figma');

const here = __dirname;
const source = ['icons.js', 'main.js']
  .map((f) => fs.readFileSync(path.join(here, f), 'utf8'))
  .join('\n\n');

const { figma, log, collections, variables, pages } = createFigmaStub();
const problems = [];
const expect = (ok, label) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}`);
  if (!ok) problems.push(label);
};

// 生成器在加载末尾自跑 main()（和 Figma 里的生命周期一致），所以这里只求值一次、等它结束，
// 不要再手动调一次 main()——两次并发会交叉，计数全乱。
new Function('figma', 'console', source)(figma, console);

const waitForReport = async (ms) => {
  const deadline = Date.now() + ms;
  while (log.closed === null && Date.now() < deadline) await new Promise((r) => setTimeout(r, 10));
  return log.closed;
};

waitForReport(5000).then((report) => {
  if (report === null) {
    console.error('SMOKE FAIL: 生成器 5 秒内没有结束（可能卡在 await 上）');
    process.exit(1);
  }
  if (report.startsWith('BUILD FAILED')) {
    console.error(`SMOKE FAIL: ${report}`);
    process.exit(1);
  }

  const valueOf = (prefix) => Number((report.split('\n').find((l) => l.startsWith(prefix)) || '=').split('=')[1]);
  const boards = valueOf('boards=');
  const dark = valueOf('dark boards=');

  // 报告里的几何类结论（含 AUDIT VERDICT）由替身算不出来，原样打印会让人误以为骨架坏了，所以逐行标注。
  const GEOMETRY_PREFIXES = ['AUDIT VERDICT:', 'root overflow=', 'inner overflow='];
  console.log('--- 生成器报告（`~` 行 = 替身无布局引擎，不可信）---');
  console.log(
    report
      .split('\n')
      .map((line) => (GEOMETRY_PREFIXES.some((p) => line.startsWith(p)) ? `~ ${line}（替身不可信）` : line))
      .join('\n'),
  );
  console.log('--- 结构断言 ---');

  expect(log.notify.length === 1 && log.notify[0] === report, '报告同时走 notify 与 closePlugin');
  expect(pages.length <= 3, `页数 ${pages.length} 不超过免费版上限 3`);
  expect(valueOf('bind errors=') === 0, '没有 paint 绑定失败');
  expect(valueOf('export errors=') === 0, '没有导出设置写入失败');
  expect(valueOf('placeholder fill=') === 0, '没有停在占位灰的填充');
  expect(valueOf('stray top-level=') === 0, '没有游离的顶层节点');
  expect(
    collections.map((c) => c.name).join(',') === 'Design Tokens,Design Tokens Dark',
    '两套颜色变量集合都在（免费版每集合 1 个 mode）',
  );

  const topLevel = figma.root.children.flatMap((p) => p.children);
  expect(topLevel.length === boards && boards > 0, `画板 ${boards} 块，全部挂在页面上`);
  expect(topLevel.every((n) => n.type === 'FRAME'), '顶层只有 FRAME（组件集在画板里）');
  expect(
    topLevel.every(
      (n) =>
        n.exportSettings.length === 2 &&
        n.exportSettings[0].constraint.value === 4 &&
        n.exportSettings[1].format === 'SVG' &&
        !n.exportSettings[1].constraint &&
        n.exportSettings[1].svgOutlineText === false,
    ),
    '每块画板都是 PNG@4x + SVG 两条设置，SVG 不带 constraint 且保留 <text>',
  );
  expect(dark === boards / 2 && dark > 0, `深色画板 ${dark} 块，与 ${boards - dark} 块浅色一一对应`);
  expect(
    topLevel.filter((n) => n.name.endsWith(' · Dark')).length === dark,
    '深色画板按后缀可辨认（也是文件名的一部分）',
  );

  const paintsOf = (node, out = []) => {
    for (const field of ['fills', 'strokes']) {
      for (const p of node[field] || []) if (p.boundVariables && p.boundVariables.color) out.push(p.boundVariables.color.id);
    }
    for (const c of node.children) paintsOf(c, out);
    return out;
  };
  // 集合内变量走全量列表 + variableCollectionId 过滤，和生成器在真机上的取法一致。
  const idsOf = (name) => {
    const coll = collections.find((c) => c.name === name);
    return new Set(variables.filter((v) => v.variableCollectionId === coll.id).map((v) => v.id));
  };
  const darkIds = idsOf('Design Tokens Dark');
  const lightIds = idsOf('Design Tokens');
  const darkPaints = topLevel.filter((n) => n.name.endsWith(' · Dark')).flatMap((n) => paintsOf(n));
  const lightPaints = topLevel.filter((n) => !n.name.endsWith(' · Dark')).flatMap((n) => paintsOf(n));
  expect(darkPaints.length > 0 && darkPaints.every((id) => darkIds.has(id)), `深色画板的 ${darkPaints.length} 个绑定全在 Dark 集合`);
  expect(lightPaints.length > 0 && lightPaints.every((id) => lightIds.has(id)), `浅色画板的 ${lightPaints.length} 个绑定全在浅色集合`);
  expect(darkPaints.length >= lightPaints.length, '深色克隆没有丢绑定');

  console.log(`\n${problems.length ? `SMOKE FAIL (${problems.length})` : 'SMOKE OK'}`);
  process.exit(problems.length ? 1 : 0);
});
