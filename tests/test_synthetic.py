import copy

from procontrol.config import Config
from procontrol.synthetic import SyntheticGenerator, is_valid_ruc, ruc_check_digit, synthetic_ruc


def small_cfg():
    cfg = Config.load()
    cfg = copy.deepcopy(cfg)
    cfg.settings["synthetic"].update(n_buyers=6, n_suppliers=150, processes_per_buyer_year=40)
    return cfg


def test_ruc_check_digit_known_value():
    # 20100070970 is a widely published example RUC used in SUNAT documentation
    assert ruc_check_digit("2010007097") == 0


def test_synthetic_rucs_never_valid():
    import numpy as np

    rng = np.random.default_rng(1)
    assert not any(is_valid_ruc(synthetic_ruc("20", rng)) for _ in range(2000))


def test_generator_is_deterministic(tmp_path):
    a = SyntheticGenerator(small_cfg()).run(tmp_path / "a")
    b = SyntheticGenerator(small_cfg()).run(tmp_path / "b")
    assert a["releases"] == b["releases"]
    ga = (tmp_path / "a" / "ground_truth.csv").read_text().splitlines()
    gb = (tmp_path / "b" / "ground_truth.csv").read_text().splitlines()
    assert ga == gb and len(ga) > 1
