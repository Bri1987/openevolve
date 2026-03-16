# empty
#!/usr/bin/env python3
"""将单个 counter-example (cex.json) 加入到多个测例文件 (tc.json) 中。

用法:
  add_cex.py tc.json cex.json [--out out.json]

默认会原地修改第一个文件 (tc.json)。如果提供 `--out`，会将结果写到指定文件。
支持 tc.json 为数组（最常见），或包含列表字段 `cases` / `tests` 的对象。
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path):
	try:
		with path.open('r', encoding='utf-8') as f:
			return json.load(f)
	except Exception as e:
		print(f"无法读取或解析 JSON: {path}: {e}", file=sys.stderr)
		raise


def save_json(obj, path: Path):
	try:
		with path.open('w', encoding='utf-8') as f:
			json.dump(obj, f, indent=2, ensure_ascii=False)
	except Exception as e:
		print(f"无法写入 JSON: {path}: {e}", file=sys.stderr)
		raise


def merge(tc_obj, cex_obj):
	# 如果 tc_obj 本身是一个列表，直接追加
	if isinstance(tc_obj, list):
		tc_obj.append(cex_obj)
		return tc_obj

	# 常见模式：对象中包含 'cases' 或 'tests' 字段
	for key in ('cases', 'tests'):
		if isinstance(tc_obj, dict) and key in tc_obj and isinstance(tc_obj[key], list):
			tc_obj[key].append(cex_obj)
			return tc_obj

	# 不知道结构：尝试把现有对象和新 cex 放入数组中并返回
	return [tc_obj, cex_obj]


def main():
	p = argparse.ArgumentParser(description='Add a single cex JSON into a tc JSON collection.')
	p.add_argument('tc', help='Path to tc.json (array of testcases)')
	p.add_argument('cex', help='Path to cex.json (single testcase)')
	p.add_argument('--out', '-o', help='Output file (default: overwrite tc file)', default=None)
	args = p.parse_args()

	tc_path = Path(args.tc)
	cex_path = Path(args.cex)
	out_path = Path(args.out) if args.out else tc_path

	tc = load_json(tc_path)
	cex = load_json(cex_path)

	merged = merge(tc, cex)

	save_json(merged, out_path)

	print(f"已将 {cex_path} 的测例加入到 {out_path}")


if __name__ == '__main__':
	main()

