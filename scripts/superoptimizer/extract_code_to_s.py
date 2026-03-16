#!/usr/bin/env python3
"""
Extract `code` field from one or more program JSON files and write to .s files.

Usage:
  extract_code_to_s.py --in /path/to/file.json --out-dir ./out
  extract_code_to_s.py --in /path/to/programs_dir --out-dir ./out

The output .s filename is derived from the input JSON filename (replace .json -> .s).
If the JSON contains an `id` field and `--use-id` is given, the output name will use the id.
"""
import argparse
import json
import os
from pathlib import Path
from typing import Optional


def extract_and_write(json_path: Path, out_dir: Path, use_id: bool = False) -> Optional[Path]:
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load {json_path}: {e}")
        return None

    code = data.get("code")
    if code is None:
        print(f"[WARN] No 'code' field in {json_path}")
        return None

    # Accept either a single string or a list of lines
    if isinstance(code, list):
        code_text = "\n".join(code)
    else:
        code_text = str(code)

    # Normalize line endings
    code_text = code_text.replace('\r\n', '\n')

    # Determine output filename
    if use_id and data.get("id"):
        base = str(data.get("id"))
    else:
        base = json_path.stem

    out_path = out_dir / (base + ".s")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as fo:
            fo.write(code_text)
        print(f"Wrote {out_path}")
        return out_path
    except Exception as e:
        print(f"[ERROR] Failed to write {out_path}: {e}")
        return None


def main():
    p = argparse.ArgumentParser(description="Extract code field from program JSON(s) to .s files")
    p.add_argument("--in", "-i", dest="input", required=True, help="Input JSON file or directory")
    p.add_argument("--out-dir", "-o", dest="out_dir", default="./", help="Output directory for .s files")
    p.add_argument("--use-id", action="store_true", help="Use JSON 'id' field as output filename when available")
    args = p.parse_args()

    inp = Path(args.input)
    out_dir = Path(args.out_dir).resolve()

    if inp.is_dir():
        json_files = sorted([p for p in inp.glob("*.json")])
        if not json_files:
            print(f"No .json files found in directory: {inp}")
            return
        print(f"Found {len(json_files)} json files in {inp}")
        for j in json_files:
            extract_and_write(j, out_dir, use_id=args.use_id)
    elif inp.is_file():
        extract_and_write(inp, out_dir, use_id=args.use_id)
    else:
        print(f"Input path not found: {inp}")


if __name__ == '__main__':
    main()
