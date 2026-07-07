#!/usr/bin/env python3
"""Retry Qwen on previously OOM-failed smoke_val samples, running solo."""
import json, os, sys, time
from pathlib import Path

import torch
from PIL import Image
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

MODEL_PATH = "/root/models/Qwen2.5-VL-7B-Instruct"
BUNDLE_ROOT = "/root/autodl-tmp/rs_vl_bundle_20g"
INPUT_FILE = os.path.join(BUNDLE_ROOT, "exports", "qwen", "smoke_val.jsonl")
RESULTS_FILE = "/root/autodl-tmp/RS-benchmark/qwen_smoke_val_results.jsonl"
FAILED_IDS_FILE = "/root/autodl-tmp/RS-benchmark/qwen_failed_ids.txt"
OUTPUT_FILE = "/root/autodl-tmp/RS-benchmark/qwen_smoke_val_results_v2.jsonl"

# Load failed IDs
with open(FAILED_IDS_FILE) as f:
    failed_ids = set(line.strip() for line in f if line.strip())
print(f"Retrying {len(failed_ids)} failed samples")

# Load original smoke_val samples (just the failed ones)
all_samples = {}
with open(INPUT_FILE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d["id"] in failed_ids:
            all_samples[d["id"]] = d

print(f"Matched {len(all_samples)} samples from input")

# Load model
print(f"Loading model from {MODEL_PATH} ...")
t0 = time.time()
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    attn_implementation="eager",
)
processor = AutoProcessor.from_pretrained(MODEL_PATH)
model.eval()
print(f"Model loaded in {time.time()-t0:.1f}s, VRAM: {torch.cuda.memory_allocated()/1e9:.2f} GB")

# Load existing results
existing_results = []
with open(RESULTS_FILE) as f:
    for line in f:
        line = line.strip()
        if line:
            existing_results.append(json.loads(line))

# Build index of existing results by ID (keep non-failed ones)
result_by_id = {}
for r in existing_results:
    rid = r["id"]
    meta = r.get("_inference", {})
    if "error" not in meta:
        result_by_id[rid] = r  # keep successful ones

print(f"Keeping {len(result_by_id)} previously successful results")

# Run inference on failed samples
retry_list = [(eid, all_samples[eid]) for eid in failed_ids if eid in all_samples]
n_total = len(retry_list)
t_start = time.time()
success = 0
still_failed = 0

for idx, (eid, sample) in enumerate(retry_list):
    try:
        # Build messages from original sample
        messages = []
        for msg in sample["messages"]:
            new_msg = {"role": msg["role"]}
            if isinstance(msg["content"], list):
                new_content = []
                for item in msg["content"]:
                    if item["type"] == "image":
                        img_abs_path = os.path.join(BUNDLE_ROOT, item["image"])
                        pil_img = Image.open(img_abs_path).convert("RGB")
                        new_content.append({"type": "image", "image": pil_img})
                    elif item["type"] == "text":
                        new_content.append({"type": "text", "text": item["text"]})
                new_msg["content"] = new_content
            else:
                new_msg["content"] = msg["content"]
            messages.append(new_msg)

        user_messages = [m for m in messages if m["role"] == "user"]

        text = processor.apply_chat_template(
            user_messages, tokenize=False, add_generation_prompt=True
        )
        images = []
        for m in user_messages:
            if isinstance(m.get("content"), list):
                for item in m["content"]:
                    if item["type"] == "image":
                        images.append(item["image"])

        inputs = processor(
            text=[text], images=images if images else None,
            return_tensors="pt", padding=True
        ).to("cuda")

        t1 = time.time()
        with torch.no_grad():
            generated_ids = model.generate(
                **inputs, max_new_tokens=256, do_sample=False,
            )
        elapsed = time.time() - t1

        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        n_tokens = int(generated_ids_trimmed[0].shape[0])

        result = {
            "id": eid,
            "messages": [
                m for m in sample["messages"] if m["role"] == "user"
            ] + [
                {"role": "assistant", "content": [{"type": "text", "text": output_text}]},
            ],
            "task": sample["task"],
            "source": sample["source"],
            "bundle_split": sample["bundle_split"],
            "_inference": {
                "model": "Qwen2.5-VL-7B-Instruct",
                "time_s": round(elapsed, 3),
                "tokens": n_tokens,
                "retry": True,
            },
        }
        result_by_id[eid] = result
        success += 1

        if (idx + 1) % 10 == 0 or idx == 0:
            elapsed_tot = time.time() - t_start
            rate = (idx + 1) / elapsed_tot
            eta = (n_total - idx - 1) / rate if rate > 0 else 0
            print(f"[{idx+1}/{n_total}] {elapsed_tot:.0f}s | {rate:.2f}/s | ETA {eta:.0f}s | last: {elapsed:.2f}s")

        del inputs, generated_ids, generated_ids_trimmed
        torch.cuda.empty_cache()

    except Exception as e:
        print(f"STILL FAILED [{idx}] {eid}: {e}")
        # Keep old result with error
        for r in existing_results:
            if r["id"] == eid:
                result_by_id[eid] = r
                break
        still_failed += 1

total_time = time.time() - t_start
print(f"\n{'='*60}")
print(f"Retry complete: {success} succeeded, {still_failed} still failed")
print(f"Total: {total_time:.1f}s")

# Write final merged results in original order
final_ids_order = [r["id"] for r in existing_results]
with open(OUTPUT_FILE, "w") as fout:
    for eid in final_ids_order:
        r = result_by_id.get(eid, {"id": eid, "_inference": {"error": "missing"}})
        fout.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"Final results: {OUTPUT_FILE} ({len(final_ids_order)} entries)")
print("Done!")
