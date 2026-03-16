#!/usr/bin/env python3
"""
AlphaEvolve automation wrapper (improved): enhanced process cleanup and validation flow
"""

import argparse
import subprocess
import time
import json
import re
import os
import signal
import psutil
import shutil
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

# ================== 配置（请根据实际情况修改） ==================
SCRIPT_DIR = Path(__file__).parent

parser = argparse.ArgumentParser()
parser.add_argument("--name", type=str, default="nn_shl_c", help="task name")
parser.add_argument("--step", type=int, default=10, help="single run step")
args = parser.parse_args()

# 2. 将参数赋值给你的原有变量名
ASSEMBLY_NAME = args.name          # 这样你下方的所有拼接逻辑都自动生效了
BASE_TOTAL_ITER = args.step        # 同理


SUPEROPTIMIZER_DIR = (SCRIPT_DIR / "../../../../").resolve()  # 自动定位到 t-superoptimizer 根目录
RESEARCH_DIR = (SCRIPT_DIR / "../../examples/lsy_asm_opt").resolve()

SUPEROPTIMIZER_CMD = str(SUPEROPTIMIZER_DIR / "build/tsuperoptimizer")

# 路径配置
INITIAL_PROGRAM = RESEARCH_DIR / ASSEMBLY_NAME / "initial_program.s"
EVALUATOR_PY = RESEARCH_DIR / ASSEMBLY_NAME  / "evaluator.py"  
CONFIG_YAML = RESEARCH_DIR / ASSEMBLY_NAME  / "config.yaml"
TESTCASES_JSON = str(RESEARCH_DIR / ASSEMBLY_NAME / "tc.json")
OPENEOLVE_RUN = (SCRIPT_DIR / "../../openevolve-run.py").resolve()
OPENEOLVE_CMD_BASE = ["python", str(OPENEOLVE_RUN), str(INITIAL_PROGRAM), str(EVALUATOR_PY), "--config", str(CONFIG_YAML)]
BASE_PERF_NPY = RESEARCH_DIR / ASSEMBLY_NAME / "base_perf_terms.npy"
OPENEVOLVE_OUTPUT_DIR = RESEARCH_DIR / ASSEMBLY_NAME / "openevolve_output"

# 验证器相关
TOML_PATH = SUPEROPTIMIZER_DIR / "asm" / "final_benchmark" / ASSEMBLY_NAME / f"{ASSEMBLY_NAME}_validator.toml"
ADD_CEX_SCRIPT = (SCRIPT_DIR / "add_cex.py").resolve()

POLL_INTERVAL_SEC = 5              # 轮询间隔
CHECKPOINT_ROOT = RESEARCH_DIR / ASSEMBLY_NAME / "openevolve_output" / "checkpoints"

LOG_DEBUG = True

def debug_log(msg: str):
    if LOG_DEBUG:
        print(f"[{datetime.now()}] [DEBUG] {msg}")


def clean_previous_outputs():
    """Clean previous baseline/output artifacts for a fresh run."""
    try:
        if BASE_PERF_NPY.exists():
            if BASE_PERF_NPY.is_file() or BASE_PERF_NPY.is_symlink():
                BASE_PERF_NPY.unlink()
                print(f"[{datetime.now()}] Removed baseline file: {BASE_PERF_NPY}")
            else:
                shutil.rmtree(BASE_PERF_NPY)
                print(f"[{datetime.now()}] Removed baseline path: {BASE_PERF_NPY}")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to remove baseline path {BASE_PERF_NPY}: {e}")

    try:
        if OPENEVOLVE_OUTPUT_DIR.exists():
            shutil.rmtree(OPENEVOLVE_OUTPUT_DIR)
            print(f"[{datetime.now()}] Removed output dir: {OPENEVOLVE_OUTPUT_DIR}")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to remove output dir {OPENEVOLVE_OUTPUT_DIR}: {e}")


