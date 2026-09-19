"""单位边界测试：金额、时间、等候费、映射结构（§9.1/§6.2）。"""
from __future__ import annotations

import pytest

from freight_core.errors import InvalidInput
from freight_core.money import bounded_int, calculate_wait, instant, yuan_to_minor
from freight_core.mapping.service import structure_digest


# ---- 金额边界（与参考引擎对齐）----
def test_money_decimal_string():
    assert yuan_to_minor("1050.09") == 105009


def test_money_negative():
    assert yuan_to_minor("-100.50") == -10050


def test_money_float_rejected():
    with pytest.raises(InvalidInput):
        yuan_to_minor(0.1)


def test_money_three_decimals_rejected():
    with pytest.raises(InvalidInput):
        yuan_to_minor("1.001")


def test_money_exponent_rejected():
    with pytest.raises(InvalidInput):
        yuan_to_minor("1e3")


def test_money_nan_rejected():
    with pytest.raises(InvalidInput):
        yuan_to_minor("NaN")


def test_money_limit_rejected():
    with pytest.raises(InvalidInput):
        yuan_to_minor("10000000000.01")


def test_bounded_int_bool_rejected():
    with pytest.raises(InvalidInput):
        bounded_int(True)


def test_bounded_int_float_rejected():
    with pytest.raises(InvalidInput):
        bounded_int(1.0)


# ---- 时间边界 ----
def test_instant_requires_timezone():
    with pytest.raises(InvalidInput):
        instant("2026-09-01T08:00:00")
    assert instant("2026-09-01T08:00:00+08:00").tzinfo is not None
    assert instant("2026-09-01T08:00:00Z").tzinfo is not None


# ---- 等候费边界（§9.3 示例）----
def test_wait_golden_example():
    # 在场180分钟，免费120，每30分钟50元 → 100元
    assert calculate_wait(10800, 7200, 1800, 5000) == 10000


def test_wait_free_exact_zero():
    assert calculate_wait(7200, 7200, 1800, 5000) == 0


def test_wait_below_free_zero():
    assert calculate_wait(7199, 7200, 1800, 5000) == 0


def test_wait_one_second_one_block():
    assert calculate_wait(7201, 7200, 1800, 5000) == 5000  # 不由模型四舍五入


def test_wait_exact_block_boundary():
    assert calculate_wait(9000, 7200, 1800, 5000) == 5000
    assert calculate_wait(9001, 7200, 1800, 5000) == 10000


def test_wait_zero_block_rejected():
    with pytest.raises(InvalidInput):
        calculate_wait(9000, 7200, 0, 5000)


def test_wait_negative_rejected():
    with pytest.raises(InvalidInput):
        calculate_wait(-1, 0, 1800, 5000)


# ---- 映射结构签名（§6.2）----
def test_mapping_structure_digest_changes_with_header():
    a = structure_digest("bill", ["line_id", "amount_minor"])
    b = structure_digest("bill", ["line_id", "amount_minor", "extra"])
    assert a != b


def test_mapping_digest_independent_of_kind_order():
    assert structure_digest("bill", ["a", "b"]) != structure_digest("trips", ["a", "b"])
