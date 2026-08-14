"""独立 transformers OCR 子进程入口，由 vLLM 环境的 Python 调用。"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    """在独立解释器里跑一次整图识别。

    参数：
        argv: 命令行；`--prompt` 默认 `OCR:`，`--max-new-tokens` 默认 512。

    返回：
        进程退出码；成功时向 stdout 打印 `{"text": ...}`。
    """
    parser = argparse.ArgumentParser(description="PaddleOCR-VL transformers fallback")
    parser.add_argument("--model", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--prompt", default="OCR:")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    args = parser.parse_args(argv)
    try:
        import torch
        from PIL import Image
        from transformers import AutoModelForImageTextToText, AutoProcessor

        image = Image.open(args.image).convert("RGB")
        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        dtype = torch.bfloat16 if device != "cpu" else torch.float32
        model = (
            AutoModelForImageTextToText.from_pretrained(
                args.model, torch_dtype=dtype, trust_remote_code=True
            )
            .to(device)
            .eval()
        )
        processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": args.prompt},
                ],
            }
        ]
        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(model.device)
        outputs = model.generate(**inputs, max_new_tokens=args.max_new_tokens)
        text = processor.decode(outputs[0][inputs["input_ids"].shape[-1] : -1])
        print(json.dumps({"text": text}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
