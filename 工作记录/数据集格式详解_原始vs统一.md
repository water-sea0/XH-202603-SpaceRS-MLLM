# 各数据集原始信息 → 统一标准格式 对照详解

> 目标：搞清楚每个数据集**原本有什么信息**，与统一 LLaVA conversation 格式有何区别。

---

## 零、目标标准格式

```json
{
  "id": "来源/任务/索引",
  "images": ["绝对路径/tile.jpg", ...],
  "conversations": [
    {"from": "human", "value": "<image>...\n[token前缀] 问题"},
    {"from": "gpt",   "value": "标准答案"}
  ],
  "task": "changecaption|changedetection|caption|refer|vqa",
  "sensor": "optical", "resolution": 256, "bands": "rgb",
  "source": "levir_mci|levir_cc|vrsbench|xlrs_lite|mme_realworld",
  "language": "en|zh"
}
```

`<image>` token 数量 = images 列表长度。token 前缀 `[传感器类型（optical，有必要吗？） 图像分辨率 波段组合（rgb，依旧没必要啊）][任务类型标记]` 注入在 human message 的问题文本之前。

*质疑其必要性，传感器类型全部为optical，波段均为rgb，不知道是否有必要添加*
---

## 一、LEVIR-MCI / Levir-CC

两个数据集使用**完全相同的 JSON 格式**，仅图片数量和目录不同。

### 原始标注 `LevirCCcaptions.json`

```json
{
  "images": [
    {
      "filepath": "train",              // train/val/test
      "filename": "train_000001.png",
      "imgid": 0,                       // 全局 ID
      "changeflag": 0,                  // ★ 0=无变化, 1=有变化 → Change Detection 标签
      "sentences": [                    // ★ 5句变化描述 → Change Captioning 标注
        {"imgid": 0, "sentid": 0,
         "raw": " there is no difference .",
         "tokens": ["there", "is", "no", "difference"]},
        // ... 共 5 句（changeflag=1 时描述具体变化, =0 时描述"无变化"）
      ],
      "sentids": [0, 1, 2, 3, 4],       //顺延，例如第二张图片就包含56789
      "split": "train"
    }
  ]
}
```

### 原始图像

```
LEVIR-MCI/LEVIR-MCI-dataset/images/
├── train/{A,B}/  (各 6815 png, 256×256)
├── val/{A,B}/    (各 1333)
└── test/{A,B}/   (各 1929)

Levir-CC-dataset/images/
├── train/{A,B}/  (各 7,590)
├── val/{A,B}/    (各 1,438)
└── test/{A,B}/   (各 2,135)
```

#### 注：
1. Levir-CC中标注对与图片对数不一一对应，三个划分集分别缺775、105、206张，这些图片对没有对应的标注对，只有binary changeflag 标签
2. A/B 为同名配对：`train_000001.png` 的时相 A 和时相 B 分别在 `train/A/` 和 `train/B/` 下。
3. 将`filepath`归类到`split`，**丢弃**`sentences[].tokens`分词列表, **丢弃**冗余的`sentids`后归为统一格式，**新增**`changeflag`条目，**新增**`changecaption`、`changedetection`的标准任务描述
4. 每条sentence对应一条输出

### 输出示例

```json
// ── changecaption (每条 sentence 一条) ──
{
  "id": "levir_mci/train/000000_0",
  "images": ["F:/.../train/A/train_000001.png", "F:/.../train/B/train_000001.png"],
  "conversations": [
    {"from":"human", "value":"<image>\n<image>\n[optical 256 rgb][changecaption] Describe the changes between the two images."},
    {"from":"gpt",   "value":"there is no difference."}
  ],
  "task":"changecaption", "sensor":"optical", "resolution":256, "bands":"rgb",
  "source":"levir_mci", "language":"en", "split":"train"
}
// ── changedetection (每对图一条) ──
{
  "id": "levir_mci/train/000000_det",
  "conversations": [
    {"from":"human", "value":"<image>\n<image>\n[optical 256 rgb][changedetection] Is there any change between the two images? Answer with 'change' or 'no change'."},
    {"from":"gpt", "value":"no change"}
  ],
  "task":"changedetection", ...
}
```

