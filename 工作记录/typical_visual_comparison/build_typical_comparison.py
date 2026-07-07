from __future__ import annotations

import base64
import html
import io
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
BUNDLE = WORKSPACE / "dataset" / "_derived" / "rs_vl_bundle_20g"
CANONICAL = BUNDLE / "manifests" / "smoke_val.jsonl"
QWEN = HERE / "qwen_smoke_val_results_v2.jsonl"
EARTH = HERE / "earthdial_smoke_val_results.jsonl"
OUTPUT = HERE / "TYPICAL_VISUAL_COMPARISON.html"
MARKDOWN_OUTPUT = HERE / "TYPICAL_VISUAL_COMPARISON.md"
ASSET_DIR = HERE / "typical_visual_assets"

Image.MAX_IMAGE_PIXELS = 250_000_000

SELECTIONS = [
    {
        "id": "levir/train/train_000251/change_captioning",
        "label": "LEVIR-MCI · 变化描述",
        "verdict": "无变化样本：EarthDial 命中参考；Qwen 把纹理差异解释成视角变化。",
        "q_class": "bad",
        "e_class": "good",
    },
    {
        "id": "levir/train/train_000461/change_detection",
        "label": "LEVIR-MCI · 变化检测",
        "verdict": "新增房屋样本：两者都回答 no_change，是一个简洁但重要的共同失败例。",
        "q_class": "bad",
        "e_class": "bad",
    },
    {
        "id": "vrsbench/train/001554",
        "label": "VRSBench · 图像描述",
        "verdict": "EarthDial 识别出右下方大型船只；Qwen 将场景误判为隧道或桥梁。",
        "q_class": "bad",
        "e_class": "good",
    },
    {
        "id": "vrsbench/train/003711",
        "label": "VRSBench · 视觉定位",
        "verdict": "EarthDial 给出接近参考框的坐标；Qwen 只作文字解释，没有按要求输出框。",
        "q_class": "bad",
        "e_class": "good",
    },
    {
        "id": "vrsbench/train/001453",
        "label": "VRSBench · VQA",
        "verdict": "参考答案为 yes：EarthDial 正确，Qwen 对车站屋顶颜色判断错误。",
        "q_class": "bad",
        "e_class": "good",
    },
    {
        "id": "xlrs_caption_zh/train/data-00001-of-00023/00011",
        "label": "XLRS 中文描述 · 图像描述",
        "verdict": "4096² 大图：Qwen 直接 OOM；EarthDial 完成推理，但输出偏目标计数而非整体场景描述。",
        "q_class": "oom",
        "e_class": "warn",
    },
    {
        "id": "xlrs_grounding_zh/train/f777b5b99518e06dd699",
        "label": "XLRS 中文定位 · 视觉定位",
        "verdict": "7360×4912 大图：Qwen OOM；EarthDial 能返回框，但与参考湖泊位置明显不符。",
        "q_class": "oom",
        "e_class": "bad",
    },
]


def load_jsonl(path: Path) -> dict[str, dict]:
    values = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            value = json.loads(line)
            values[value["id"]] = value
    return values


def qwen_answer(value: dict) -> str:
    try:
        return str(value["messages"][-1]["content"][0]["text"])
    except (KeyError, IndexError, TypeError):
        return "（无输出）"


def earth_answer(value: dict) -> str:
    try:
        return str(value["conversations"][-1]["value"])
    except (KeyError, IndexError, TypeError):
        return "（无输出）"


def compact(text: str, limit: int = 250) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def reference_text(record: dict) -> str:
    target = record["target"]
    if "texts" in target:
        return compact(str(target["texts"][0]))
    if "class_label" in target:
        return str(target["class_label"])
    if "answer" in target:
        return str(target["answer"])
    if "boxes" in target:
        box = target["boxes"][0]["xyxy"]
        return "GT 框：" + str([round(float(v) * 100, 1) for v in box]) + "（0–100）"
    return compact(json.dumps(target, ensure_ascii=False))


def parse_earth_box(text: str) -> list[float] | None:
    match = re.search(
        r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*"
        r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
        text,
    )
    if not match:
        return None
    return [float(value) / 100.0 for value in match.groups()]


def open_media(record: dict) -> list[Image.Image]:
    images = []
    for media in record["media"]:
        path = BUNDLE / Path(media["locator"]["path"])
        with Image.open(path) as source:
            images.append(source.convert("RGB"))
    return images


def draw_normalized_box(draw: ImageDraw.ImageDraw, size: tuple[int, int], box: list[float], color: str, width: int) -> None:
    w, h = size
    xy = [box[0] * w, box[1] * h, box[2] * w, box[3] * h]
    draw.rectangle(xy, outline=color, width=width)


