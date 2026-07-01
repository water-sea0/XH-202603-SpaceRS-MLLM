# LLaVA Conversation JSON 标准格式与我们做的微小改动

## 为什么需要了解这个？

我们手上有 7 个遥感数据集，格式各不相同——JSON、Arrow 二进制、LLaVA conversation、多选题 JSON。要让它们能**一起训练**，必须统一成一种格式。

社区事实上的标准就是 **LLaVA Conversation JSON**。绝大多数训练框架（LLaMA-Factory、LLaVA-NeXT、Qwen-VL 等）都支持它。我们选这个格式作为目标，改动尽量小。

---

## 标准 LLaVA Conversation JSON

### 一条样本的完整结构

```json
{
  "id": "一个人类可读的标识符（可选但推荐）",
  "image": "相对路径/到/图片.jpg",
  "conversations": [
    {
      "from": "human",
      "value": "<image>\n这里是用户说的话或指令"
    },
    {
      "from": "gpt",
      "value": "这里是模型应该给出的回答"
    }
  ]
}
```

### 逐字段解释

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 否 | 样本唯一标识。没有的话框架也能跑，但建议保留便于调试和追溯来源 |
| `image` | string | 是 | 图片的相对路径。训练时框架会在配置中指定图片根目录，然后拼接此路径去读图 |
| `conversations` | array | 是 | 对话列表。每条是一个说话回合，按时间顺序排列 |
| `conversations[].from` | string | 是 | 说话人。取值为 `"human"`（用户）或 `"gpt"`（模型/助手） |
| `conversations[].value` | string | 是 | 说话内容。`human` 的 value 必须以 `<image>\n` 开头，后面跟具体指令 |

### `<image>` 是什么？

`<image>` 是一个**占位符（placeholder）**。

它不是真实图片数据。训练时，框架会把 `<image>` 替换成该张图片经过 ViT 编码后的视觉 token（一串向量）。模型看到这些 token 就知道"这里有一张图"。

```
原始文本：         "<image>\n描述这张遥感图的内容。"
                    ↓  框架处理
模型实际看到的：    [IMG_TOKEN][IMG_TOKEN]...[IMG_TOKEN] 描述这张遥感图的内容。
                    ↑ 图片被 ViT 编码成一串 token
```

> **关键规则**：`<image>` 必须出现在 `human` 的 `value` 字段中，且通常是第一行。`gpt` 的 `value` 里不需要 `<image>`——因为模型要输出的是文字回答，不是图片。

### 一个完整的数据集 JSON 文件

整个数据集是一个**数组**（注意是数组，不是对象），包含多条样本：

```json
[
  {
    "id": "sample_001",
    "image": "images/train/00001.png",
    "conversations": [
      {"from": "human", "value": "<image>\nDescribe this remote sensing image."},
      {"from": "gpt",   "value": "The image shows an airport with a large plane on the tarmac."}
    ]
  },
  {
    "id": "sample_002",
    "image": "images/train/00002.png",
    "conversations": [
      {"from": "human", "value": "<image>\nWhat type of land cover is dominant?"},
      {"from": "gpt",   "value": "The dominant land cover is agricultural fields."}
    ]
  }
]
```

---

## 不同任务在 LLaVA 格式里的写法

虽然底层结构一样，但不同任务的 `human` 和 `gpt` 写法有约定俗成的差异。

### Caption（图像描述）

> 输入 = 一张图 + 描述指令，输出 = 一段描述文字。

```json
{
  "id": "caption_001",
  "image": "airport.png",
  "conversations": [
    {
      "from": "human",
      "value": "<image>\nDescribe this image in detail."
    },
    {
      "from": "gpt",
      "value": "The image captures part of an airport where a large white aircraft is positioned on the tarmac. Surrounding the aircraft are taxiways and a section of grass."
    }
  ]
}
```

### VQA（视觉问答，开放式短答案）

> 输入 = 图 + 问题，输出 = 简短答案。

