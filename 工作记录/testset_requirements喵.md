# 多任务遥感测试集 — 需求文档

## 1. 目标

构建一个 **自包含、可移植** 的多任务遥感测试集，用于：

| 用途 | 说明 |
|------|------|
| **训练链路验证** | 在服务器上传全量数据前，先用此测试集跑通 LoRA 微调全流程 |
| **模型横向评测** | 覆盖 5 类任务，可评测不同基座模型的开箱能力 |

**硬约束**：总大小 ≤ 30GB（含图像 + 标注），方便快速上传服务器。

---

## 2. 覆盖的 5 个任务

| 任务 | 输入 | 输出 | 数据来源 |
|------|------|------|---------|
| **Change Captioning** | 双时相图 A+B | 变化描述文字 | LEVIR-MCI, Levir-CC |
| **Change Detection** | 双时相图 A+B | change / no change | LEVIR-MCI |
| **Image Caption** | 单张遥感图 | 描述文字 | VRSBench, XLRS-lite |
| **Visual Grounding** | 图 + 文字描述 | bounding box 坐标 | VRSBench, XLRS-lite |
| **VQA** | 图 + 问题 | 答案 | VRSBench, MME-RealWorld(RS), XLRS-lite |

---

## 3. 数据集选取与规模估算

### 现状数据量

| 源数据集 | 总大小 | 图像数 | 样本数 |
|----------|--------|--------|--------|
| LEVIR-MCI | **2.66 GB** | 20,154 | ~30K conversations |
| Levir-CC | **2.5 GB** | ~8,500 对 | ~8.5K conversations |
| VRSBench | 12.1 GB (图像) | 29,614 | 142,390 (train.json) |
| XLRS-lite | 35.6 GB (arrow) | ~3,108 行 | ~3,108 行 × 多任务 |
| MME-RealWorld (RS) | 48.3 GB | 1,265 | ~4,000 QA |

### 选取方案

由于 LEVIR-MCI 和 Levir-CC 本身很小，**全量保留**。其余数据集按比例采样。

| 数据集 | 选取量 | 原始大小 | 处理后大小 | 理由 |
|--------|--------|---------|-----------|------|
| **LEVIR-MCI** | 全量 (train+val+test) | 2.66 GB | ~2.7 GB | 太小，全量保留；唯一含 Change Detection 的数据集 |
| **Levir-CC** | 全量 (train+val+test) | 2.5 GB | ~2.5 GB | 同上，纯 Change Captioning |
| **VRSBench** | val 全量 + train 抽 15% | ~5 GB | ~5 GB | 覆盖 Caption/Refer/VQA 三类任务 |
| **XLRS-lite** | 15-20 shards (~630-840 行) | ~9 GB (原始) | ~3.5 GB (切图后) | EN VQA+Grounding，每行是一张超大图 |
| **MME-RealWorld** | RS 子集抽 ~300 图 | ~12 GB (原始) | ~5 GB (切图后) | EN+ZH 多选题 VQA |
| **合计** | | | **~18-20 GB** | 留 10GB 余量 |

### 各任务样本预估

| 任务 | 来源 | 预估样本数 |
|------|------|-----------|
| Change Captioning | LEVIR-MCI + Levir-CC | ~20,000+ |
| Change Detection | LEVIR-MCI | ~20,000 |
| Image Caption | VRSBench + XLRS-lite | ~3,000 |
| Visual Grounding | VRSBench + XLRS-lite | ~5,000 |
| VQA | VRSBench + XLRS-lite + MME-RS | ~5,000 |

---

## 4. 处理方案

### 4.1 总体思路

**废弃**现有全部 `unified_data/` 输出和旧 converter 脚本，重新写一套更简洁的处理管线。

### 4.2 核心变化 vs 旧脚本

| 项目 | 旧方案 | 新方案 |
|------|--------|--------|
| 图像处理 | 引用原始路径（不拷贝） | **拷贝至统一目录**，保证可移植 |
| Tiling | 对大图切 448×448 tiles | 沿用，但参数可调 |
| 输出目录 | `F:\挑战杯数据集\unified_data\` | **工作区内的 `.\testset\`** |
| MME | 切全量图（费时） | 只切采样后的 RS 子集 |
| VRSBench | 只处理 train | 处理 train + val，采样均衡 |
| 标注格式 | 沿用 LLaVA conversation | 沿用，增加 `task`/`source`/`split` 字段 |
| split 划分 | — | 输出 `train.json` + `val.json`（从测试集中再分 8:2），支持训练链路验证 |

### 4.3 处理步骤

```
原始数据集
  │
  ├─→ [step1] convert_levir_mci   → 拷贝双时相图 + 生成标注
  ├─→ [step2] convert_levir_cc    → 同上
  ├─→ [step3] convert_vrsbench    → 采样 + 拷贝图 + 生成标注
  ├─→ [step4] convert_xlrs_lite   → 采样 shards + 切图 + 生成标注
  ├─→ [step5] convert_mme_rs      → 采样 RS 子集 + 切图 + 生成标注
  │
  └─→ [step6] merge_and_split     → 合并 → 按 8:2 分 train/val → 输出统计
```

### 4.4 目录结构

```
.\testset\
├── images\          ← 所有图像（含 tiles）
│   ├── levir_mci\
│   ├── levir_cc\
│   ├── vrsbench\
│   ├── xlrs_lite\
│   └── mme_rs\
├── annotations\
│   ├── train.json   ← 合并后训练部分 (~80%)
│   └── val.json     ← 合并后验证部分 (~20%)
└── stats.json       ← 各任务/来源统计信息
```

---

## 5. 开放问题

1. **VRSBench 采样策略**：是按任务均衡采样（每类取等量），还是保持原始比例？建议均衡采样以保证每类任务都有足够测试样本。

2. **split 划分粒度**：train/val 按 8:2 全局随机分，还是按数据集+任务分层抽样？建议分层，保证 val 里每类任务都有代表。

3. **Change Detection 标注形式**：旧脚本用 `"change" / "no change"` 二分类文字。是否需要更细粒度（如输出变化区域描述）？

4. **Tiling 阈值**：旧脚本 TILE_SIZE=448。对大图（如 XLRS 的 4096×4096）是否保持？建议保持 448，与主流 VL 模型输入一致。

5. **MME-RealWorld 中英文比例**：RS 子集 EN:ZH ≈ 3700:300。是否保持原始比例还是均衡采样？

---

## 6. 与旧输出的关系

- 删除 `F:\挑战杯数据集\unified_data\` 全部内容
- 删除 `script\` 下除 `utils\` 外的旧 converter（或用新脚本覆盖）
- 新脚本放在 `script\` 下，输出只写到 `.\testset\`
