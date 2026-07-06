# 各数据集到 RS-VL-1.0 的字段映射

> 配套 schema：`工作记录/rs-vl-1.0.schema.json`  
> 路径基准：工作区中的 `dataset/` 作为 dataset root；manifest 中不得出现盘符绝对路径。

## 共同规则

- 一个 canonical record 表示一个图像组上的一个任务实例。
- 同一底层图像或时相对必须使用相同 `image_group_id`，用于去重和 split 防泄漏。
- 原始图片不复制、不改名、不重编码；Arrow 内嵌图片使用 `arrow` locator。
- `width/height` 是像素尺寸；`gsd_m` 只接受来源明确提供的米/像素值，否则为 `null`。
- `boxes[].xyxy` 统一为相对于**原始整图**的 `[0,1]` 浮点坐标；必须满足 `0 <= x1 < x2 <= 1`、`0 <= y1 < y2 <= 1`。
- caption 的多个参考答案在 canonical 中保存在同一条记录的 `target.texts`；训练导出时可按 reference 展开，评测时只预测一次。
- 选择题的选项保存在 `choices`，答案保存在 `target.answer`。adapter 决定模型最终输出选项字母还是完整答案。

## 1. LEVIR-MCI（本工作区唯一双时相来源，同时代替本地 Levir-CC）

| Canonical 字段 | 来源/规则 |
|---|---|
| `source` | `levir_mci` |
| `source_split` | 原 `split` |
| `image_group_id` | `levir/{split}/{filename_without_ext}` |
| `media[0]` | `images/{split}/A/{filename}`, role=`t1` |
| `media[1]` | `images/{split}/B/{filename}`, role=`t2` |
| `task=change_captioning` | 每个图像对生成 1 条；`sentences[].raw` 合并到 `target.texts` |
| `task=change_detection` | 每个图像对生成 1 条；`changeflag=1/0` 映射为 `change/no_change` |
| `meta.changeflag` | 保留原值 |
| `meta.mask_locator` | 可选，指向 LEVIR-MCI 的 label；当前五类任务不把 mask 作为模型输入 |

处理决定：

- 不再单独转换 `Levir-CC-dataset`。本地两份 JSON 解析后完全相等，同名 A/B 图抽查逐像素相同；重复加入会把同一场景计算两次。
- 评测按 image pair 计数，而不是把五条 caption 当五个独立测试样本。
- 两个时相各自保持 256×256；不离线放大到 280 或 448。

## 2. VRSBench

### Train

| Canonical 字段 | 来源/规则 |
|---|---|
| `source` | `vrsbench` |
| `source_split` | `train` |
| `image_group_id` | `vrsbench/train/{image_stem}` |
| `media` | `data/Images_train/{image}`，role=`image` |
| `task` | 从原 human 文本中的 `[caption] / [refer] / [vqa]` 读取 |
| `prompt` | 删除原任务 token 与 `<image>` 后保留自然语言问题 |
| caption/VQA target | 原 gpt 文本 |
| grounding target | 解析 `{<x1><y1><x2><y2>}` 百分坐标为 `[0,1]` xyxy |

### Val/Eval

- 以 `data/Annotations_val/*.json` 为权威来源，关联 `data/Images_val/`。
- 每张图最多生成：1 条 caption、若干 grounding、若干 VQA；20GiB bundle 再按每图上限抽取。
- `obj_coord` 已是归一化 HBB；`obj_corner` 是 OBB，初版 canonical 同时可放入 `meta`，但五任务 baseline 使用 HBB。
- `VRSBench_EVAL_referring.json` 和 `VRSBench_EVAL_vqa.json` 用作与官方评测 ID/问题的交叉核对，避免重复创造另一套 test split。

## 3. XLRS-Bench-lite

| Canonical 字段 | 来源/规则 |
|---|---|
| `source` | `xlrs_lite` |
| `source_split` | `benchmark`（HF 物理 split 名虽为 train） |
| `task` | `vqa` |
| `image_group_id` | 优先使用规范化后的原 `path`；再以像素 hash 去重 |
| `media.locator` | Arrow shard 相对路径 + row + column=`image` + index=0 |
| `prompt` | 原 `question` |
| `choices` | 原 `multi-choice options` |
| `target.answer` | 原 `answer` 字母 |
| `category` | 原 `category` |

处理决定：

- 这是 3,080 条英文多选 benchmark VQA，不进入 smoke_train。
- 不按 shard 抽样，也不预先把每张 4096 图切成 81 张 JPEG；bundle sampler 只物化被抽中的 Arrow 行。
- `l2-category=default` 可放在 provenance/meta，但不作为分层依据。

