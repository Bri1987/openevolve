"""
Evaluator that invokes the local t-superoptimizer binary to evaluate a
candidate assembly program. This evaluator runs a command like::

  ./build/tsuperoptimizer evaluator /path/to/nn_add_mc.toml --rewrite=/abs/path/to/candidate.s --tc-json=/tmp/tc.json

It captures stdout/stderr, looks for the last occurrence of a line like
`[info] cost: <cost>, perf: <perf>` and returns those values inside an
EvaluationResult. `cost` is treated as correctness cost and `perf` as
performance metric (both lower is better).
"""

import json
import subprocess
import tempfile
import re
from pathlib import Path
from openevolve.evaluation_result import EvaluationResult
import os
import logging
import math

THIS_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
LOGGER = logging.getLogger("examples.nn_add_mc.evaluator")

# Default t-superoptimizer root; override by setting TSUPER_ROOT env var.
DEFAULT_TSUPER_ROOT = Path(os.environ.get("TSUPER_ROOT", "/home/ubuntu/lsy_workspace/t-superoptimizer"))

RE_INFO = re.compile(r"\[info\]\s*cost:\s*([0-9]+(?:\.[0-9]+)?),\s*perf:\s*([0-9]+(?:\.[0-9]+)?)", re.I)


def _parse_cost_perf(text: str):
    matches = RE_INFO.findall(text)
    if not matches:
        return None
    cost_s, perf_s = matches[-1]
    try:
        cost = float(cost_s) if '.' in cost_s else int(cost_s)
        perf = float(perf_s)
    except Exception:
        return None
    return cost, perf


def evaluate(program_path: str) -> EvaluationResult:
    print("Evaluating candidate program at:", program_path)
    
    try:
        # 读取文件内容
        with open(program_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        
        # 检查并删除第一行如果是"assembly"
        modified = False
        if lines and lines[0].strip().lower() == "assembly":
            print("Removing first line 'assembly' from the file")
            lines = lines[1:]
            modified = True
        
        # 如果文件被修改，写回文件
        if modified:
            with open(program_path, 'w', encoding='utf-8') as file:
                file.writelines(lines)
        
        # 打印文件内容
        content = ''.join(lines)
        print("\n=== File Content ===")
        print(content)
        print("=== End of File ===\n")
        
    except FileNotFoundError:
        print(f"Error: File not found at {program_path}")
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": f"File not found at {program_path}"}
        )
    except Exception as e:
        print(f"Error reading file: {e}")
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": f"Error reading file: {str(e)}"}
        )
    
    # 继续原有的评估逻辑
    try:
        return _evaluate(program_path)
    except Exception as e:
        LOGGER.exception("Evaluation failed")
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": str(e)}
        )