```json
{
  "id": "vqa_001",
  "image": "airport.png",
  "conversations": [
    {
      "from": "human",
      "value": "<image>\nWhat color is the aircraft in the image?"
    },
    {
      "from": "gpt",
      "value": "White"
    }
  ]
}
```

### VQA（视觉问答，多选题）

> 输入 = 图 + 问题 + 选项，输出 = 正确选项字母。

```json
{
  "id": "vqa_mc_001",
  "image": "remote_sensing/scene.jpg",
  "conversations": [
    {
      "from": "human",
      "value": "<image>\nWhat is the main structure visible?\n(A) Bridge\n(B) Stadium\n(C) Airport terminal\n(D) School"
    },
    {
      "from": "gpt",
      "value": "C"
    }
  ]
}
```

> **注意**：多选题的选项直接写在 `human` 的 `value` 里，用换行分隔。`gpt` 只需回答选项字母。不要写成 JSON 或别的结构，保持纯文本。

### Visual Grounding / Referring（视觉定位 / 指称表达）

> 输入 = 图 + 物体描述，输出 = bounding box 坐标。

```json
{
  "id": "refer_001",
  "image": "airport.png",
  "conversations": [
    {
      "from": "human",
      "value": "<image>\nLocate the white aircraft in the image."
    },
    {
      "from": "gpt",
      "value": "[0.61, 0.40, 0.35, 0.87]"
    }
  ]
}
```

坐标说明：

| 格式 | 示例 | 含义 |
|------|------|------|
| `[x, y, w, h]` 归一化 | `[0.61, 0.40, 0.35, 0.87]` | 框的左上角在水平61%、垂直40%处，宽占35%，高占87% |
| `[xmin, ymin, xmax, ymax]` 归一化 | `[0.61, 0.40, 0.96, 0.87]` | 框从(61%,40%)到(96%,87%) |

> 两种写法社区都有，我们用 `[xmin, ymin, xmax, ymax]` 归一化到 [0,1]，与 EarthDial 和大多数目标检测框架一致。坐标以**原图尺寸**为基准，取值为 0~1 的浮点数。

### Change Captioning（变化描述）

> 输入 = **两张图**（时相A + 时相B），输出 = 变化描述文字。

这是标准 LLaVA 格式的延伸。原版格式只支持单张图（一个 `image` 字段），变化描述需要两张图。

---

## 我们做的微小改动

为了在不破坏 LLaVA 标准兼容性的前提下支持多图、多任务混合训练，我们做了三个微小改动。

---

### 改动一：`image` → `images`

| 维度 | 原版 LLaVA | 我们的版本 | 原因 |
|------|-----------|-----------|------|
| 字段名 | `image`（单数字符串） | `images`（字符串数组） | 变化描述任务需要两张图（时相A+时相B） |
| 类型 | `"image": "path.jpg"` | `"images": ["A.jpg", "B.jpg"]` | 单图任务数组里就一个元素，兼容 |

**为什么这样改**：
- 单图任务（Caption、VQA、Refer）→ `"images": ["图.jpg"]`，数组只有一个元素
- 变化描述任务（Change Captioning、Change Detection）→ `"images": ["时相A.jpg", "时相B.jpg"]`，两个元素
- 数组长度直接告诉模型"有几张图"，不需要额外的元数据字段

> 这个改动**向后兼容**。大多数训练框架读 `image` 字段时会 fallback 到 `images[0]`，或者在数据处理 script 里做一层映射即可。

---

### 改动二：在 `human` 对话中加入 EarthDial 风格 Token 前缀

| 维度 | 原版 LLaVA | 我们的版本 | 原因 |
|------|-----------|-----------|------|
| human value | `<image>\nDescribe this image.` | `<image>\n[optical 512 rgb][caption] Describe this image.` | 让模型知道输入来自什么传感器、什么分辨率、要做什么任务 |

**Token 前缀的结构**：

```
[optical 512 rgb][caption]
  ↑       ↑   ↑    ↑
 传感器  分辨率 波段  任务
```

