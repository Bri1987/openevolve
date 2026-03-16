#!/usr/bin/env python3
"""
AlphaEvolve automation wrapper (improved): enhanced process cleanup and validation flow
"""

import argparse
import subprocess
import time
import json
import yaml
import shutil
import re
import os
import signal
import psutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

# ================== 配置（请根据实际情况修改） ==================
SCRIPT_DIR = Path(__file__).parent

parser = argparse.ArgumentParser()
parser.add_argument("--name", type=str, default="nn_shl_c", help="task name")
parser.add_argument("--step", type=int, default=50, help="single run step")
parser.add_argument("--num", type=int, default=5, help="init population size (top N programs to extract)")
parser.add_argument("--output", type=str, default=None, help="output file path")
parser.add_argument("--threshold", type=float, default=10, help="performance threshold for filtering programs")
args = parser.parse_args()

# 2. 将参数赋值给你的原有变量名
ASSEMBLY_NAME = args.name + "_loop"  # 同理
OUTPUT_PATH = args.output
THRESHOLD = args.threshold
TOP_N = args.num
TOTAL_ITER = args.step


SUPEROPTIMIZER_DIR = (SCRIPT_DIR / "../../../../").resolve()  # 自动定位到 t-superoptimizer 根目录
RESEARCH_DIR = (SCRIPT_DIR / "../../examples/lsy_asm_opt").resolve()

SUPEROPTIMIZER_CMD = str(SUPEROPTIMIZER_DIR / "build/tsuperoptimizer")

# 路径配置
INITIAL_PROGRAM = RESEARCH_DIR / ASSEMBLY_NAME / "initial_program.s"
EVALUATOR_PY = RESEARCH_DIR / ASSEMBLY_NAME  / "evaluator.py"  
CONFIG_YAML = RESEARCH_DIR / ASSEMBLY_NAME  / "config.yaml"
TESTCASES_JSON = str(RESEARCH_DIR / ASSEMBLY_NAME / "tc.json")
CHECKPOINT_ROOT = str(RESEARCH_DIR / ASSEMBLY_NAME / "openevolve_output" / "checkpoints" / "checkpoint_0")
OPENEOLVE_RUN = (SCRIPT_DIR / "../../openevolve-run.py").resolve()
OPENEOLVE_CMD_BASE = ["python", str(OPENEOLVE_RUN), str(INITIAL_PROGRAM), str(EVALUATOR_PY), "--config", str(CONFIG_YAML), "--checkpoint", str(CHECKPOINT_ROOT)]
BASE_PERF_NPY = RESEARCH_DIR / ASSEMBLY_NAME / "base_perf_terms.npy"


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
    
def get_latest_checkpoint() -> Optional[Path]:
    cps = [p for p in CHECKPOINT_ROOT.glob("checkpoint_*") if p.is_dir()]
    return max(cps, key=lambda p: int(p.name.split("_")[1])) if cps else None


# ================== 主流程 ==================

def main():
    clean_previous_outputs()

    update_config_max_iterations(CONFIG_YAML, TOTAL_ITER)
    
    # 1. 启动前彻底清理
    cleanup_residual_processes()
    cmd = OPENEOLVE_CMD_BASE[:]

    # 确保输出目录存在（如果未指定则默认到脚本目录下的 top_programs）
    out_dir = Path(OUTPUT_PATH) if OUTPUT_PATH else (SCRIPT_DIR / "top_programs")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 启动 openevolve-run.py 并将输出直接打印到控制台（不写文件）
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    print("Starting openevolve-run; output will be printed to console")

    try:
        proc = subprocess.Popen(cmd, preexec_fn=os.setsid, env=env)
    except Exception as e:
        print(f"Failed to start openevolve-run: {e}")
        return

    try:
        # 等待进程结束（运行可能很久），支持 Ctrl-C 中断
        ret = proc.wait()
    except KeyboardInterrupt:
        print("Interrupted by user — terminating openevolve-run...")
        safe_terminate(proc)
        return
    except Exception as e:
        print(f"Error while waiting for openevolve-run: {e}")
        safe_terminate(proc)
        return

    if ret != 0:
        return

    # 2. 运行完成后，找到最新 checkpoint
    last_cp = get_latest_checkpoint()
    if not last_cp:
        print("No checkpoints found under", CHECKPOINT_ROOT)
        return

    # 3. 调用 extract_top_programs.py，得到最终的 top N 程序列表, 写入 output 路径
    extract_top_programs_cmd = [
        "python", str(SCRIPT_DIR / "extract_top_programs.py"),
        str(last_cp / "programs"),
        # str(TOP_N),
        str(THRESHOLD),
        "--out-dir", str(out_dir),
    ]
    print("Running:", " ".join(extract_top_programs_cmd))
    result = subprocess.run(extract_top_programs_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error extracting top programs: {result.stderr}")
        return

    print(f"Top {TOP_N} programs extracted to: {out_dir}")
    print("Task complete.")

if __name__ == '__main__':
    main()