"""Verify only the files enumerated in MANIFEST.sha256. No network requests."""
from pathlib import Path
import hashlib, sys
root=Path(__file__).resolve().parents[1]
manifest=root/'MANIFEST.sha256'
if not manifest.is_file():raise SystemExit('Missing MANIFEST.sha256')
fail=[];count=0
for line in manifest.read_text(encoding='utf-8').splitlines():
    if not line.strip():continue
    want,relative=line.split('  ',1)
    path=(root/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():fail.append(relative+' (missing/unsafe)');continue
    count+=1
    if hashlib.sha256(path.read_bytes()).hexdigest()!=want:fail.append(relative+' (hash mismatch)')
print(f'Checked {count} files; mismatches: {len(fail)}')
for f in fail:print(f)
raise SystemExit(1 if fail else 0)