def visual_data_uri(record: dict, earth_text: str) -> str:
    images = open_media(record)
    if len(images) == 2:
        panels = []
        for index, image in enumerate(images, 1):
            image.thumbnail((520, 520), Image.Resampling.LANCZOS)
            panel = Image.new("RGB", (image.width, image.height + 28), "#10151c")
            panel.paste(image, (0, 28))
            ImageDraw.Draw(panel).text((10, 7), f"T{index}", fill="white")
            panels.append(panel)
        canvas = Image.new("RGB", (sum(p.width for p in panels) + 8, max(p.height for p in panels)), "#0a0e13")
        x = 0
        for panel in panels:
            canvas.paste(panel, (x, 0))
            x += panel.width + 8
    else:
        canvas = images[0]
        canvas.thumbnail((1100, 720), Image.Resampling.LANCZOS)
        if record["task"] == "visual_grounding":
            draw = ImageDraw.Draw(canvas)
            gt = [float(value) for value in record["target"]["boxes"][0]["xyxy"]]
            ed = parse_earth_box(earth_text)
            line = max(3, round(min(canvas.size) / 160))
            draw_normalized_box(draw, canvas.size, gt, "#2dd4bf", line)
            if ed:
                draw_normalized_box(draw, canvas.size, ed, "#fb923c", line)
            draw.rectangle((8, 8, 370, 39), fill="#0b111bcc")
            draw.text((16, 15), "GT: cyan    EarthDial: orange", fill="white")
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=84, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def escaped(text: str) -> str:
    return html.escape(text, quote=True)


def build() -> None:
    canonical = load_jsonl(CANONICAL)
    qwen = load_jsonl(QWEN)
    earth = load_jsonl(EARTH)
    cards = []
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    markdown = [
        "# RS-VL 典型样例极简对比\n",
        "EarthDial_4B_RGB 与 Qwen2.5-VL-7B-Instruct 在 `smoke_val` 上的对比。每个现有“数据集 × 任务”组合选取 1 个典型案例；当前结果不含 MME-RS 与 XLRS-lite。定位图中青框为参考，橙框为 EarthDial。\n",
        "## 用自然语言理解统计结果\n",
        "两者最确定的差异是**运行稳定性**。在同一批 889 个样本上，EarthDial 完成了全部样本，Qwen 完成 753 个（84.7%），其余 136 个均因大尺寸 XLRS 图像触发 OOM。按同一样本配对比较，这一完成率差异极显著（精确配对二项检验，`p≈2.3×10⁻⁴¹`）。因此可以相当有把握地说：在当前硬件、当前预处理和当前推理参数下，EarthDial 对超大遥感图像明显更稳；这个结论不等于换显存或限制 Qwen 视觉 token 后仍会保持同样差距。\n",
        "在**变化检测**的 40 个样本上，如果严格要求只输出 `change` 或 `no_change`，Qwen 正确 29 个（72.5%），EarthDial 正确 24 个（60.0%）。配对差异不显著（`p=0.359`），样本量也较小，所以不能据此断言某一个模型更准。EarthDial 有时会描述具体变化而没有返回规定标签，这会被严格匹配判错；这里同时测到了识别能力与指令遵循。\n",
        "在 **VQA** 的 428 个样本上，严格字符串匹配时 EarthDial 为 91/428（21.3%），Qwen 为 25/428（5.8%），配对差异显著（`p≈4.3×10⁻¹⁴`）。但把标准放宽为“输出中连续包含参考答案词组”后，EarthDial 为 197/428（46.0%），Qwen 为 174/428（40.7%），差异只到临界水平（`p=0.052`）。这说明 EarthDial 的严格匹配优势有很大一部分来自回答短、格式直接；Qwen 经常给出较长解释，使自动精确匹配吃亏。若要判断真正的语义正确率，还需要人工复核或专门的答案判分器。\n",
        "在**视觉定位**的 219 个样本上，Qwen 没有产生任何可解析的四坐标框：95 个 VRSBench 样本主要返回自然语言，124 个 XLRS 样本则全部 OOM。EarthDial 有 197/219（90.0%）能解析出框，因此在接口可用性上明显占优；但只有 14 个样本达到 `IoU≥0.5`，可解析框的平均 IoU 仅 0.099。这意味着“能稳定输出框”并不等于“框得准”，EarthDial 的定位精度仍有很大提升空间。\n",
        "对**图像描述和变化描述**，当前结果只能稳妥比较完成率和输出风格，不能仅凭字数判断语义质量。Qwen 的平均输出明显更长：变化描述约 217 字符对 EarthDial 的 43 字符，普通图像描述约 692 对 217 字符。Qwen 往往更丰富，也更容易添加错误细节；EarthDial 更简洁、偏目标计数。大图中文描述中 Qwen 12/12 OOM，而 EarthDial 12/12 完成。没有 BLEU、CIDEr、BERTScore 或人工评分前，不宜声称谁的描述质量在统计上更高。\n",
        "> 以上显著性检验都利用同一样本上的配对结果；文本指标是可复核的自动近似，不是完整语义评价。推理速度由于两模型运行条件不完全一致，未进行显著性比较。\n",
        "## 典型案例\n",
    ]
    for index, selection in enumerate(SELECTIONS, 1):
        sample_id = selection["id"]
        record = canonical[sample_id]
        q_text = qwen_answer(qwen[sample_id])
        e_text = earth_answer(earth[sample_id])
        image_uri = visual_data_uri(record, e_text)
        asset_name = f"{index:02d}_{record['source']}_{record['task']}.jpg"
        asset_path = ASSET_DIR / asset_name
        asset_path.write_bytes(base64.b64decode(image_uri.split(",", 1)[1]))
        dims = " + ".join(f"{m['width']}×{m['height']}" for m in record["media"])
        cards.append(
            f"""
            <article class="card">
              <div class="head"><span class="num">{index:02d}</span><div><h2>{escaped(selection['label'])}</h2><p>{escaped(dims)}</p></div></div>
              <img class="visual" src="{image_uri}" alt="{escaped(selection['label'])}">
              <p class="prompt"><b>问题</b> {escaped(compact(re.sub(r'<[^>]+>', '', record['prompt']), 180))}</p>
              <div class="answers">
                <div class="answer ref"><b>参考</b><span>{escaped(reference_text(record))}</span></div>
                <div class="answer {selection['e_class']}"><b>EarthDial</b><span>{escaped(compact(e_text))}</span></div>
                <div class="answer {selection['q_class']}"><b>Qwen2.5-VL</b><span>{escaped(compact(q_text))}</span></div>
              </div>
              <p class="verdict">{escaped(selection['verdict'])}</p>
              <code>{escaped(sample_id)}</code>
            </article>
            """
        )
        markdown.extend(
            [
                f"### {index:02d}｜{selection['label']}\n",
                f"![{selection['label']}](typical_visual_assets/{asset_name})\n",
                f"- **尺寸**：{dims}",
                f"- **问题**：{compact(re.sub(r'<[^>]+>', '', record['prompt']), 180)}",
                f"- **参考**：{reference_text(record)}",
                f"- **EarthDial**：{compact(e_text)}",
                f"- **Qwen2.5-VL**：{compact(q_text)}",
                f"- **观察**：{selection['verdict']}",
                f"- **样本 ID**：`{sample_id}`\n",
            ]
        )

    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RS-VL 典型样例极简对比</title>