---

## 二、VRSBench

### 原始标注 `VRSBench_train.json`（142,390 条）

**已经被整理为 LLaVA conversation 格式**，但缺少模态前缀，且 `id` 字段无意义：

```json
{
  "id": "Final_Data/v1.2",              // 固定值, 全部一样, 无区分意义
  "image": "00002_0000.png",            // 文件名(不含路径)
  "conversations": [
    {"from":"human", "value":"<image>\n[caption] Could you describe the contents of this image for me?"},
    //                         ^^^^^^^^ [caption]/[refer]/[vqa] 任务标记
    {"from":"gpt",   "value":"The image, sourced from GoogleEarth, shows..."
    // 或 refer: "{<45><45><59><59>}"  ← 归一化百分号坐标 {<x1><y1><x2><y2>}
    // 或 vqa:   "expressway-toll-station"  ← 短答案
    }
  ]
}
```

三种任务数量：caption 20,264 / refer 36,313 / vqa 85,813

### 原始图像

```
VRSBench/data/
├── Images_train/  (20,264 png, 全部 512×512)
└── Images_val/    (9,350 png, 全部 512×512)
```

#### 注：

1. 每张图片都包含若干个不同任务的标注，例如`00002_0000.png`就包含1条caption（整图描述）,2个object（收费站 + 车辆，各带坐标和 referring sentence）,4对VQA
2. 原始id为固定值，改为我们的id格式
3. 不处理`data/Annotations_train/`文件夹中的内容，LLaVA JSON已含全部所需信息
4. 保留512×512输入 **不切图**。听说模型自身的processor会自动将其resize+pad到合法尺寸（28的倍数），512在多数VL模型的输入窗口范围内, 切成4个448 tile反而引入噪声。

---

## 三、XLRS-Bench-lite

### 原始格式：HuggingFace Arrow 分片（暂未解压）

| 字段 | 类型 | 示例值 |
|------|------|--------|
| `path` | string | `"DOTA_v2_4096_4096/dota_v2_..._P5729.png"` |
| `index` | int32 | 行序号 |
| `question` | string | `"The width and calmness of the river...suggest?"` |
| `multi-choice options` | list[string] | `["(A) It is a vital...", "(B) This area...", ...]` |
| `answer` | string | `"D"` (选项字母) |
| `category` | string | `"Complex reasoning/Anomaly Detection...""` |
| `l2-category` | string | `"default"` (全部相同, 无信息量) |
| `image` | list[struct{bytes, path}] | 内嵌 JPEG 字节 + 路径 |

类别（10 shard 采样）：Object spatial relationship ~52%, Complex reasoning 两类 ~48%。全部为多选题 VQA。

图像内嵌为 JPEG 字节 (~12MB/张, 4096×4096), 需提取后切图。

### 转换对照表

| | 原始有什么 | 统一格式怎么处理 |
|---|---|---|
| **保留** | `question` + `multi-choice options` | → human value `"{问题}\n{选项列表}\nAnswer with the letter..."` |
| **保留** | `answer` | → gpt value (选项字母) |
| **保留** | `category` | → 可选 `category` 字段 |
| **变形** | `image[0].bytes` (内嵌 JPEG) | → 提取→解码→切 448×448 tiles, 存为独立 JPEG。4096²→81 tiles |
| **新增** | — | `task="vqa"` |
| **新增** | — | `id` = `"xlrs_lite/{index:06d}"` |
| **新增** | — | N 个 `<image>` (N = tile 数) + token 前缀 |
| **新增** | — | `sensor`, `bands`, `resolution`, `source`, `language` |
| **丢弃** | `l2-category` | 全部 `"default"`, 零信息 |
| **丢弃** | `path` | 图片已提取, 原始路径无用 |

