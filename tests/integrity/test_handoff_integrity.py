"""交接包完整性双向断言（HANDOFF_DELTA 纪律）：

MANIFEST.sha256 的 mismatch 集合必须恰好等于 HANDOFF_DELTA.md 已登记的文件集合；
新增文件不得出现在 manifest 中，未登记的改动一律测试失败。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# HANDOFF_DELTA.md 已登记的、且属于 manifest 范围的修改文件（缺陷 1/2 修复）
REGISTERED_DELTA_FILES = {
    "05_tests/requirements-reference.txt",
    "05_tests/test_reference.py",
}


def test_manifest_mismatches_exactly_match_registered_delta():
    manifest = ROOT / "MANIFEST.sha256"
    mismatches = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        want, relative = line.split("  ", 1)
        path = (ROOT / relative).resolve()
        if not path.is_file():
            mismatches.add(relative + " (missing)")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != want:
            mismatches.add(relative)
    unexpected = mismatches - REGISTERED_DELTA_FILES
    unregistered_expectations = REGISTERED_DELTA_FILES - mismatches
    assert not unexpected, f"未登记的交接包改动: {sorted(unexpected)}"
    assert not unregistered_expectations, \
        f"HANDOFF_DELTA 登记的文件实际未改动（应更新登记表）: {sorted(unregistered_expectations)}"


def test_handoff_delta_document_lists_all_registered_files():
    text = (ROOT / "06_development/HANDOFF_DELTA.md").read_text(encoding="utf-8")
    for relative in REGISTERED_DELTA_FILES:
        assert relative in text, f"HANDOFF_DELTA.md 缺少 {relative} 的登记"