<style>
:root{{--bg:#f4f6f8;--paper:#fff;--ink:#15202b;--muted:#65707d;--line:#dfe5ea;--good:#087f5b;--bad:#c92a2a;--warn:#b26a00;--oom:#7c3aed}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:1080px;margin:auto;padding:42px 24px 70px}} h1{{font-size:30px;margin:0 0 8px}} .intro{{color:var(--muted);margin:0 0 28px}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 24px;font-size:13px}} .legend span{{padding:4px 9px;background:white;border:1px solid var(--line);border-radius:99px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}} .card{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 4px 18px #1824310d}}
.head{{display:flex;gap:10px;align-items:center;margin-bottom:12px}} .num{{font:700 12px/1 monospace;color:white;background:#263544;border-radius:6px;padding:7px}} h2{{font-size:17px;margin:0}} .head p{{font-size:12px;color:var(--muted);margin:1px 0 0}}
.visual{{display:block;width:100%;height:270px;object-fit:contain;background:#0b1016;border-radius:8px}} .prompt{{font-size:13px;margin:12px 0 10px;color:#36414c}}
.answers{{display:grid;gap:7px}} .answer{{border-left:4px solid #64748b;background:#f7f9fb;padding:8px 10px;border-radius:4px}} .answer b{{display:block;font-size:12px;margin-bottom:2px}} .answer span{{display:block;font-size:13px}}
.answer.good{{border-color:var(--good)}} .answer.bad{{border-color:var(--bad)}} .answer.warn{{border-color:var(--warn)}} .answer.oom{{border-color:var(--oom)}}
.verdict{{font-weight:650;margin:11px 0 5px}} code{{font-size:11px;color:var(--muted);overflow-wrap:anywhere}} footer{{margin-top:28px;color:var(--muted);font-size:12px}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}} .visual{{height:auto;max-height:420px}} main{{padding:24px 14px 50px}}}}
@media print{{body{{background:white}} main{{max-width:none;padding:10mm}} .card{{break-inside:avoid;box-shadow:none}}}}
</style></head><body><main>
<h1>RS-VL 典型样例极简对比</h1>
<p class="intro">EarthDial_4B_RGB vs Qwen2.5-VL-7B-Instruct｜smoke_val｜每个现有“数据集 × 任务”组合 1 例。青框为参考，橙框为 EarthDial。当前结果不含 MME-RS 与 XLRS-lite，因此未列入。</p>
<div class="legend"><span>绿色边：较好</span><span>红色边：错误/未遵循格式</span><span>黄色边：完成但偏题</span><span>紫色边：OOM</span></div>
<section class="grid">{''.join(cards)}</section>
<footer>来源：qwen_smoke_val_results_v2.jsonl、earthdial_smoke_val_results.jsonl 与 RS-VL canonical smoke_val。页面内图片均为压缩预览，原始媒体未修改。</footer>
</main></body></html>"""
    OUTPUT.write_text(page, encoding="utf-8")
    MARKDOWN_OUTPUT.write_text("\n".join(markdown), encoding="utf-8")
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
    print(f"wrote {MARKDOWN_OUTPUT} ({MARKDOWN_OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