**为什么这样改**：
- 7 个数据集混在一起训练时，模型需要区分"这张 256×256 的 LEVIR 双时相图要写变化描述"和"这张 7360×7360 的 XLRS 超大图要做视觉定位"
- 把区别直接写进文本里——和 `<image>` 一样放在 human 消息的最前面——模型通过自回归学习自然就能理解这些 token 的含义
- EarthDial 论文验证了这种做法有效，我们的 token 命名规则直接照搬

**Token 取值表**：

| 传感器 | Token | 分辨率 | Token | 波段 | Token | 任务 | Token |
|--------|-------|--------|-------|------|-------|------|-------|
| 光学 RGB | `[optical]` | 256px | `[256]` | RGB | `[rgb]` | 图像描述 | `[caption]` |
| SAR（未来） | `[sar]` | 512px | `[512]` | 灰度 | `[gray]` | 视觉定位 | `[refer]` |
| 多光谱（未来） | `[multi]` | 4096px | `[4096]` | VH极化 | `[vh]` | 视觉问答 | `[vqa]` |
| | | 7360px | `[7360]` | VV极化 | `[vv]` | 变化描述 | `[changecaption]` |
| | | 11500px | `[11500]` | | | 变化检测 | `[changedet]` |
| | | | | | | 复杂推理 | `[reason]` |

---

### 改动三：新增元数据字段

在原版 LLaVA schema（`id` + `image` + `conversations`）之外，我们附加了 6 个字段作为元数据。

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `task` | string | `"caption"` | 任务类型，与 token 前缀中的任务 token 一致 |
| `sensor` | string | `"optical"` | 传感器类型 |
| `resolution` | int | `512` | 图像分辨率（取宽高中的较大值） |
| `bands` | string | `"rgb"` | 波段类型 |
| `split` | string | `"train"` | 数据划分 |
| `language` | string | `"en"` | 标注语言 |
| `source` | string | `"vrsbench"` | 来源数据集名称 |

**为什么加这些**：
- `token` 前缀里的信息是从这些字段生成的，保留原值方便做数据分析（比如统计各任务的数据量是否均衡）
- 训练框架**不会用到**这些字段（它们只看 `images` + `conversations`），不会造成兼容性问题
- 如果未来想按任务类型做加权采样、按语言做分桶训练，直接读这些字段就行，不需要从文本里正则匹配 token 前缀

---

## 改动汇总：Before vs After

### 一个 LEVIR 变化描述样本

**改写前（原始 LEVIR JSON）**：
```json
{
  "filepath": "train",
  "filename": "train_000042.png",
  "imgid": 41,
  "changeflag": 1,
  "split": "train",
  "sentences": [
    {"tokens": ["a", "new", "building", "appears"], "raw": "a new building appears", "imgid": 41, "sentid": 205}
  ]
}
```

**改写后（统一格式）**：
```json
{
  "id": "levir_mci/train/0041",
  "images": ["levir_mci/train_000042.png"],
  "conversations": [
    {
      "from": "human",
      "value": "<image>\n[optical 256 rgb][changecaption] Describe the changes between the two temporal images."
    },
    {
      "from": "gpt",
      "value": "a new building appears"
    }
  ],
  "task": "changecaption",
  "sensor": "optical",
  "resolution": 256,
  "bands": "rgb",
  "split": "train",
  "language": "en",
  "source": "levir_mci"
}
```

### 一个 XLRS 中文视觉定位样本（含大图切分）

**改写前（Arrow 二进制，不可读）**：
```
Arrow Table Row:
  image_width: 7360
  image_height: 4912
  question: "给定一个7360 x 4912像素的卫星图像。请定位图片右下角的蓝色汽车..."
  bbox: [6025.2, 3585.8, 6403.2, 3831.4]
  image: {bytes: <JPEG binary ~3MB>, path: "DOTA_v2_P5729.jpg"}
```

