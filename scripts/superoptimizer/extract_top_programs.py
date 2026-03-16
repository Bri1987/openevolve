#!/usr/bin/env python3
"""
读取一个包含 program JSON 的目录，按要求过滤并按 (diversity, combined_score) 排序，输出前 n 个程序。

用法:
    旧格式(兼容): python extract_top_programs.py /path/to/programs n threshold [--out-dir OUT]
    新格式(可省略 n): python extract_top_programs.py /path/to/programs threshold [--out-dir OUT]

示例:
  python extract_top_programs.py ./openevolve_output/checkpoints/checkpoint_5/programs 10 0.2 --out-dir ./top10
    python extract_top_programs.py ./openevolve_output/checkpoints/checkpoint_5/programs 0.2 --out-dir ./top_auto
"""
import argparse
import json
import os
import shutil
from typing import Any, Dict, List, Optional, Set, Tuple


def load_program(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_metadata(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def default_metadata_path(programs_dir: str) -> str:
    return os.path.join(os.path.dirname(programs_dir), "metadata.json")


def parse_feature_key(feature_key: str) -> Optional[Tuple[int, int]]:
    parts = feature_key.split("-")
    if len(parts) < 2:
        return None
    try:
        first = int(parts[0])
        second = int(parts[-1])
    except ValueError:
        return None
    return first, second


def build_second_dim_entries(meta: Dict[str, Any]) -> Dict[int, List[Tuple[int, str]]]:
    """
    按第二维分组，保留该第二维下所有 (第一维, program_id) 条目。
    后续会在阈值过滤后的候选里再选择第一维最大的格子。
    """
    entries_by_second: Dict[int, List[Tuple[int, str]]] = {}

    for fmap in meta.get("island_feature_maps", []):
        if not isinstance(fmap, dict):
            continue
        for feature_key, pid in fmap.items():
            if not isinstance(feature_key, str) or not isinstance(pid, str):
                continue
            parsed = parse_feature_key(feature_key)
            if parsed is None:
                continue
            first, second = parsed
            entries_by_second.setdefault(second, []).append((first, pid))

    return entries_by_second


def extract_values(data: Dict[str, Any]) -> Dict[str, Any]:
    # code
    code = data.get("code", "")
    # diversity: prefer top-level, fall back to metrics
    diversity = None
    if "diversity" in data:
        diversity = data.get("diversity")
    else:
        diversity = data.get("metrics", {}).get("diversity")
    try:
        diversity = float(diversity) if diversity is not None else 0.0
    except Exception:
        diversity = 0.0

    # combined_score: try top-level then metrics
    combined = None
    if "combined_score" in data:
        combined = data.get("combined_score")
    else:
        combined = data.get("metrics", {}).get("combined_score")
    try:
        combined = float(combined) if combined is not None else 0.0
    except Exception:
        combined = 0.0

    return {"id": data.get("id"), "code": code, "diversity": diversity, "combined_score": combined, "raw": data}


def main():
    p = argparse.ArgumentParser(description="Extract top-n programs by diversity and combined_score")
    p.add_argument("programs_dir", help="directory containing program JSON files")
    p.add_argument("arg2", help="old format: n; new format: threshold")
    p.add_argument("arg3", nargs="?", help="old format only: threshold")
    p.add_argument("--metadata", help="optional metadata.json path (default: parent of programs_dir)")
    p.add_argument("--out-dir", help="optional output directory to copy selected JSON files")
    args = p.parse_args()

    requested_n: Optional[int]
    threshold: float
    if args.arg3 is None:
        # New format: programs_dir threshold
        requested_n = None
        try:
            threshold = float(args.arg2)
        except ValueError:
            raise SystemExit(f"Invalid threshold: {args.arg2}")
    else:
        # Old format: programs_dir n threshold
        try:
            requested_n = int(args.arg2)
        except ValueError:
            raise SystemExit(f"Invalid n: {args.arg2}")
        try:
            threshold = float(args.arg3)
        except ValueError:
            raise SystemExit(f"Invalid threshold: {args.arg3}")

    if not os.path.isdir(args.programs_dir):
        raise SystemExit(f"programs_dir not found: {args.programs_dir}")

    files = [os.path.join(args.programs_dir, f) for f in os.listdir(args.programs_dir) if f.endswith(".json")]
    print(f"Found {len(files)} .json files in {args.programs_dir}")
    if requested_n is None:
        print(f"Requesting top n=auto with threshold={threshold}")
    else:
        print(f"Requesting top n={requested_n} with threshold={threshold}")

    items: List[Dict[str, Any]] = []
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for fp in files:
        try:
            data = load_program(fp)
        except Exception:
            print(f"Warning: failed to load JSON file: {fp}")
            continue
        item = extract_values(data)
        # id fallback to filename stem
        item_id = item.get("id") or os.path.splitext(os.path.basename(fp))[0]
        item["id"] = item_id
        # filter out if combined_score < threshold
        if item["combined_score"] < threshold:
            continue
        # attach source path for optional saving
        item["_src_path"] = fp
        items.append(item)
        items_by_id[item_id] = item

    # sort: first by diversity (desc), then combined_score (desc)
    items.sort(key=lambda x: (-x["diversity"], -x["combined_score"]))

    print(f"After filtering, {len(items)} items remain (combined_score >= {threshold})")

    # Phase 1: use metadata island_feature_maps to guarantee second-dimension coverage,
    # and for each second dimension keep entries from the max first-dimension cell.
    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()
    available_second_bins_after_threshold = 0
    metadata_used = False

    metadata_path = args.metadata or default_metadata_path(args.programs_dir)
    if os.path.isfile(metadata_path):
        try:
            meta = load_metadata(metadata_path)
            second_dim_entries = build_second_dim_entries(meta)
            if second_dim_entries:
                metadata_used = True
                all_seconds = sorted(second_dim_entries.keys())
                print(f"Metadata loaded: {metadata_path}")
                print(f"Second-dimension bins found: {all_seconds}")
                print(f"Ensuring coverage for bins: {all_seconds}")

                missing_bins: List[int] = []
                for second in all_seconds:
                    raw_entries = second_dim_entries.get(second, [])
                    available_entries: List[Tuple[int, Dict[str, Any]]] = []
                    for first, pid in raw_entries:
                        item = items_by_id.get(pid)
                        if item is None:
                            continue
                        available_entries.append((first, item))

                    if not available_entries:
                        missing_bins.append(second)
                        continue

                    max_first = max(first for first, _ in available_entries)
                    candidates = [item for first, item in available_entries if first == max_first]

                    available_second_bins_after_threshold += 1
                    # if multiple IDs in the same max-first-dim cell, pick highest diversity
                    chosen = max(candidates, key=lambda x: (x["diversity"], x["combined_score"]))
                    pid = chosen.get("id")
                    if pid not in selected_ids:
                        selected.append(chosen)
                        selected_ids.add(pid)

                if missing_bins:
                    print(f"Warning: no available candidate for second-dimension bins: {missing_bins}")
                print(f"Preselected {len(selected)} programs from metadata coverage")
        except Exception as e:
            print(f"Warning: failed to use metadata from {metadata_path}: {e}")
    else:
        print(f"Metadata not found, skip coverage preselection: {metadata_path}")

    if requested_n is None:
        if metadata_used:
            effective_n = available_second_bins_after_threshold
            print(f"n not provided, auto n={effective_n} (available second-dimension bins after threshold)")
        else:
            effective_n = len(items)
            print(f"n not provided and metadata unavailable, fallback to n={effective_n} (all filtered items)")
    else:
        effective_n = requested_n

    if effective_n > 0 and effective_n < len(selected):
        print(f"Requested n={effective_n} is smaller than required coverage count={len(selected)}, expanding n")
        effective_n = len(selected)

    # Phase 2: fallback to previous diversity-first ranking for remaining slots
    top = list(selected)
    if effective_n > 0:
        for it in items:
            if len(top) >= effective_n:
                break
            pid = it.get("id")
            if pid in selected_ids:
                continue
            top.append(it)
    else:
        for it in items:
            pid = it.get("id")
            if pid in selected_ids:
                continue
            top.append(it)

    print(f"Selecting top {len(top)} items")
    if top:
        print("Selected IDs:", [t.get('id') for t in top])
    else:
        print("No programs selected (empty result)")

    # print results as JSON array to stdout
    def _code_lines(code_str: str) -> List[str]:
        # Split into lines preserving empty lines
        if code_str is None:
            return []
        return code_str.split("\n")

    out_list = []
    for it in top:
        # Only include the three requested fields, in the requested order
        code_lines = _code_lines(it.get("code"))
        out_list.append({
            "code": code_lines,
            "diversity": it.get("diversity"),
            "combined_score": it.get("combined_score"),
        })

    print(json.dumps(out_list, ensure_ascii=False, indent=2))

    # optionally copy raw json files to out-dir
    if args.out_dir:
        if os.path.isdir(args.out_dir):
            shutil.rmtree(args.out_dir)
            print(f"Removed existing output directory: {args.out_dir}")
        os.makedirs(args.out_dir, exist_ok=True)
        for it in top:
            src = it.get("_src_path")
            if not src:
                continue
            dst = os.path.join(args.out_dir, os.path.basename(src))
            # write trimmed JSON containing only the three fields
            trimmed = {"code": it.get("code"), "diversity": it.get("diversity"), "combined_score": it.get("combined_score")}
            try:
                with open(dst, "w", encoding="utf-8") as fw:
                    json.dump(trimmed, fw, ensure_ascii=False, indent=2)
                print(f"Wrote trimmed JSON to: {dst}")
            except Exception:
                print(f"Warning: failed to write trimmed JSON to: {dst}")


if __name__ == "__main__":
    main()
