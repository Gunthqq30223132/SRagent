#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
GATES_YML = os.path.join(REPO_DIR, ".agents", "gates.yml")
TRACE_JSON = os.path.join(REPO_DIR, ".agents", "qc_trace.json")

FORBIDDEN_TIER3_PATHS = [
    ".agents/",
    "scripts/",
    "gates.yml",
    ".github/",
    "ci/"
]

TEST_PATH_PATTERNS = [
    "tests/",
    "test_",
    ".test.ts",
    ".test.js",
    ".spec.ts",
    ".spec.js"
]

def parse_simple_yaml(filepath):
    """Simple parser to read gates.yml without external dependencies."""
    config = {}
    current_section = None
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' in line:
                if line.endswith(':'):
                    current_section = line[:-1].strip()
                    config[current_section] = {}
                else:
                    parts = line.split(':', 1)
                    key = parts[0].strip()
                    val = parts[1].strip().strip('"').strip("'")
                    if current_section:
                        config[current_section][key] = val
                    else:
                        config[key] = val
    return config

def get_modified_files(patch_file=None):
    """Get list of modified file paths from a patch file or git diff."""
    files = []
    if patch_file and os.path.exists(patch_file):
        with open(patch_file, 'r') as f:
            for line in f:
                if line.startswith("+++ b/"):
                    files.append(line[6:].strip())
                elif line.startswith("--- a/") and not line.startswith("--- a/dev/null"):
                    files.append(line[6:].strip())
        return list(set(files))
    
    try:
        cmd = ["git", "status", "--porcelain"]
        res = subprocess.check_output(cmd, cwd=REPO_DIR).decode('utf-8', errors='ignore')
        for line in res.splitlines():
            line = line.strip()
            if line:
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1].strip())
    except Exception:
        pass
    return list(set(files))

def check_path_guard(modified_files, role=None):
    """Enforce Path Guard & Oracle rules on modified files."""
    violations = []
    for filepath in modified_files:
        norm_path = filepath.replace("\\", "/")
        
        # 1. Tier 3 protection: Lính patch touching infrastructure/gates/scripts
        for forbidden in FORBIDDEN_TIER3_PATHS:
            if norm_path.startswith(forbidden) or norm_path == "gates.yml" or f"/{forbidden}" in norm_path:
                violations.append(f"[Tier-3 Path Guard] Patch touched protected path: '{filepath}'")
                break
                
        # 2. Oracle Rule: Fixer role is forbidden from modifying test files
        if role == "fixer":
            is_test_file = any(tp in norm_path for tp in TEST_PATH_PATTERNS)
            if is_test_file:
                violations.append(f"[Oracle Rule Guard] Fixer role is forbidden from modifying test file: '{filepath}'")

    return violations

def run_command(name, command, timeout_s=60):
    print(f"[*] Running gate: {name} -> '{command}' (timeout={timeout_s}s)...")
    start_time = datetime.now()
    
    env = os.environ.copy()
    venv_bin_dir = os.path.join(REPO_DIR, ".venv", "bin")
    if os.path.exists(venv_bin_dir):
        env["PATH"] = venv_bin_dir + os.path.pathsep + env.get("PATH", "")
    
    try:
        process = subprocess.run(
            command,
            shell=True,
            cwd=REPO_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=timeout_s
        )
        duration = (datetime.now() - start_time).total_seconds()
        exit_code = process.returncode
        stdout = process.stdout.decode("utf-8", errors="ignore")[-2000:]
        stderr = process.stderr.decode("utf-8", errors="ignore")[-2000:]
    except subprocess.TimeoutExpired as te:
        duration = (datetime.now() - start_time).total_seconds()
        exit_code = 124
        stdout = te.stdout.decode("utf-8", errors="ignore")[-2000:] if te.stdout else ""
        stderr = f"TIMEOUT: Gate execution exceeded threshold of {timeout_s}s"
    
    result = {
        "name": name,
        "command": command,
        "exit_code": exit_code,
        "duration_seconds": duration,
        "stdout": stdout,
        "stderr": stderr,
        "status": "PASS" if exit_code == 0 else "FAIL"
    }
    
    if exit_code == 0:
        print(f"[+] Gate {name} PASSED ({duration:.2f}s)")
    else:
        print(f"[-] Gate {name} FAILED ({duration:.2f}s)")
        print(f"    Stderr snippet: {stderr[-300:].strip()}")
        
    return result

def main():
    parser = argparse.ArgumentParser(description="QC Harness with Path Guard & Gates Enforcement")
    parser.add_argument("--patch", help="Path to patch file to validate before execution")
    parser.add_argument("--role", choices=["worker", "fixer", "orchestrator"], default="worker", help="Role executing QC")
    parser.add_argument("--skip-path-guard", action="store_true", help="Skip path guard check (Orchestrator only)")
    args = parser.parse_args()

    # Pre-flight Path Guard
    if not args.skip_path_guard:
        modified_files = get_modified_files(args.patch)
        violations = check_path_guard(modified_files, role=args.role)
        if violations:
            print("----------------------------------------------------------------", file=sys.stderr)
            print("❌ QC HARNESS PRE-FLIGHT REJECTED (PATH GUARD / ORACLE RULE):", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            print("----------------------------------------------------------------", file=sys.stderr)
            sys.exit(1)

    if not os.path.exists(GATES_YML):
        print(f"[-] Error: gates.yml not found at {GATES_YML}", file=sys.stderr)
        sys.exit(1)
        
    config = parse_simple_yaml(GATES_YML)
    gates = config.get("quality_gates", {})
    clinical_gate = config.get("clinical_firewall")
    timeout_s = int(config.get("timeout_s", 60))
    
    trace = {
        "timestamp": datetime.now().isoformat() + "Z",
        "project": config.get("project", "Unknown"),
        "version": config.get("version", "0.0.0"),
        "results": [],
        "overall_status": "PASS"
    }
    
    failed = False
    
    for name, cmd in gates.items():
        res = run_command(name, cmd, timeout_s=timeout_s)
        trace["results"].append(res)
        if res["exit_code"] != 0:
            failed = True
            
    if clinical_gate:
        res = run_command("clinical_firewall", clinical_gate, timeout_s=timeout_s)
        trace["results"].append(res)
        if res["exit_code"] != 0:
            failed = True
            
    trace["overall_status"] = "FAIL" if failed else "PASS"
    
    os.makedirs(os.path.dirname(TRACE_JSON), exist_ok=True)
    with open(TRACE_JSON, "w") as f:
        json.dump(trace, f, indent=2)
        
    print(f"\n[*] QC Trace saved to {TRACE_JSON}")
    if failed:
        print("[-] Verification FAILED.")
        sys.exit(1)
    else:
        print("[+] Verification PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    main()