def update_config_max_iterations(config_path: Path, new_value: int):
    """Safely update `max_iterations` in YAML at `config_path` to `new_value`.
    Creates a timestamped backup before modifying. Uses PyYAML to avoid
    corrupting the file.
    """
    try:
        if not config_path.exists():
            print(f"[{datetime.now()}] Warning: config file not found: {config_path}")
            return

        # backup
        # backup_path = config_path.with_name(config_path.name + f".bak.{int(time.time())}")
        # shutil.copy2(config_path, backup_path)

        with open(config_path, 'r') as f:
            cfg = yaml.safe_load(f) or {}

        # set the value
        cfg['max_iterations'] = int(new_value)

        # write back
        with open(config_path, 'w') as f:
            yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

        # print(f"[{datetime.now()}] Updated {config_path} max_iterations -> {new_value} (backup: {backup_path.name})")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to update config: {e}")

# ================== 强化进程清理模块 ==================

def get_process_match_patterns() -> List[str]:
    """返回需要清理的关键词列表，覆盖评估器、验证器和主程序"""
    name = re.escape(ASSEMBLY_NAME)
    return [
        rf"openevolve-run\.py.*{name}",
        rf"python.*evaluator\.py.*{name}",
        # rf"tsuperoptimizer.*{name}",
        rf"evaluator\.py"  # 有时进程名里直接就是这个
    ]

def cleanup_residual_processes():
    """地毯式清理：遍历所有进程，匹配模式则强制 Kill 及其子进程"""
    patterns = get_process_match_patterns()
    my_pid = os.getpid()
    killed_count = 0

    # 尝试两轮清理，防止清理过程中又有新进程派生
    for _ in range(2):
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] == my_pid: continue
                
                cmdline = ' '.join(proc.info.get('cmdline') or [])
                if any(re.search(pat, cmdline, re.IGNORECASE) for pat in patterns):
                    # 递归获取并杀掉所有子进程
                    try:
                        children = proc.children(recursive=True)
                        for child in children:
                            child.kill()
                    except: pass
                    
                    proc.kill() # 强杀主匹配进程
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    
    if killed_count > 0:
        print(f"[{datetime.now()}] [CLEANUP] Force-cleaned {killed_count} residual processes.")

def safe_terminate(proc: Optional[subprocess.Popen]):
    """通过进程组 (PGID) 终止，并配合地毯式清理"""
    if proc is None or proc.poll() is not None:
        cleanup_residual_processes()
        return

    pid = proc.pid
    try:
        pgid = os.getpgid(pid)
        print(f"[{datetime.now()}] Terminating process group PGID={pgid}...")
        
        # 1. 尝试优雅终止进程组
        os.killpg(pgid, signal.SIGTERM)
        
        # 2. 等待
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # 3. 强杀
            print(f"Timeout, sending SIGKILL to PGID={pgid}")
            os.killpg(pgid, signal.SIGKILL)
    except Exception as e:
        debug_log(f"Terminate error: {e}")

    # 4. 无论如何都执行一次地毯式清理
    cleanup_residual_processes()

# ================== 核心功能函数 ==================

