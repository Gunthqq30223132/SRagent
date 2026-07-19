#!/usr/bin/env python3
import sys
import os
import re
import json
import fnmatch
import subprocess

# Read staged files from stdin
staged_files = [line.strip() for line in sys.stdin if line.strip()]
if not staged_files:
    sys.exit(0)

EMAIL_REGEX = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')
ID_REGEX = re.compile(r'\b\d{9}\b|\b\d{12}\b')
PHONE_REGEX = re.compile(r'(?<!\d)(?:\+?\d{1,3}[- .]?)?\(?\d{2,4}\)?[- .]?\d{3,4}[- .]?\d{3,4}\b')

def get_staged_content(filepath):
    try:
        return subprocess.check_output(['git', 'show', f':{filepath}'])
    except Exception:
        return None

def is_binary(content_bytes):
    return b'\0' in content_bytes

def should_skip_checks(filepath):
    skip_extensions = {
        '.lock', '-lock.json', '.png', '.jpg', '.jpeg', '.gif', '.ico',
        '.pdf', '.zip', '.gz', '.tar', '.mp4', '.woff', '.woff2', '.ttf', '.eot'
    }
    lower_path = filepath.lower()
    for ext in skip_extensions:
        if lower_path.endswith(ext):
            return True
    if 'package-lock.json' in lower_path:
        return True
    return False

def check_package_json(filepath):
    try:
        old_content = subprocess.check_output(['git', 'show', f'HEAD:{filepath}'], stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        old_data = json.loads(old_content)
    except Exception:
        old_data = {}

    try:
        new_content = subprocess.check_output(['git', 'show', f':{filepath}']).decode('utf-8', errors='ignore')
        new_data = json.loads(new_content)
    except Exception as e:
        return [f"Failed to parse staged {filepath}: {e}"]

    def get_all_deps(data):
        deps = {}
        for key in ['dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies']:
            if key in data and isinstance(data[key], dict):
                deps.update(data[key])
        return deps

    old_deps = get_all_deps(old_data)
    new_deps = get_all_deps(new_data)

    added_deps = [pkg for pkg in new_deps if pkg not in old_deps]

    approved_patterns = [
        'next',
        'react',
        'react-dom',
        'tailwindcss',
        'lucide-react',
        'better-sqlite3',
        'sqlite3',
        'typescript',
        'eslint',
        'postcss',
        'autoprefixer',
        'jest',
        '@radix-ui/*',
        '@types/*',
        'prettier',
        'eslint-config-next',
        'eslint-plugin-*',
        'ts-jest',
        '@testing-library/*',
        'postcss-*',
        'globals',
        '@eslint/*',
        'typescript-eslint',
    ]

    def is_approved(pkg):
        for pattern in approved_patterns:
            if fnmatch.fnmatch(pkg, pattern):
                return True
        return False

    unapproved = [pkg for pkg in added_deps if not is_approved(pkg)]
    if unapproved:
        return [f"Unapproved npm packages added to {filepath}: {', '.join(unapproved)}"]
    
    return []

def check_pii(filepath, content):
    errs = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        emails = EMAIL_REGEX.findall(line)
        if emails:
            errs.append(f"PII (Email) found in '{filepath}' line {idx}: {', '.join(emails)}")
            
        ids = ID_REGEX.findall(line)
        if ids:
            errs.append(f"PII (National ID) found in '{filepath}' line {idx}: {', '.join(ids)}")

        phones = PHONE_REGEX.findall(line)
        valid_phones = []
        for p in phones:
            digits = re.sub(r'\D', '', p)
            if 9 <= len(digits) <= 12:
                if p.startswith('+') or p.startswith('0') or p.startswith('(') or p.startswith('84'):
                    valid_phones.append(p)
                elif len(digits) == 10 and digits.startswith('84'):
                    valid_phones.append(p)
        if valid_phones:
            errs.append(f"PII (Phone) found in '{filepath}' line {idx}: {', '.join(valid_phones)}")
            
    return errs

def check_latex_comments(filepath, content):
    CLINICAL_KEYWORDS = ["dose", "calculation", "formula", "dosing", "infusion", "weight-based"]
    CLINICAL_DIRS = ["calculations", "math", "formula", "clinical", "medication", "dosing", "calc"]
    
    is_clinical = False
    path_parts = filepath.lower().split('/')
    for part in path_parts[:-1]:
        for d_kw in CLINICAL_DIRS:
            if d_kw in part:
                is_clinical = True
                break
        if is_clinical:
            break
            
    if not is_clinical:
        content_lower = content.lower()
        for kw in CLINICAL_KEYWORDS:
            if kw in content_lower:
                is_clinical = True
                break
                
    if is_clinical:
        LATEX_REGEX = re.compile(r'\$[A-Za-z0-9_ += \\times \\div \\cdot * / \- \(\) \^ \{ \} \[ \] \. , \\ ]+\$')
        if not LATEX_REGEX.search(content):
            return [
                f"File '{filepath}' contains clinical calculation reference but lacks a LaTeX comment (matching '$...$')."
            ]
    return []

def check_secrets(filepath, content):
    SECRET_REGEXES = [
        re.compile(r'\bsk-[a-zA-Z0-9_-]{16,}\b'),
        re.compile(r'\bBearer\s+[a-zA-Z0-9_\-\.]{16,}\b'),
        re.compile(r'\bAIzaSy[A-Za-z0-9_-]{33}\b'),
        re.compile(r'(?i)(?:secret|api)_?(?:key|token|secret)\s*[:=]\s*["\'\u201d\u201c][a-zA-Z0-9_\-\.\@\/]{8,}[\"\'\u201d\u201c]'),
        re.compile(r'(?i)[\"\'\u201d\u201c]\w*(?:secret|api)_?(?:key|token|secret)\w*[\"\'\u201d\u201c]\s*:\s*[\"\'\u201d\u201c][a-zA-Z0-9_\-\.\@\/]{8,}[\"\'\u201d\u201c]')
    ]
    errs = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        for p in SECRET_REGEXES:
            m = p.search(line)
            if m:
                secret = m.group(0)
                masked = secret[:6] + "..." + secret[-4:] if len(secret) > 10 else "..."
                errs.append(f"Secret Key pattern found in '{filepath}' line {idx}: {masked}")
                break
    return errs

errors = []
for filepath in staged_files:
    if os.path.basename(filepath) == 'package.json':
        errs = check_package_json(filepath)
        errors.extend(errs)
        continue

    if should_skip_checks(filepath):
        continue

    content_bytes = get_staged_content(filepath)
    if content_bytes is None:
        continue

    if is_binary(content_bytes):
        continue

    try:
        content = content_bytes.decode('utf-8')
    except UnicodeDecodeError:
        continue

    errors.extend(check_pii(filepath, content))
    errors.extend(check_latex_comments(filepath, content))
    errors.extend(check_secrets(filepath, content))

if errors:
    print("----------------------------------------------------------------", file=sys.stderr)
    print("COMMIT BLOCKED BY SAFETY PRE-COMMIT HOOK:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    print("----------------------------------------------------------------", file=sys.stderr)
    sys.exit(1)

sys.exit(0)
