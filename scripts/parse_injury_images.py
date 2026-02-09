#!/usr/bin/env python3
"""
从 data/todays_injuries 下的伤停/比赛列表图片中识别文字，输出到控制台或文本文件。
供人工校对后整理为 CSV（all_today.csv、todays_matches.csv）。

依赖（可选）：pip install easyocr
- 未安装时提示安装，不执行 OCR。
- 表格类图片识别结果可能需人工校对与结构化。
"""
from pathlib import Path
import os
import sys
import ssl

# 抑制 easyocr/torch 下载与识别时的刷屏进度条
os.environ["TQDM_DISABLE"] = "1"

# 部分环境下首次运行 easyocr 会下载检测模型，若遇 SSL 证书校验失败则使用不验证上下文
if getattr(ssl, "_create_default_https_context", None) is not None:
    ssl._create_default_https_context = ssl._create_unverified_context

ROOT = Path(__file__).resolve().parent.parent
INJURIES_DIR = ROOT / "data" / "todays_injuries"


def _run_ocr_on_image(img_path: Path) -> list[tuple[list, str]]:
    """对单张图片做 OCR，返回 easyocr 的 list of (bbox, text)。"""
    try:
        import easyocr
    except ImportError:
        print("未安装 easyocr。请运行: pip install easyocr", file=sys.stderr)
        sys.exit(1)
    with open(os.devnull, "w") as devnull:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = devnull
        try:
            reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            result = reader.readtext(str(img_path))
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    return result


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="对 todays_injuries 目录下图片做 OCR，输出识别文字")
    p.add_argument("--dir", type=Path, default=INJURIES_DIR, help="图片目录")
    p.add_argument("--out", type=Path, default=None, help="将每张图的识别结果写入该目录下的 .txt 文件")
    p.add_argument("--image", type=Path, default=None, help="仅处理指定图片")
    p.add_argument("--quiet", action="store_true", help="仅输出成功/失败，不输出识别文字")
    args = p.parse_args()

    dir_path = Path(args.dir)
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"目录不存在: {dir_path}", file=sys.stderr)
        sys.exit(1)

    if args.image is not None:
        images = [Path(args.image)]
        if not images[0].exists():
            print(f"文件不存在: {images[0]}", file=sys.stderr)
            sys.exit(1)
    else:
        images = sorted(dir_path.glob("*.png")) + sorted(dir_path.glob("*.jpg"))
    if not images:
        print(f"未在 {dir_path} 下找到 .png/.jpg 图片。", file=sys.stderr)
        sys.exit(0)

    out_dir = Path(args.out) if args.out else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    for img_path in images:
        if args.quiet:
            try:
                raw = _run_ocr_on_image(img_path)
                lines = [t[1] for t in raw]
                text = "\n".join(lines)
                if out_dir is not None:
                    out_file = out_dir / f"{img_path.stem}.txt"
                    out_file.write_text(text, encoding="utf-8")
                print(f"{img_path.name}: 识别成功")
            except Exception as e:
                failed += 1
                print(f"{img_path.name}: 识别失败 - {e}", file=sys.stderr)
        else:
            print(f"\n--- {img_path.name} ---")
            try:
                raw = _run_ocr_on_image(img_path)
                lines = [t[1] for t in raw]
                text = "\n".join(lines)
                print(text)
                if out_dir is not None:
                    out_file = out_dir / f"{img_path.stem}.txt"
                    out_file.write_text(text, encoding="utf-8")
                    print(f"  -> 已写入 {out_file}")
            except Exception as e:
                failed += 1
                print(f"  OCR 失败: {e}", file=sys.stderr)
    if args.quiet:
        print("全部完成。" if failed == 0 else f"完成，{failed} 张失败。")


if __name__ == "__main__":
    main()
