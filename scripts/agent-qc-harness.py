#!/usr/bin/env python3
import os
import sys
import json
import subprocess
from datetime import datetime

# Path definition
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
GATES_YML = os.path.join(REPO_DIR, ".agents", "gates.yml")
TRACE_JSON = os.path.join(REPO_DIR, ".agents", "qc_trace.json")

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

def run_command(name, command):
    print(f"[*] Running gate: {name} -> '{command}'...")
    start_time = datetime.now()
    
    # Prepend .venv/bin to PATH to resolve virtualenv executables
    env = os.environ.copy()
    venv_bin_dir = os.path.join(REPO_DIR, ".venv", "bin")
    if os.path.exists(venv_bin_dir):
        env["PATH"] = venv_bin_dir + os.path.pathsep + env.get("PATH", "")
    
    # Run in repo root
    process = subprocess.run(
        command,
        shell=True,
        cwd=REPO_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    result = {
        "name": name,
        "command": command,
        "exit_code": process.returncode,
        "duration_seconds": duration,
        "stdout": process.stdout.decode("utf-8", errors="ignore")[-2000:], # Cap logs to prevent massive trace files
        "stderr": process.stderr.decode("utf-8", errors="ignore")[-2000:],
        "status": "PASS" if process.returncode == 0 else "FAIL"
    }
    
    if process.returncode == 0:
        print(f"[+] Gate {name} PASSED ({duration:.2f}s)")
    else:
        print(f"[-] Gate {name} FAILED ({duration:.2f}s)")
        print(f"    Stderr snippet: {result['stderr'][-300:].strip()}")
        
    return result

def main():
    if not os.path.exists(GATES_YML):
        print(f"[-] Error: gates.yml not found at {GATES_YML}")
        sys.exit(1)
        
    config = parse_simple_yaml(GATES_YML)
    gates = config.get("quality_gates", {})
    clinical_gate = config.get("clinical_firewall")
    
    # Use timezone-aware UTC datetime or standard formatting
    trace = {
        "timestamp": datetime.now().isoformat() + "Z",
        "project": config.get("project", "Unknown"),
        "version": config.get("version", "0.0.0"),
        "results": [],
        "overall_status": "PASS"
    }
    
    failed = False
    
    # Run core quality gates
    for name, cmd in gates.items():
        res = run_command(name, cmd)
        trace["results"].append(res)
        if res["exit_code"] != 0:
            failed = True
            
    # Run clinical firewall if configured
    if clinical_gate:
        res = run_command("clinical_firewall", clinical_gate)
        trace["results"].append(res)
        if res["exit_code"] != 0:
            failed = True
            
    trace["overall_status"] = "FAIL" if failed else "PASS"
    
    # Write trace file
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
