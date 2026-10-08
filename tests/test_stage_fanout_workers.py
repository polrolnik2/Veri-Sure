"""`SPECFLOW_FANOUT_WORKERS` sets the fan-out width; anything else keeps 4."""
import threading
import time

from specflow import stage


def _peak(monkeypatch, value, n_items=12):
    if value is None:
        monkeypatch.delenv("SPECFLOW_FANOUT_WORKERS", raising=False)
    else:
        monkeypatch.setenv("SPECFLOW_FANOUT_WORKERS", value)
    live, peak, lock = [0], [0], threading.Lock()

    def one(_x):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return _x

    out = stage.run_fanout(list(range(n_items)), one, warmup=0)
    assert out == list(range(n_items))
    return peak[0]


def test_default_width_is_unchanged(monkeypatch):
    assert _peak(monkeypatch, None) == stage.FANOUT_WORKERS == 4


def test_the_environment_widens_the_pool(monkeypatch):
    assert _peak(monkeypatch, "10") == 10


def test_nonsense_falls_back_to_the_default(monkeypatch):
    assert _peak(monkeypatch, "zero") == 4
    assert _peak(monkeypatch, "-3") == 4
