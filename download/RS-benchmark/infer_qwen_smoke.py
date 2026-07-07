#!/usr/bin/env python3
"""
Qwen2.5-VL-7B-Instruct inference on RS-VL smoke_val benchmark.
Reads exports/qwen/smoke_val.jsonl, runs model.generate(), writes results in same format.
"""

import os, sys, json, time
from datetime import datetime

import torch
from PIL import Image
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor

# ── Config ──────────────────────────────────────────
MODEL_PATH = "/root/models/Qwen2.5-VL-7B-Instruct"
BUNDLE_ROOT = "/root/autodl-tmp/rs_vl_bundle_20g"
INPUT_FILE = os.path.join(BUNDLE_ROOT, "exports", "qwen", "smoke_val.jsonl")
OUTPUT_DIR = "/root/autodl-tmp/RS-benchmark"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "qwen_smoke_val_results.jsonl")


def load_model():
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
    load_time = time.time() - t0
    print(f"Model loaded in {load_time:.1f}s")
    print(f"VRAM: {torch.cuda.memory_allocated()/1024**3:.1f} GB")
    return model, processor


def run_inference(model, processor):
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
            # Build messages with loaded PIL images
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

            # Filter to user messages only for inference
            user_messages = [m for m in messages if m["role"] == "user"]

            # Preprocess
            text = processor.apply_chat_template(
                user_messages, tokenize=False, add_generation_prompt=True
            )
            # Extract PIL images from user content
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

            # Inference
            t0 = time.time()
            with torch.no_grad():
                generated_ids = model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                )

            # Decode
            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_text = processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]
            elapsed = time.time() - t0

            n_tokens = int(generated_ids_trimmed[0].shape[0])
            n_tokens_total += n_tokens

            # Build result in same format, replacing assistant answer
            result = {
                "id": sample["id"],
                "messages": [
                    m for m in sample["messages"] if m["role"] == "user"
                ] + [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": output_text}],
                    }
                ],
                "task": sample["task"],
                "source": sample["source"],
                "bundle_split": sample["bundle_split"],
                "_inference": {
                    "model": "Qwen2.5-VL-7B-Instruct",
                    "time_s": round(elapsed, 3),
                    "tokens": n_tokens,
                },
            }
            results.append(result)

            if (idx + 1) % 50 == 0 or idx == 0:
                elapsed_total = time.time() - t_start
                rate = (idx + 1) / elapsed_total
                eta = (n_total - idx - 1) / rate if rate > 0 else 0
                print(f"[{idx+1}/{n_total}] {elapsed_total:.0f}s elapsed | "
                      f"{rate:.2f} samples/s | ETA {eta/60:.1f}min | "
                      f"last: {elapsed:.2f}s {n_tokens}tok '{output_text[:60]}...'")
                # Save checkpoint
                ckpt_path = os.path.join(OUTPUT_DIR, "qwen_smoke_val_ckpt.jsonl")
                with open(ckpt_path, "w", encoding="utf-8") as fout:
                    for r in results:
                        fout.write(json.dumps(r, ensure_ascii=False) + "\n")

            # Cleanup
            del inputs, generated_ids, generated_ids_trimmed
            torch.cuda.empty_cache()

        except Exception as e:
            print(f"ERROR [{idx}] {sample.get('id','?')}: {e}")
            import traceback
            traceback.print_exc()
            result = {
                "id": sample.get("id", "?"),
                "messages": [
                    {"role": "assistant", "content": [{"type": "text", "text": f"__ERROR__: {str(e)}"}]},
                ],
                "task": sample.get("task", "?"),
                "source": sample.get("source", "?"),
                "bundle_split": sample.get("bundle_split", "?"),
                "_inference": {"model": "Qwen2.5-VL-7B-Instruct", "error": str(e)},
            }
            results.append(result)
            continue

    # Final save
    total_time = time.time() - t_start
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fout:
        for r in results:
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"Qwen2.5-VL smoke_val benchmark complete!")
    print(f"  Total: {n_total} samples, {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"  Avg: {total_time/n_total:.2f}s/sample")
    print(f"  Output: {OUTPUT_FILE}")


def main():
    model, processor = load_model()
    run_inference(model, processor)


if __name__ == "__main__":
    main()
