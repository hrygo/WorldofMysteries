#!/usr/bin/env node
// 合成 code.js（icons.js + main.js），并把 code.js 与 manifest.json 写到 Figma 插件选择器可访问的目录。
// 构建产物只写在仓库外，不纳入版本控制。

const fs = require('fs');
const os = require('os');
const path = require('path');

const NAME = require('./manifest.json').name;
const DEFAULT_OUT = path.join(os.homedir(), 'Downloads', `${NAME.replace(/\s+/g, '-')}-figma-kit`);

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const here = __dirname;
const outDir = arg('out', DEFAULT_OUT);

// 骨架默认的插件名/id 只够跑一次试做。多个项目都沿用它，Development 子菜单里会出现同名条目，
// 而菜单项与辅助函数都按名字匹配——可能跑到另一个项目的 kit 上。在离线门禁这里就说清楚。
if (NAME === 'Design Kit' || require('./manifest.json').id === 'design-kit-local-dev') {
  console.warn('警告：manifest.json 的 name / id 仍是骨架默认值。正式使用前改成带项目前缀的唯一值，');
  console.warn('      否则多个项目的开发插件在 Figma 里同名，会跑到别的 kit 上。');
}

const parts = ['icons.js', 'main.js'].map((f) => {
  const p = path.join(here, f);
  if (!fs.existsSync(p)) throw new Error(`missing source: ${f}`);
  return `// ---- ${f} ----\n${fs.readFileSync(p, 'utf8')}`;
});

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'code.js'), parts.join('\n\n'));
fs.writeFileSync(path.join(outDir, 'manifest.json'), fs.readFileSync(path.join(here, 'manifest.json')));

console.log(`built -> ${path.join(outDir, 'code.js')}`);
console.log('在 Figma 桌面版：Plugins → Development → Import plugin from manifest…，指向同目录的 manifest.json');