**改写后（统一格式）**：
```json
{
  "id": "xlrs_vg/train/02950",
  "images": [
    "xlrs_vg/DOTA_v2_P5729_r0_c0.jpg",
    "xlrs_vg/DOTA_v2_P5729_r0_c1.jpg",
    "xlrs_vg/DOTA_v2_P5729_r1_c0.jpg",
    "xlrs_vg/DOTA_v2_P5729_r1_c1.jpg"
  ],
  "conversations": [
    {
      "from": "human",
      "value": "<image>\n[optical 7360 rgb][refer] 给定一个7360 x 4912像素的卫星图像。请定位图片右下角的蓝色汽车..."
    },
    {
      "from": "gpt",
      "value": "[0.82, 0.73, 0.87, 0.78]"
    }
  ],
  "task": "refer",
  "sensor": "optical",
  "resolution": 7360,
  "bands": "rgb",
  "split": "train",
  "language": "zh",
  "source": "xlrs_vg"
}
```

> **注意**：原图 7360×4912，被切成了多个 448×448 的 tile（示例里只画了 4 个，实际可能几十上百个），每个 tile 作为独立的图片文件，路径按 `{原名}_r{行}_c{列}.jpg` 规则命名。坐标 `[0.82, 0.73, 0.87, 0.78]` 已经归一化到 [0,1]，以**原图尺寸**为基准。

---

## 一条样本从生到死

```
数据集原始格式 ──[convert脚本]──→ 统一 JSON ──[训练框架读取]──→ 模型

LEVIR JSON        →               {
Arrow 二进制      →   convert       "images": [...],
LLaVA JSON        →   脚本群        "conversations": [
多选题 JSON       →                  {"from":"human","value":"<image>\n[token] ..."},
                                     {"from":"gpt","value":"..."}
                                   ],
                                   "task": "...",
                                   ...
                                 }

                                 训练框架：
                                 1. 读 JSON
                                 2. 从 images 路径加载图片
                                 3. ViT 编码图片 → visual tokens
                                 4. 替换 <image> → visual tokens
                                 5. 拼接 human + gpt → 完整序列
                                 6. 对 gpt 部分计算 loss，做梯度下降
```

---

## 常见疑问

### Q: 为什么 `<image>` 要放在 human 消息里而不是单独成一个字段？

因为多模态大模型的本质是**"把图片当外语翻译成文字"**。`<image>` 这个占位符在训练时会变成一串视觉 token，模型在自回归生成时看到它们就知道上下文里有一张图。放在文本流里是最自然的方式——模型不需要额外的架构改动。

### Q: 多图怎么办？可以放两个 `<image>` 吗？

社区有多种做法：
- LLaVA-NeXT 用 `<image>` 的数量对应图片数量
- Qwen-VL 用 `<img>path.jpg</img>` 标签

我们的做法：`images` 数组长度 = 图片数量，`human` 消息里放一个 `<image>` 代表"这里有图"。训练框架负责把 `images[0]`、`images[1]`……依次编码并拼接。这是最简单的方案，不需要发明新的 token 语法。

### Q: `<image>\n` 后面的 `\n` 是必须的吗？

是的。`\n`（换行符）把图片占位符和文字指令分开，让 tokenizer 能正确分词。不加的话 `<image>Describe...` 可能被当成一个 token 处理，影响训练稳定性。

### Q: 我们的格式能被 LLaMA-Factory 直接用吗？

几乎可以。LLaMA-Factory 默认读 `image`（单数）字段。我们需要在 dataset 注册脚本里做两件事：
1. 把 `images` 数组映射到框架期望的图片列表接口
2. 让框架知道可能有多个 `<image>` 占位符

这在 LLaMA-Factory 的 `dataset_info.json` 里配一个自定义 `dataset` 条目就能解决，不需要改源码。

### Q: 元数据字段能不能不要？

可以。如果只用 LLaMA-Factory，它只看 `images` + `conversations`，多余的字段会被忽略。我们保留元数据是为了方便后续做数据分析和平衡采样，不影响训练。

---

## 参考资料

- LLaVA 原始论文：https://llava-vl.github.io/
- LLaMA-Factory 数据集格式文档：https://github.com/hiyouga/LLaMA-Factory
- EarthDial 论文：`reference & PPT/EarthDial.pdf`
- VRSBench（标准 LLaVA 格式的遥感数据集）：`dataset/VRSBench/VRSBench_train.json`
