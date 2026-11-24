import pytest

from terrain.catalog import PARTS, part_contract


@pytest.mark.parametrize("part", PARTS)
def test_every_parametric_part_has_an_export_contract(part):
    contract = part_contract(part)

    assert len(contract.extents) == 3
    assert all(dimension > 0 for dimension in contract.extents)
    assert contract.components == 1
    assert contract.degenerate_budget >= 0


def test_multi_body_parts_have_explicit_contracts():
    assert part_contract("coupon").components == 3
    assert part_contract("assembly").components == 7
    assert part_contract("e_floor").degenerate_budget == 20
    assert part_contract("assembly").degenerate_budget == 80
    assert "49 open edges" in part_contract("e_floor").baseline_notes[0]
    assert part_contract("coupon").baseline_notes
    assert part_contract("assembly").baseline_notes
