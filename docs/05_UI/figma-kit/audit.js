#!/usr/bin/env node
// 静态自检（不需要 Figma）：生成器引用的颜色变量 / 文本样式 / 图标，是否都能在自身的表里解析到。
// 退出码非 0 表示存在悬空引用。

const fs = require('fs');
const path = require('path');

const here = __dirname;
// 整行注释不参与扫描：三种字面量写法常被当成示例写进注释，不剥掉就会变成"悬空引用"。
// 只剥整行注释，行尾注释与字符串里的内容照常保留。
const stripLineComments = (src) =>
  src
    .split('\n')
    .filter((line) => !/^\s*\/\//.test(line))
    .join('\n');
const read = (f) => stripLineComments(fs.readFileSync(path.join(here, f), 'utf8'));

// 抓取 `const NAME = { ... };` 的整块
function tableBlock(src, varName) {
  const start = src.indexOf(`const ${varName} = {`);
  if (start < 0) return '';
  let depth = 0;
  let i = src.indexOf('{', start);
  const from = i;
  for (; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1;
    else if (src[i] === '}') {
      depth -= 1;
      if (depth === 0) break;
    }
  }
  return src.slice(from, i + 1);
}

// 顶层条目：按 depth 0 的逗号切 `key: value`，key 可带引号。
// 单行声明（`const RADII = { a: 1, b: 2 };`）与一行一个 key 的写法都能取到；
// 不解析字符串里的逗号（表里没有这种值，遇到就把这条当解析失败，不猜）。
function tableEntries(block) {
  const inner = block.slice(1, -1);
  const entries = [];
  let depth = 0;
  let buf = '';
  const flush = () => {
    const m = /^\s*'?([A-Za-z0-9_./-]+)'?\s*:\s*([\s\S]*?)\s*$/.exec(buf);
    if (m) entries.push({ name: m[1], value: m[2].replace(/,\s*$/, '') });
    buf = '';
  };
  for (const ch of inner) {
    if (ch === '{' || ch === '[' || ch === '(') depth += 1;
    else if (ch === '}' || ch === ']' || ch === ')') depth -= 1;
    if (ch === ',' && depth === 0) {
      flush();
      continue;
    }
    buf += ch;
  }
  flush();
  return entries;
}

function table(src, varName) {
  const block = tableBlock(src, varName);
  return { block, names: new Set(tableEntries(block).map((e) => e.name)) };
}

const main = read('main.js');
const icons = read('icons.js');

// --print-tokens：打印稿侧的 token 清单，供实现侧对齐与交接包登记。
// pipeline 阶段 0.2 要求"生成器 / Figma variables / 代码三处同源且可校验"，这里给出其中的稿侧那一列。
if (process.argv.indexOf('--print-tokens') !== -1) {
  for (const name of ['COLORS', 'DARK_COLORS', 'RADII', 'TEXT_STYLES']) {
    const entries = tableEntries(tableBlock(main, name));
    console.log(`${name} (${entries.length})`);
    for (const e of entries) console.log(`  ${e.name.padEnd(18)}${e.value}`);
  }
  process.exit(0);
}

// 静态自检只认这三种字面量写法。绕过它们（例如把名字放进变量再传）就失去校验，
// 这是刻意的取舍：形式稍严，但能在没有 Figma 的环境里给出确定结论。
const CHECKS = [
  { label: 'color', re: /fill:\s*'([^']+)'/g, table: table(main, 'COLORS') },
  { label: 'textStyle', re: /text\([^,()]*,\s*'([^']+)'/g, table: table(main, 'TEXT_STYLES') },
  { label: 'text fill', re: /text\([^,()]*,\s*'[^']+'\s*,\s*'([^']+)'/g, table: table(main, 'COLORS') },
  { label: 'icon', re: /drawIcon\(\s*'([^']+)'/g, table: table(icons, 'ICONS') },
  { label: 'icon tint', re: /drawIcon\(\s*'[^']+'\s*,\s*'([^']+)'/g, table: table(main, 'COLORS') },
];

let failed = 0;
for (const { label, re, table: { names } } of CHECKS) {
  const used = new Set();
  let m;
  while ((m = re.exec(main)) !== null) used.add(m[1]);
  re.lastIndex = 0;
  const dangling = [...used].filter((n) => !names.has(n)).sort();
  const unused = [...names].filter((n) => !used.has(n)).sort();
  console.log(`${label}: defined=${names.size} used=${used.size} dangling=${dangling.length}`);
  if (dangling.length) {
    failed += 1;
    console.log(`  DANGLING: ${dangling.join(', ')}`);
  }
  if (unused.length) console.log(`  unused (info): ${unused.join(', ')}`);
}

console.log(failed ? `AUDIT FAIL (${failed} table(s) with dangling refs)` : 'AUDIT OK');
process.exit(failed ? 1 : 0);