def _evaluate(program_path: str) -> EvaluationResult:
    tsuper_root = DEFAULT_TSUPER_ROOT
    tsuper_bin = tsuper_root / "build" / "tsuperoptimizer"
    toml_path = tsuper_root / "asm" / "final_benchmark" / "nn_add_mc" / "nn_add_mc.toml"

    if not tsuper_bin.exists():
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": f"t-superoptimizer binary not found at {tsuper_bin}"}
        )
    if not toml_path.exists():
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": f"toml not found at {toml_path}"}
        )

    # Ensure program_path is absolute
    program_path = str(Path(program_path).resolve())

    # Quick compile check: try to assemble/compile the .s into an object file.
    try:
        import tempfile as _tf
        obj_fd = _tf.NamedTemporaryFile(suffix=".o", delete=False)
        obj_path = obj_fd.name
        obj_fd.close()
        compile_cmd = ["gcc", "-c", program_path, "-o", obj_path]
        LOGGER.debug("Compile check: %s", " ".join(compile_cmd))
        cproc = subprocess.run(compile_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        if cproc.returncode != 0:
            try:
                os.unlink(obj_path)
            except Exception:
                pass
            return EvaluationResult(
                metrics={"combined_score": 0.0},
                artifacts={
                    "compile_cmd": " ".join(compile_cmd),
                    "compile_stdout": cproc.stdout,
                    "compile_stderr": cproc.stderr,
                }
            )
        try:
            os.unlink(obj_path)
        except Exception:
            pass
    except subprocess.TimeoutExpired:
        return EvaluationResult(metrics={"combined_score": 0.0}, artifacts={"error": "compile_timeout"})
    except Exception as e:
        LOGGER.exception("Compile check failed")
        return EvaluationResult(metrics={"combined_score": 0.0}, artifacts={"error": str(e)})

    # Prepare tc.json
    example_tc = THIS_DIR / "tc.json"
    if example_tc.exists():
        tc_json = example_tc
        cmd = [str(tsuper_bin), "evaluator", str(toml_path), f"--rewrite={program_path}", f"--tc-json={tc_json}"]
        LOGGER.info("Running (using existing tc.json): %s", " ".join(cmd))
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return EvaluationResult(metrics={"combined_score": 0.0}, artifacts={"error": "timeout", "timeout": True})
    else:
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            tc_json = tdp / "tc.json"
            cmd = [str(tsuper_bin), "evaluator", str(toml_path), f"--rewrite={program_path}", f"--tc-json={tc_json}"]
            LOGGER.info("Running (using temp tc.json): %s", " ".join(cmd))
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
            except subprocess.TimeoutExpired:
                return EvaluationResult(metrics={"combined_score": 0.0}, artifacts={"error": "timeout", "timeout": True})

    output = proc.stdout or ""

    # Print the external command output for debugging (user requested).
    print("\n=== tsuperoptimizer output ===")
    print(output)
    print("=== end tsuperoptimizer output ===\n")

    parsed = _parse_cost_perf(output)
    if parsed:
        raw_correctness_cost, raw_perf_cost = parsed
        compile_success = True
    else:
        raw_correctness_cost = None
        raw_perf_cost = None
        compile_success = True  # 已通过 gcc -c

    # ────────────────────────────────────────────────
    # 转换为越高越好的 score
    # ────────────────────────────────────────────────

    # 正确性 score（cost 越接近 0 越好）
    if raw_correctness_cost is None:
        correctness_score = 0.0
    else:
        correctness_score = 1.0 / (1.0 + raw_correctness_cost ** 0.4 * 10)   # **0.5 压缩大值，*10 控制斜率

    # 性能 score（perf 越小越好，用 baseline 归一化）
    BASELINE_PERF = 52.666666666666664 # 你的初始程序 perf 值
    if raw_perf_cost is None or raw_perf_cost <= 0:
        performance_score = 0.0
    else:
        performance_score = 1.0 / (1.0 + math.exp((raw_perf_cost - BASELINE_PERF) / 20))
        # performance_score = BASELINE_PERF / (BASELINE_PERF + raw_perf_cost)

    combined_score = performance_score * (correctness_score ** 2.5)

    # ────────────────────────────────────────────────
    # 返回结果
    # ────────────────────────────────────────────────

    metrics = {
        "combined_score": combined_score,          # 主 fitness，MAP-Elites 用这个
        # "correctness_cost": raw_correctness_cost,
        # "perf_cost": raw_perf_cost,
        "correctness_score": correctness_score,
        "performance_score": performance_score,
    }

    artifacts = {
        "compile_success": compile_success,
    }

    return EvaluationResult(metrics=metrics, artifacts=artifacts)


if __name__ == "__main__":
    import sys
    from pathlib import Path as _P

    if len(sys.argv) < 2:
        print("Usage: evaluator.py <candidate_asm.s>")
        sys.exit(1)
    candidate = _P(sys.argv[1])
    res = evaluate(str(candidate))
    print(json.dumps({"metrics": res.metrics}, indent=2))
    print(json.dumps({"artifacts": res.artifacts}, indent=2))