# 美术资产存储策略 v1.0

> **状态**：已定案 · 2026-09-19
> **决策者**：项目所有者（AGT-ARB 执行）
> **取代**：`Premium_Art_Production_Pipeline_v2.0.md` 第 16 节中「Git LFS 或外部 artifact store，
> 按仓库策略决定」的悬置表述

## 1. 分层与归属

| 层 | 内容 | 归宿 | 是否入库 |
|:---|:---|:---|:---|
| 运行时 derivative | `Assets.xcassets` 内的场景/世界/神器图片 | `macos-app/WorldOfMysteries/Assets.xcassets/` | ✅ 入库 |
| 审批源图 | `source.png`（原生分辨率生成结果） | `docs/05_UI/artwork/sources/` | ✅ 入库 |
| 设计参考 | 12 张高保真原型参考、生成原图 | `docs/05_UI/assets/` | ❌ 本机资产 |
| 生产母版 | 4K/6K master、super-resolution 输出、调色结果、裁剪与 QA 中间产物 | `docs/05_UI/artwork/workbench/` | ❌ 本机资产 |
| 证据与索引 | provenance / QA / manifest / 本文件 | `docs/05_UI/artwork/{provenance,qa}/` | ✅ 入库 |

## 2. 三条判据

1. **能不能重建**：可由入库物确定性重建的（derivative 由 master 下采样得到）不入库中间态；
   不可重建的（生成原图、人工审批依据）必须留在本机并靠 manifest + SHA256 可校验。
2. **有没有运行时用途**：App 真正加载的副本入库；只用于人看的参考不入库。
3. **体积是否与价值相称**：单张超 MB 级、且能被后续流水线重新产出的中间产物不进 Git 历史——
   GitHub 对仓库体积的建议是「尽量小于 1 GB，强烈建议小于 5 GB」，单文件超过 50 MiB 会告警。

## 3. 为什么不用 Git LFS

Git LFS 解决的是「必须入库但是大」的矛盾，本项目的母版并不属于这一类（第 2 节判据 3），
引入 LFS 只会额外承担按套餐计量的存储与带宽成本，并把 GB 级二进制绑进每次 clone。
当前 `.git` 体积约 180 MB 量级、最大单文件约 8 MB，远在硬限制之内；
**触发重新评估的条件**：仓库体积超过 500 MB，或出现必须入库且单文件超过 20 MiB 的资产。

## 4. 本地母版库（`workbench/`）

```text
docs/05_UI/artwork/workbench/
├── world-scenes/     # W1-W6：crop / super-resolution / grade / 4096x2560 master
├── artifacts/        # A01-A15：同构的中间产物与母版
├── weights/          # Real-ESRGAN 权重（重建母版的必要输入，仓库内无法重建）
└── （目录整体不入库）

docs/05_UI/artwork/local_store_manifest.json
                      # 入库的索引：路径 / 字节数 / SHA256 / 与 provenance 的一致性
```

- 目录整体由 `.gitignore` 第 9 节排除，**必须留在项目目录内**，不得移到 `/tmp` 或仓库之外；
- `local_store_manifest.json` 由 [`tools/local_store_manifest.py`](tools/local_store_manifest.py) 生成，
  只记录哈希与体积，本身**不含二进制、不含绝对路径**，因此入库并随仓库分发；
- 校验：`python3 docs/05_UI/artwork/tools/local_store_manifest.py verify`
  逐条比对母版 SHA256 与 provenance 中记录的 `master.sha256`，不一致即报错。

## 5. 可重建性的边界（诚实声明）

当前 provenance 记录 `generator.provider` / `generation_id`，但 `model` 与
`source_prompt_digest_sha256` 为 `null`，且生成时的对话式迭代过程无法从仓库还原。
因此：

- **可校验**：母版一旦丢失，manifest 能证明「新文件不是原来的那个」；
- **不可重建**：无法据此重新生成同一张母版。

回填这些字段需要在后续生产中有意识地记录模型版本、提示词摘要与随机种子；
在那之前，母版的冗余只能靠本机副本与备份承担，不能靠"以后能再生成一次"。

## 6. 运行时图像编码档位

| 档位 | 手段 | 实测收益 | 保真度 | 是否默认执行 |
|:---|:---|:---|:---|:---|
| 无损重打包 | 去掉全不透明 alpha 通道 + zlib level 9 重编 PNG | 80.9 MB → 64.7 MB（18 张，1.25x） | 逐像素一致（RGB24 平面 SHA256 相同） | ✅ |
| HEIC | `sips` 编码为 HEIC（Q100） | 单张再省约 18-33% | PSNR 50.6-51.6 dB、SSIM 0.9972-0.9976（有损） | ❌ 需人工视觉签核 |

两档都由 [`tools/reencode_runtime_assets.py`](tools/reencode_runtime_assets.py) 执行，
证据写入 [`qa/`](qa/) 并回填 provenance。

**为什么 HEIC 不默认开**：把质量从 Q85 提到 Q98，PSNR 中位数只从 37.31 升到 37.45——
损失来自色度下采样，不是质量档位，因此 HEIC 换不来"近无损"。这些插画已通过
`USER_APPROVED` 视觉审批，替换其像素需要重新走一遍视觉复核，不能由编码优化顺手完成。