def run_validator(rewrite_asm_path: str) -> tuple[bool, Path | None]:
    cmd = [SUPEROPTIMIZER_CMD, "validator", str(TOML_PATH), f"--rewrite={rewrite_asm_path}"]
    print(f"[{datetime.now()}] Validator running...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        stdout = result.stdout
        if "[RESULT] They are equivalent." in stdout:
            return True, None
        
        cex_path = Path.cwd() / "cex.json"
        if "not equivalent" in stdout.lower() and cex_path.exists():
            return False, cex_path
    except Exception as e:
        print(f"Validator exception: {e}")
    
    return False, None

def add_cex_to_testcases(cex_path: Path):
    cmd = ["python3", str(ADD_CEX_SCRIPT), TESTCASES_JSON, str(cex_path), "--out", TESTCASES_JSON]
    subprocess.run(cmd, check=True)
    print(f"[{datetime.now()}] Injected counterexample into {TESTCASES_JSON}")

def evaluate_program(rewrite_asm_path: str) -> Optional[Dict[str, float]]:
    """调用 evaluator.py 获得三项指标"""
    cmd = ["python", str(EVALUATOR_PY), str(rewrite_asm_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        full_output = result.stdout + "\n" + result.stderr
        parts = re.split(r'(?:^|\n)final\s+result:\s*', full_output, flags=re.IGNORECASE)
        if len(parts) <= 1:
            debug_log("evaluate_program: no 'final result:' marker")
            return None

        tail = parts[-1]
        # 寻找从第一个 '{' 开始的并匹配的大括号子串（处理多重嵌套）
        start = tail.find('{')
        if start == -1:
            debug_log("evaluate_program: no '{' in final result section")
            return None

        brace = 0
        end_idx = None
        for i in range(start, len(tail)):
            ch = tail[i]
            if ch == '{':
                brace += 1
            elif ch == '}':
                brace -= 1
                if brace == 0:
                    end_idx = i
                    break

        if end_idx is None:
            json_str = tail[start:]
        else:
            json_str = tail[start:end_idx+1]

        # 尝试解析 JSON，若失败尝试移除尾随逗号后重试
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            debug_log(f"Evaluate error: initial JSON parse failed: {e}")
            # 清理尾随逗号（例如 {"a":1,}）再试
            cleaned = re.sub(r',\s*(?=[}\]])', '', json_str)
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as e2:
                debug_log(f"Evaluate error: cleaned JSON parse failed: {e2}")
                debug_log("部分 final result 内容：" + json_str[:1000])
                return None

        metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
        return {
            "combined_score": float(metrics.get("combined_score", 0.0)),
            "correctness_score": float(metrics.get("correctness_score", 0.0)),
            "performance_score": float(metrics.get("performance_score", 0.0)),
        }
    except Exception as e:
        debug_log(f"Evaluate error: {e}")
    return None

def reevaluate_checkpoint(checkpoint_dir: Path):
    """
    批量重评并同步更新所有元数据，包括单个程序 JSON、Best Info 以及全局 Metadata。
    """
    programs_dir = checkpoint_dir / "programs"
    if not programs_dir.exists():
        print(f"Programs directory not found: {programs_dir}")
        return

    print(f"[{datetime.now()}] Starting batch re-evaluation of {programs_dir}")
    program_files = list(programs_dir.glob("*.json"))
    new_metrics_map = {}
    temp_asm_path = Path("temp_reeval.s")
    
    # 1. 第一轮遍历：执行重评并记录新分数
    for program_file in program_files:
        try:
            with open(program_file, 'r') as f:
                data = json.load(f)
            program_id = data.get("id")
            code = data.get("code")
            if not program_id or not code: continue

            temp_asm_path.write_text(code)
            new_metrics = evaluate_program(str(temp_asm_path))
            
            if new_metrics:
                new_metrics_map[program_id] = new_metrics
            else:
                print(f"  [Re-eval failed] {program_id[:8]}: keeping original")
        except Exception as e:
            print(f"Error processing {program_file.name}: {e}")
    
    if temp_asm_path.exists(): temp_asm_path.unlink()

    # 2. 第二轮遍历：写回文件，同步更新 parent_metrics
    print(f"[{datetime.now()}] Synchronizing program JSON files...")
    for program_file in program_files:
        try:
            with open(program_file, 'r+') as f:
                data = json.load(f)
                p_id = data.get("id")
                p_parent_id = data.get("parent_id")
                if p_id in new_metrics_map:
                    data["metrics"] = new_metrics_map[p_id]
                if p_parent_id in new_metrics_map:
                    if "metadata" not in data: data["metadata"] = {}
                    data["metadata"]["parent_metrics"] = new_metrics_map[p_parent_id]
                f.seek(0); json.dump(data, f, indent=4); f.truncate()
        except Exception as e:
            print(f"Failed to write {program_file.name}: {e}")

    # 3. 第三轮遍历：加载所有数据用于全局决策
    all_programs_data = []
    for pf in program_files:
        try:
            with open(pf, 'r') as f: all_programs_data.append(json.load(f))
        except: continue

    if not all_programs_data: return

    # 选出全局最佳
    best_program_data = max(all_programs_data, key=lambda d: d.get("metrics", {}).get("combined_score", -1.0))
    best_id = best_program_data["id"]

    # 4. 更新 best_program_info.json 和 best_program.s
    best_info_path = checkpoint_dir / "best_program_info.json"
    existing_info = {}
    if best_info_path.exists():
        try:
            with open(best_info_path, 'r') as f: existing_info = json.load(f)
        except: pass

    new_best_info = {
        "id": best_id,
        "generation": best_program_data.get("generation"),
        "iteration": best_program_data.get("iteration_found", existing_info.get("iteration", -1)),
        "current_iteration": existing_info.get("current_iteration", -1),
        "metrics": best_program_data.get("metrics"),
        "language": best_program_data.get("language", "assembly"),
        "timestamp": best_program_data.get("timestamp", time.time()),
        "saved_at": time.time()
    }
    with open(best_info_path, 'w') as f: json.dump(new_best_info, f, indent=4)
    (checkpoint_dir / "best_program.s").write_text(best_program_data.get("code", ""))

    # ================== 5. 关键：同步修改全局 Metadata 文件 ==================
    metadata_path = checkpoint_dir / "metadata.json" 

    if metadata_path.exists():
        print(f"[{datetime.now()}] Synchronizing global metadata: {metadata_path.name}")
        try:
            with open(metadata_path, 'r+') as f:
                meta = json.load(f)
                
                # A. 更新全局 Best ID
                meta["best_program_id"] = best_id
                
                # B. 更新各岛屿的岛主 (island_best_programs)
                if "islands" in meta and "island_best_programs" in meta:
                    new_island_bests = []
                    for i, island_ids in enumerate(meta["islands"]):
                        # 在当前岛屿的所有程序中找最高分
                        current_island_programs = [p for p in all_programs_data if p["id"] in island_ids]
                        if current_island_programs:
                            ibest = max(current_island_programs, key=lambda p: p.get("metrics", {}).get("combined_score", -1.0))
                            new_island_bests.append(ibest["id"])
                        else:
                            # 降级处理：保留原样
                            new_island_bests.append(meta["island_best_programs"][i])
                    meta["island_best_programs"] = new_island_bests

                # C. (可选但推荐) 更新特征统计，防止分位点计算偏差
                # 在 reevaluate_checkpoint 函数的步骤 5 中加入这段：
                if "feature_stats" in meta:
                    for feat_name in ["complexity", "diversity"]:
                        # 从你已经加载好的重评数据中提取现有的特征值
                        current_vals = [p.get("features", {}).get(feat_name) for p in all_programs_data 
                                if p.get("features", {}).get(feat_name) is not None]
        
                        if current_vals:
                            # 即使计算逻辑没变，也要确保统计范围和当前存活的程序完全一致
                            meta["feature_stats"][feat_name]["min"] = float(min(current_vals))
                            meta["feature_stats"][feat_name]["max"] = float(max(current_vals))
                            meta["feature_stats"][feat_name]["values"] = [float(v) for v in current_vals]
                            print(f"  [Stats sync] {feat_name}: min={min(current_vals)}, max={max(current_vals)}")

                f.seek(0)
                json.dump(meta, f, indent=4)
                f.truncate()
                print(f"  [Metadata sync success] Global Best now points to: {best_id[:8]}")
        except Exception as e:
            print(f"Metadata synchronization failed: {e}")
    else:
        print(f"Warning: global metadata file not found, resuming may cause state rollback.")

    print(f"[{datetime.now()}] Batch re-evaluation and full metadata update complete!")
        
        
def get_latest_checkpoint() -> Optional[Path]:
    cps = [p for p in CHECKPOINT_ROOT.glob("checkpoint_*") if p.is_dir()]
    return max(cps, key=lambda p: int(p.name.split("_")[1])) if cps else None


# ================== 主流程 ==================

def main():
    clean_previous_outputs()

    # Ensure config max_iterations matches requested total iterations before any run
    update_config_max_iterations(CONFIG_YAML, BASE_TOTAL_ITER)

    current_checkpoint = get_latest_checkpoint()
    last_seen_iter = 0
    best_iter_tracked = 0
    max_total_iter = BASE_TOTAL_ITER
    
    # 启动前先同步一下进度
    if current_checkpoint:
        last_seen_iter = int(current_checkpoint.name.split("_")[1])

    while last_seen_iter < max_total_iter:
        # 1. 启动前彻底清理
        cleanup_residual_processes()
        
        cmd = OPENEOLVE_CMD_BASE[:]
        if current_checkpoint:
            max_total_iter = int(current_checkpoint.name.split("_")[1]) + BASE_TOTAL_ITER
            cmd += ["--checkpoint", str(current_checkpoint)]
            print(f"[{datetime.now()}] Resuming from {current_checkpoint.name}, stop at iter {max_total_iter}")
        else:
            print(f"[{datetime.now()}] Starting for the first time")

        # 使用 os.setsid 开启新进程组，方便后续一锅端
        proc = subprocess.Popen(cmd, preexec_fn=os.setsid)

        # 监控循环
        while True:
            time.sleep(POLL_INTERVAL_SEC)
            
            # 检查进程是否意外挂掉
            if proc.poll() is not None:
                # 进程退出后，最后看一眼磁盘进度
                final_cp = get_latest_checkpoint()
                if final_cp:
                    final_iter = int(final_cp.name.split("_")[1])
                    if final_iter >= max_total_iter:
                        print(f"[{datetime.now()}] Target reached ({final_iter}/{max_total_iter}), exiting normally.")
                        return # task completed
                
                print(f"[{datetime.now()}] Main program exited unexpectedly, preparing to restart...")
                break # 跳出监控，由外层逻辑 Resume

            latest_cp = get_latest_checkpoint()
            if not latest_cp: continue

            info_path = latest_cp / "best_program_info.json"
            if not info_path.exists(): continue

            try:
                with open(info_path, 'r') as f:
                    info = json.load(f)
                
                f_best_iter = info.get("iteration", -1)
                f_curr_iter = info.get("current_iteration", -1)
                last_seen_iter = max(f_curr_iter, last_seen_iter)
                
                print(f"[{datetime.now()}] Monitoring... current iteration: {f_curr_iter}, Best iteration: {f_best_iter}, last recorded iteration: {last_seen_iter}")
                # 发现新的 Best 程序
                if f_best_iter > best_iter_tracked:
                    print(f"[{datetime.now()}] Detected new Best (Iter {f_best_iter}), triggering validation flow")
                    best_iter_tracked = f_best_iter
                    
                    # 停止并深度清理
                    safe_terminate(proc)
                    
                    # 提取代码验证
                    best_s = latest_cp / "best_program.s"
                    if best_s.exists():
                        is_equiv, cex = run_validator(str(best_s))
                        if not is_equiv:
                            print("!!! Not equivalent, injecting counterexample and re-evaluating !!!")
                            if cex: add_cex_to_testcases(cex)
                            reevaluate_checkpoint(latest_cp)
                        else:
                            print(">>> Validation passed, program is equivalent.")
                    
                    current_checkpoint = latest_cp
                    break # 跳出监控，重启 AlphaEvolve

                if last_seen_iter >= max_total_iter:
                    print(f"[{datetime.now()}] Progress reached ({f_curr_iter}), stopping...")
                    safe_terminate(proc)
                    return # exit script

            except Exception as e:
                debug_log(f"Loop error: {e}")

    print("Task complete.")
    
    print("Final check")
    latest_cp = get_latest_checkpoint()
    best_s = latest_cp / "best_program.s"
    is_equiv, cex = run_validator(str(best_s))
    if not is_equiv:
        print("!!! Final best program is not equivalent, injecting counterexample and re-evaluating !!!")
        if cex: add_cex_to_testcases(cex)
        # 这里的目录错误
        reevaluate_checkpoint(latest_cp)
    else:
        print(">>> Final validation passed, program is equivalent.")
        
    # 如果又更新了, 把lastest_cp里的best_program.s和best_program_info.json复制到openevolve/best的目录下，供后续使用
    if not is_equiv:
        best_dir = CHECKPOINT_ROOT / "../best"
        best_dir.mkdir(exist_ok=True)
        shutil.copy2(latest_cp / "best_program.s", best_dir / "best_program.s")
        shutil.copy2(latest_cp / "best_program_info.json", best_dir / "best_program_info.json")
        print(f"Copied final best program and info to {best_dir}")
    

if __name__ == '__main__':
    main()