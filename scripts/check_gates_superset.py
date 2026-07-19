#!/usr/bin/env python3
import os
import sys
import yaml

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
GATES_YML = os.path.join(REPO_DIR, ".agents", "gates.yml")

# Standard required gates per project instance
REQUIRED_GATES = {
    "SRagent": [
        "secret_scan",
        "lint_boundary",
        "test_suite",
        "compliance_check",
        "clinical_firewall"
    ],
    "AnesthOS": [
        "secret_scan",
        "lint_boundary",
        "test_suite",
        "compliance_check",
        "clinical_firewall"
    ],
    "AnesthOS-app": [
        "secret_scan",
        "lint_boundary",
        "build",
        "test",
        "test_coverage"
    ]
}

def parse_yaml(filepath):
    try:
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        # Fallback simple parser
        config = {}
        curr = None
        with open(filepath, 'r') as f:
            for line in f:
                l = line.strip()
                if not l or l.startswith('#'): continue
                if ':' in l:
                    if l.endswith(':'):
                        curr = l[:-1].strip()
                        config[curr] = {}
                    else:
                        k, v = l.split(':', 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if curr: config[curr][k] = v
                        else: config[k] = v
        return config

def main():
    if not os.path.exists(GATES_YML):
        print(f"[-] Error: {GATES_YML} missing.", file=sys.stderr)
        sys.exit(1)

    config = parse_yaml(GATES_YML) or {}
    project = config.get("project", "")
    quality_gates = config.get("quality_gates", {})
    if isinstance(quality_gates, dict):
        present_gates = set(quality_gates.keys())
    else:
        present_gates = set()

    if config.get("clinical_firewall"):
        present_gates.add("clinical_firewall")
    if config.get("tier_top_verify"):
        present_gates.add("tier_top_verify")

    required = set(REQUIRED_GATES.get(project, []))
    if not required:
        # Default fallback required gates
        required = {"secret_scan", "lint_boundary", "build", "test"}

    missing = required - present_gates
    if missing:
        print(f"❌ CI Gate-Compare FAILED: gates.yml in '{project}' is missing required gates: {sorted(list(missing))}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"✅ CI Gate-Compare PASSED: gates.yml in '{project}' satisfies all required standard gates: {sorted(list(required))}")
        sys.exit(0)

if __name__ == "__main__":
    main()