---

## 四、MME-RealWorld（仅 Remote Sensing 子集）

### 原始标注 `MME_RealWorld.json` (EN 23,609) + `MME_RealWorld_CN.json` (ZH 5,917)

```json
{
  "Question_id": "perception/remote_sensing/color/0001",
  "Question Type": "Multiple Choice",           // 固定值
  "Image": "remote_sensing/03553_Toronto.png",  // 相对路径 (相对于 images/)
  "Text": "What color is the roof of the square building...?",
  "Answer choices": ["(A) Yellow", "(B) Blue", "(C) Gray", "(D) White", "(E) ..."],
  "Ground truth": "D",                          // 单个选项字母
  "Task": "position",
  "Subtask": "Remote Sensing",                  // 遥感图
  "Category": "color",
  "Dataset": "dota_v2"
}
```

MME-RealWorld 共 6 个场景（Autonomous Driving / MME-HD-CN / Diagram & Table / Monitoring / OCR / Remote Sensing），我们只取其中 Subtask=="Remote Sensing" 的子集：共引用 1,265 张图，包含英文 3,738 条 + 中文 300 条 ≈ 4,000 QA 对。

### 原始图像

```
MME-RealWorld/images/remote_sensing/  (1,086 个 png, 4096~7360 px)
```


#### 注：

1. 引用中包含约1200张图片, 实际存在约1000张, 说明图片和引用的映射可能有问题。
2. 将`Question Type`固定为Multiple Choice，**丢弃**`Task`，仅使用Category，**丢弃**非 RS 子集全部条目，只保留遥感场景图片

---

## 五、总结

### 所有数据集统一新增的信息

原始数据集中**无一包含**以下字段, 全部是我们根据遥感领域知识补充的：

| 新增字段 | LEVIR-MCI | LEVIR-CC | VRSBench | XLRS-lite | MME-RS |
|----------|-----------|----------|----------|-----------|--------|
| `sensor` | optical | optical | optical | optical | optical |
| `resolution` | 256 | 256 | 512 | 4096 | 4096~7360 |
| `bands` | rgb | rgb | rgb | rgb | rgb |
| `task` | changecaption / changedetection | changecaption | caption / refer / vqa | vqa | vqa |
| `source` | levir_mci | levir_cc | vrsbench | xlrs_lite | mme_realworld |
| token 前缀 | ✅ | ✅ | ✅ | ✅ | ✅ |

### 所有数据集统一丢弃的信息

| 丢弃的字段 | 原因 |
|-----------|------|
| LEVIR: `filepath`, `sentids`, `tokens` | 冗余/训练不需要 |
| VRSBench: 原始 `id` | 固定字符串无意义 |
| VRSBench: `Annotations_train/` | LLaVA JSON 已含全部标注 |
| XLRS-lite: `l2-category` | 全部 `"default"` |
| XLRS-lite: `path` | 图片已提取 |
| MME: `Question Type`, `Task` | 无信息量或太粗 |
| MME: 非 RS 的 4 个场景 | 不相关 |

### 图像处理策略

| 数据集 | 原图尺寸 | 切图？ | 理由 |
|--------|---------|--------|------|
| LEVIR-MCI/CC | 256×256 | 否 | <448 |
| VRSBench | 512×512 | 否 | 512 在多数 VL 模型可接受范围，切图反而有害 |
| XLRS-lite | ~4096×4096 | 是 (81 tiles) | 必须 |
| MME-RS | 4096~7360 | 是 | 必须 |

*建议：896以下的尺寸保留原尺寸，期待processor发力，能够切成4个tile以上的则切*

*但是4096的切完剩下100多个像素，7360切完剩200多个像素，是新加一个tile还是让其他像素分还是下采样还是把tile改大？还是干脆直接塞原图？*

*不管了，都试一下不就好了，不是改进重点*