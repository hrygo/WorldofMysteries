# 《诡秘世界》Figma 设计套件生成器 (Figma Kit)

> **版本**：v1.0.0  
> **核心原则**：**“稿是生成的，不是画的”**。生成器脚本是稿的源码，Figma 文档是产物，代码里的 token 文件是运行态事实。  
> **单一事实源**：[`docs/05_UI/design_tokens.json`](../design_tokens.json)  
> **离线门禁**：`audit.js`（静态引用检查）+ `smoke.js`（离屏冒烟测试）全部通过。

---

## 1. 画板构成与页预算 (Page Budget)

针对 Figma 免费 Starter Plan 每文件最多 3 页的硬限制，本生成器声明 2 页，平铺容纳全部画板：

| 页码与名称 | 画板名称 | 包含内容 |
|:---|:---|:---|
| **`01 Design Tokens`** | `Design Tokens` / `Design Tokens · Dark` | 22 项全色阶调色板 Swatches、8 级排版层级 Typography Scale、间距标尺与同心圆角几何体系 |
| **`02 Components`** | `Core Components` / `Core Components · Dark` | 6 大核心 UI 组件变体集：`Listening Ring` (4态), `Sidebar Row` (2态), `Victorian Card` (3材质), `Spirituality Gauge` (3档), `Database HUD Card` (2类), `Advice Input` (2态) |

---

## 2. 离线三道门禁校验命令

```bash
# 1. 语法检查与悬空引用静态自检 (必须显示 AUDIT OK)
node --check main.js && node audit.js

# 2. 离屏替身 API 冒烟测试 (15 项结构断言必须全部 ok，SMOKE OK)
node smoke.js

# 3. 打包生成桌面端可用插件 (产物输出至 ~/Downloads)
node build.js
```

---

## 3. 在 Figma 桌面版中生成设计稿 SOP

1. **打开 Figma 桌面版**（`/Applications/Figma.app`）；
2. 新建一个空白文件，命名为 **《诡秘世界》Design Kit**；
3. 点击顶部菜单：**Plugins → Development → Import plugin from manifest...**；
4. 选择目录：`~/Downloads/World-of-Mysteries-Design-Kit-figma-kit/manifest.json`；
5. 点击 **Plugins → Development → World of Mysteries Design Kit** 运行插件；
6. 插件将在 1 秒内自动创建两个页面、生成 4 块标准画板、建立 Design Tokens 颜色变量集，并输出生成报告。

---

## 4. 导出与核验

本生成器已自动为所有画板注入 `PNG @4x`（超清像素走查）与 `SVG`（保留 `<text>`，供 Agent 可机读分析）导出规则：
* 在 Figma 中选择全部画板后，按下快捷键 `Cmd + Shift + E`；
* 导出目标目录建议为 `docs/05_UI/exports/`。
