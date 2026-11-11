from __future__ import annotations

import pytest

from custom_components.factusol.calibration import fit_pairs


def test_recovers_scale_and_offset() -> None:
    pairs = [(x, 1.05 * x + 2.0) for x in range(0, 500, 5)]
    fit = fit_pairs(pairs)
    assert fit is not None
    assert fit.factor_ls == pytest.approx(1.05)
    assert fit.offset_wh == pytest.approx(2.0)
    assert fit.r2 == pytest.approx(1.0)
    assert fit.desfase_pct < 0  # la pinza lee de menos
    assert fit.factor == pytest.approx(fit.oficial_kwh / fit.propio_kwh)


def test_too_few_hours_gives_no_fit() -> None:
    assert fit_pairs([(1.0, 1.0)] * 5) is None


def test_degenerate_input_keeps_unity() -> None:
    fit = fit_pairs([(0.0, 0.0)] * 30)
    assert fit is not None
    assert fit.factor == 1.0 and fit.factor_ls == 1.0
