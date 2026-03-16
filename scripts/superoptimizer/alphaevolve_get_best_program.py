#!/usr/bin/env python3
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

# ================== 配置（请根据实际情况修改） ==================
SCRIPT_DIR = Path(__file__).parent

parser = argparse.ArgumentParser()
parser.add_argument("--name", type=str, default="nn_add_mc", help="task name")
parser.add_argument("--output", type=str, default=None, help="output file path")
args = parser.parse_args()

# 2. 将参数赋值给你的原有变量名
ASSEMBLY_NAME = args.name
OUTPUT_PATH = args.output
RESEARCH_DIR = (SCRIPT_DIR / "../../examples/lsy_asm_opt").resolve()

CHECKPOINT_ROOT = RESEARCH_DIR / ASSEMBLY_NAME / "openevolve_output" / "checkpoints"
     
def get_latest_checkpoint() -> Optional[Path]:
    cps = [p for p in CHECKPOINT_ROOT.glob("checkpoint_*") if p.is_dir()]
    return max(cps, key=lambda p: int(p.name.split("_")[1])) if cps else None

def main():
    # 1. 获取最新的 Checkpoint 目录
    latest_cp = get_latest_checkpoint()
    
    if not latest_cp:
        print(f"[{datetime.now()}] Error: No checkpoint found in {CHECKPOINT_ROOT}")
        return

    # 2. 定位 best_program.s 文件
    best_s_path = latest_cp / "best_program.s"
    
    if not best_s_path.exists():
        print(f"[{datetime.now()}] Error: 'best_program.s' not found in {latest_cp}")
        return

    print(f"[{datetime.now()}] Reading from: {best_s_path}")

    # 3. 读取内容并进行处理
    try:
        lines = best_s_path.read_text().splitlines()
        
        if not lines:
            print("Warning: The source file is empty.")
            return

        # 如果第一行包含 "assembly" (不区分大小写)，则删除
        if "assembly" in lines[0].lower():
            processed_lines = lines[1:]
            print(f"[{datetime.now()}] Removed the first line: '{lines[0]}'")
        else:
            processed_lines = lines

        # 将处理后的内容合并为字符串
        final_content = "\n".join(processed_lines)

        # 4. 写入输出路径
        if OUTPUT_PATH:
            out_p = Path(OUTPUT_PATH)
            # 确保父目录存在
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(final_content)
            print(f"[{datetime.now()}] Successfully saved to: {OUTPUT_PATH}")
        else:
            # 如果没指定输出路径，默认打印或报错
            print("--- Processed Assembly Content ---")
            print(final_content)
            print("----------------------------------")
            print("Warning: No --output path provided. Content printed to console.")

    except Exception as e:
        print(f"[{datetime.now()}] Failed to process file: {e}")

if __name__ == '__main__':
    main()