## 4. XLRS-Bench_caption_zh

| Canonical 字段 | 来源/规则 |
|---|---|
| `source` | `xlrs_caption_zh` |
| `source_split` | `train`；从 image_group 层固定留出 `dev` 仅用于本项目评测 |
| `task` | `image_captioning` |
| `image_group_id` | 原 `id`/图像 path；用像素 hash 检查跨 shard 重复 |
| `media.locator` | Arrow shard + row + column=`image` |
| `prompt` | 优先保留原 `question`，不要统一覆盖成同一句模板 |
| `target.texts` | 原 `answer` 列表，过滤空字符串但不展开 |

处理决定：

- 当前本地缺 `data-00012-of-00023.arrow`，全量 manifest 必须标注 incomplete；不能假装已覆盖全数据。
- dev 留出须按 `image_group_id`，不能按 caption 行随机切分。

## 5. XLRS-Bench_visual_grounding_zh

| Canonical 字段 | 来源/规则 |
|---|---|
| `source` | `xlrs_grounding_zh` |
| `source_split` | 原 train/test |
| `task` | `visual_grounding` |
| `image_group_id` | 图像 path/id + 像素 hash 去重 |
| `media.locator` | Arrow shard + row + column=`image` |
| `width/height` | 原 `image_width/image_height`，并与实际图片头核对 |
| `prompt` | 从原 `question` 提取定位描述；保留完整原问题到 `meta.original_question` |
| `target.boxes[0].xyxy` | 原 `bbox`，核验范围与 xyxy 顺序 |
| `category` | 原 `category` |

处理决定：

- test 用于 eval，train 可用于 smoke_train。
- 不把整图 bbox 配给一串无位置说明的离线 tiles。模型 adapter 对整图做自己的动态处理，预测后统一回到原图归一化坐标。
- 若未来新增显式滑窗，必须为每个窗口记录原图 `window_xyxy`，并实现 bbox 正反变换；初版不启用。

## 6. MME-RealWorld Remote Sensing

| Canonical 字段 | 来源/规则 |
|---|---|
| `source` | `mme_realworld_rs` |
| `source_split` | `benchmark` |
| `task` | `vqa` |
| `image_group_id` | 规范化后的 `Image` 路径；不能只用 stem |
| `media` | `MME-RealWorld/images/{Image}` |
| `prompt` | 原 `Text` |
| `choices` | 原 `Answer choices` |
| `target.answer` | 原 `Ground truth` 字母 |
| `language` | EN JSON=`en`，CN JSON=`zh` |
| `category` | color/count/position |
| `meta.dataset` | 原 `Dataset` |
| `provenance.record_id` | 原 `Question_id` |

处理决定：

- 仅保留 Subtask 为 Remote Sensing 的条目；其任务就是通用多选 VQA，在总任务统计与 20GB 配额中必须明确列出，不能漏掉。
- MME 是 benchmark。若用其中少量条目检查训练程序，必须丢弃该次权重并从干净 checkpoint 重新开始正式评测；20GB 包仍把它们标为 eval，防止误用。
- EN RS 当前 1,265 个引用图中有 208 个本地缺失；先尝试补下载，仍缺失的条目不进入有效 manifest，只写入本地审计报告。
- 同图多题只复制一次媒体；bundle 按 image_group 抽样，再从每图最多保留 3 个问题。

## 7. 模型导出契约

### Qwen2.5-VL

- `media` 顺序转为多个 `{"type":"image"}` content item，随后放 text item。
- t1/t2 在文本中明确标号；图片数必须与 content item 数一致。
- 图像运行时由 processor 调整到 28 倍数，canonical 原图不变。
- grounding target 从 `[0,1]` 乘以 adapter 实际采用的坐标空间；模型输出再反变换到 canonical 原图坐标后评分。

### EarthDial

- file/Arrow locator 先解析为 PIL image 列表。
- 双时相按两张图传入；每张图的动态 tile 数单独记录，总 `max_dynamic_patch` 在图片间共享。
- conversation 中每张独立图对应一个 `<image>`；不得把几十个内部 tile 当成几十张语义独立图写 placeholder。
- task/modality token 由 EarthDial adapter 根据可信元数据生成；缺 GSD 时不伪造数值。
- canonical manifest 不保存 EarthDial 内部 448 tile，因为它们是特定模型、特定 profile 的运行时产物。
