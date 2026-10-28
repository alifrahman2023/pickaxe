#!/usr/bin/env python3
"""Update a Pickaxe PR's title/body through gh REST, preserving its lifecycle."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('number', type=int)
parser.add_argument('--title', required=True)
parser.add_argument('--body-file', type=Path, required=True)
args = parser.parse_args()
if args.number <= 0:
    parser.error('PR number must be positive')
payload = json.dumps({'title': args.title, 'body': args.body_file.read_text()}).encode()
raise SystemExit(subprocess.run([
    'gh', 'api', '--method', 'PATCH', f'repos/alifrahman2023/pickaxe/pulls/{args.number}',
    '--input', '-', '--jq', '{html_url,state,draft,title,head_sha:.head.sha}',
], input=payload).returncode)
