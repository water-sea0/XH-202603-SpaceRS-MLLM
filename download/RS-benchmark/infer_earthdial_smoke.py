#!/usr/bin/env python3
"""
EarthDial_4B_RGB inference on RS-VL smoke_val benchmark.
Reads exports/earthdial/smoke_val.jsonl, runs model.chat(), writes results in same format.
"""

import os, sys, json, time
from pathlib import Path
from datetime import datetime

# EarthDial source path
sys.path.insert(0, "/root/autodl-tmp/earthdial_code/src")

import torch
from PIL import Image
import torchvision.transforms as T
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoTokenizer
from earthdial.model.internvl_chat import InternVLChatModel

# ── Config ──────────────────────────────────────────
MODEL_PATH = "/root/autodl-tmp/models/EarthDial_4B_RGB"
BUNDLE_ROOT = "/root/autodl-tmp/rs_vl_bundle_20g"
INPUT_FILE = os.path.join(BUNDLE_ROOT, "exports", "earthdial", "smoke_val.jsonl")
OUTPUT_DIR = "/root/autodl-tmp/RS-benchmark"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "earthdial_smoke_val_results.jsonl")

# EarthDial inference constants (from existing benchmark)
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def build_transform(input_size: int):
    return T.Compose([
        T.Lambda(lambda img: img.convert('RGB') if img.mode != 'RGB' else img),
        T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def load_model():
    print(f"Loading model from {MODEL_PATH} ...")
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True, use_fast=False)
    model = InternVLChatModel.from_pretrained(
        MODEL_PATH,
        low_cpu_mem_usage=True,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="eager",
    ).eval()
    load_time = time.time() - t0
    print(f"Model loaded in {load_time:.1f}s")
    print(f"VRAM: {torch.cuda.memory_allocated()/1024**3:.1f} GB")
    return model, tokenizer


def run_inference(model, tokenizer):
    image_size = model.config.force_image_size or model.config.vision_config.image_size
    transform = build_transform(input_size=image_size)
    print(f"Image size: {image_size}")

    # Read all samples
    samples = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    print(f"Loaded {len(samples)} samples from {INPUT_FILE}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    n_total = len(samples)
    t_start = time.time()
    n_tokens_total = 0

    for idx, sample in enumerate(samples):
        try:
            # Extract human question
            human_msg = next(c["value"] for c in sample["conversations"] if c["from"] == "human")

            # Load and preprocess images
            pixel_values_list = []
            for img_rel_path in sample["images"]:
                img_abs_path = os.path.join(BUNDLE_ROOT, img_rel_path)
                img = Image.open(img_abs_path)
                pv = transform(img).unsqueeze(0).to(torch.bfloat16).cuda()
                pixel_values_list.append(pv)

            pixel_values = torch.cat(pixel_values_list, dim=0)  # [N, C, H, W]

            # Inference
            generation_config = {
                "num_beams": 1,
                "max_new_tokens": 256,
                "do_sample": False,
            }
            t0 = time.time()
            with torch.no_grad():
                answer = model.chat(
                    tokenizer=tokenizer,
                    pixel_values=pixel_values,
                    question=human_msg,
                    generation_config=generation_config,
                )
            elapsed = time.time() - t0

            n_tokens_est = len(answer) // 4  # rough estimate
            n_tokens_total += n_tokens_est

            # Build result in same format, replacing gpt response with model answer
            result = {
                "id": sample["id"],
                "images": sample["images"],
                "conversations": [
                    {"from": "human", "value": human_msg},
                    {"from": "gpt", "value": answer},
                ],
                "task": sample["task"],
                "source": sample["source"],
                "bundle_split": sample["bundle_split"],
                "_inference": {
                    "model": "EarthDial_4B_RGB",
                    "time_s": round(elapsed, 3),
                    "tokens_est": int(n_tokens_est),
                },
            }
            results.append(result)

            if (idx + 1) % 50 == 0 or idx == 0:
                elapsed_total = time.time() - t_start
                rate = (idx + 1) / elapsed_total
                eta = (n_total - idx - 1) / rate if rate > 0 else 0
                print(f"[{idx+1}/{n_total}] {elapsed_total:.0f}s elapsed | "
                      f"{rate:.2f} samples/s | ETA {eta/60:.1f}min | "
                      f"last: {elapsed:.2f}s '{answer[:60]}...'")
                # Save checkpoint
                ckpt_path = os.path.join(OUTPUT_DIR, "earthdial_smoke_val_ckpt.jsonl")
                with open(ckpt_path, "w", encoding="utf-8") as fout:
                    for r in results:
                        fout.write(json.dumps(r, ensure_ascii=False) + "\n")

            # Cleanup
            del pixel_values, pixel_values_list
            torch.cuda.empty_cache()

        except Exception as e:
            print(f"ERROR [{idx}] {sample.get('id','?')}: {e}")
            result = {
                "id": sample.get("id", "?"),
                "images": sample.get("images", []),
                "conversations": [
                    {"from": "human", "value": ""},
                    {"from": "gpt", "value": f"__ERROR__: {str(e)}"},
                ],
                "task": sample.get("task", "?"),
                "source": sample.get("source", "?"),
                "bundle_split": sample.get("bundle_split", "?"),
                "_inference": {"model": "EarthDial_4B_RGB", "error": str(e)},
            }
            results.append(result)
            continue

    # Final save
    total_time = time.time() - t_start
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fout:
        for r in results:
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"EarthDial smoke_val benchmark complete!")
    print(f"  Total: {n_total} samples, {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"  Avg: {total_time/n_total:.2f}s/sample")
    print(f"  Output: {OUTPUT_FILE}")


def main():
    model, tokenizer = load_model()
    run_inference(model, tokenizer)


if __name__ == "__main__":
    main()
