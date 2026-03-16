#!/usr/bin/env python3
import os
import json
import re
from collections import defaultdict


def find_programs_dir():
    # Known target relative path from request
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "examples", "lsy_asm_opt", "nn_shl_c_diversity", "openevolve_output", "checkpoints", "checkpoint_30", "programs"))
    if os.path.isdir(base):
        return base
    candidate = os.environ.get("OPENEVOLVE_PROGRAMS_DIR")
    if candidate and os.path.isdir(candidate):
        return candidate
    raise SystemExit(f"programs directory not found: tried {base}")


def find_metadata_file(programs_dir):
    # metadata.json is expected one directory above programs_dir
    parent = os.path.abspath(os.path.join(programs_dir, '..'))
    meta_path = os.path.join(parent, 'metadata.json')
    if os.path.isfile(meta_path):
        return meta_path
    return None


def detect_bins(code_text):
    bins = set()
    # patterns like 'count/4' or 'count/2 iterations'
    for m in re.finditer(r"count[^\d]*(\d+)", code_text, flags=re.IGNORECASE):
        try:
            bins.add(int(m.group(1)))
        except Exception:
            pass
    # patterns like '4x unrolled'
    for m in re.finditer(r"(\d+)x\s+unroll|(\d+)x\s+unrolled", code_text, flags=re.IGNORECASE):
        g = m.group(1) or m.group(2)
        if g:
            try:
                bins.add(int(g))
            except Exception:
                pass
    # fallback: look for small #N tokens often used in comments (heuristic)
    for m in re.finditer(r"#(\d+)\b", code_text):
        try:
            v = int(m.group(1))
            if v in (1, 2, 4, 8):
                bins.add(v)
        except Exception:
            pass
    if not bins:
        return "-"
    arr = sorted(bins, reverse=True)
    return "-".join(str(x) for x in arr)


def load_json_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
            if text.startswith('```') and text.rstrip().endswith('```'):
                # strip code fences if accidentally present
                text = '\n'.join(text.strip('`\n').splitlines())
            return json.loads(text)
    except Exception:
        return None


def main():
    prog_dir = find_programs_dir()
    files = sorted([f for f in os.listdir(prog_dir) if f.endswith('.json')])
    islands = defaultdict(list)

    for fn in files:
        path = os.path.join(prog_dir, fn)
        data = load_json_file(path)
        if not data:
            continue
        pid = data.get('id') or os.path.splitext(fn)[0]
        island = data.get('island')
        if island is None:
            island = (data.get('metadata') or {}).get('island')
        if island is None:
            island = -1

        metrics = data.get('metrics', {}) or {}
        combined = metrics.get('combined_score')
        correctness = metrics.get('correctness_score')
        perf = metrics.get('performance_score')
        better_pos = metrics.get('better_than_base_avg_position')
        diversity = data.get('diversity')
        if diversity is None:
            diversity = (data.get('metrics') or {}).get('diversity')

        # Prefer bins from metadata mapping if available (see metadata.json island_feature_maps)
        code = data.get('code') or ''
        bins = detect_bins(code)

        entry = {
            'id': pid,
            'bins': bins,
            'combined': combined,
            'correctness': correctness,
            'performance': perf,
            'better_pos': better_pos,
            'diversity': diversity,
            '_raw_bins': bins,
            'bins_source': 'detected',
        }
        islands[island].append(entry)

    # enrich bins using metadata.json mapping (overrides detected bins)
    enrich_with_metadata(prog_dir, islands)

    for isl in sorted(islands.keys()):
        printed_any = False
        lines = []
        for p in sorted(islands[isl], key=lambda x: (x['combined'] is None, -(x['combined'] or 0))):
            # only print if bins came from metadata mapping
            if p.get('bins_source') != 'meta':
                continue
            printed_any = True
            lines.append(" - bins: {bins} | id: {id} | combined_score: {combined} | correctness_score: {correctness} | performance_score: {performance} | better_than_base_avg_position: {better_pos} | diversity: {diversity}".format(**p))
        if printed_any:
            print(f"Island {isl}:")
            for l in lines:
                print(l)
            print()


def enrich_with_metadata(prog_dir, islands):
    meta = find_metadata_file(prog_dir)
    if not meta:
        return
    try:
        with open(meta, 'r', encoding='utf-8') as f:
            meta_js = json.load(f)
    except Exception:
        return

    id_to_bins = {}
    # island_feature_maps is a list of dicts mapping feature_key -> id
    for fmap in meta_js.get('island_feature_maps', []):
        for k, v in fmap.items():
            # k is like '0-2' representing bins
            if v in id_to_bins:
                # append if multiple
                if k not in id_to_bins[v].split(','):
                    id_to_bins[v] = id_to_bins[v] + ',' + k
            else:
                id_to_bins[v] = k

    # apply mapping to islands dict
    for isl, plist in islands.items():
        for p in plist:
            bid = p['id']
            if bid in id_to_bins:
                p['bins'] = id_to_bins[bid]
                p['bins_source'] = 'meta'
            else:
                # keep previously detected raw bins
                p['bins'] = p.get('_raw_bins', p.get('bins', '-'))
                p['bins_source'] = p.get('bins_source', 'detected')
            if '_raw_bins' in p:
                del p['_raw_bins']




if __name__ == '__main__':
    main()
