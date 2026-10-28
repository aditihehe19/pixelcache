"""Engine runner in isolation: parsing real engine output, failure paths with fakes."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import engine_runner as er
from tests.conftest import FIXTURES, requires_engine, small_config, wait_for

REAL = FIXTURES / "compare_64"   # produced by the real engine, see tests/fixtures


def test_parse_real_bench_output():
    rows, samples, system = er.parse_bench(REAL)
    assert {r.label for r in rows} == {"row_major", "morton", "tiled_16x16"}
    assert all(r.reps == 3 and r.output_matches_baseline is True for r in rows)
    assert all(r.hw_counters == "unavailable" for r in rows)
    assert len(samples) == 9
    assert system.get("cpu_brand")
    # summary statistics are reproducible from the stored repetitions
    for r in rows:
        reps = sorted(s.ms_per_run for s in samples if s.label == r.label)
        assert reps[1] == pytest.approx(r.median_ms, rel=1e-6)
        assert reps[0] == pytest.approx(r.min_ms, rel=1e-6)


def test_parse_real_sim_output():
    rows, geometry = er.parse_sim(REAL)
    assert {r.level for r in rows} == {"L1D", "L2", "L3"}
    assert all(r.source == "model" and r.misses <= r.accesses for r in rows)
    assert geometry["policy"].startswith("true LRU")


def test_malformed_output_is_an_error(tmp_path):
    shutil.copy(REAL / "samples_native.csv", tmp_path)
    (tmp_path / "bench_native.csv").write_text("suite,width\nsingle,notanumber\n", encoding="utf-8")
    with pytest.raises(er.EngineError, match="could not be parsed"):
        er.parse_bench(tmp_path)


def test_missing_output_is_an_error(tmp_path):
    with pytest.raises(er.EngineError, match="no benchmark summary"):
        er.parse_bench(tmp_path)


def test_refuses_unexpected_programs(tmp_path):
    with pytest.raises(er.EngineError, match="unexpected program"):
        er.run_process(Path("C:/Windows/System32/cmd.exe"), ["/c", "echo"], tmp_path, 5, tmp_path)
    with pytest.raises(er.EngineError, match="unexpected script"):
        er.run_process(Path(sys.executable), ["-c", "print(1)"], tmp_path, 5, tmp_path)


def test_rejects_bad_variant_tokens(tmp_path):
    with pytest.raises(er.EngineError):
        er.bench_single_args(op="yuv", mapping="identity", tokens=["row_major;rm -rf /"], width=64, height=64,
                             image_kind="gradient", reps=3, condition="warm", job_dir=tmp_path)


def test_timeout_is_reported(monkeypatch, tmp_path):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=k["timeout"], stderr="still running")
    monkeypatch.setattr(er.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    with pytest.raises(er.EngineError, match="exceeded the 7 s time limit"):
        er.run_process(settings.bench_bin, ["--sysinfo"], tmp_path, 7, tmp_path)


def test_nonzero_exit_is_reported(monkeypatch, tmp_path):
    secret = str(settings.repo_root / "private" / "x.ppm")
    monkeypatch.setattr(er.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a[0], 2, "", f"error: cannot read {secret}\n"))
    monkeypatch.setattr(Path, "exists", lambda self: True)
    with pytest.raises(er.EngineError) as e:
        er.run_process(settings.bench_bin, ["--single"], tmp_path, 7, tmp_path)
    assert "exited with code 2" in e.value.public
    assert str(settings.repo_root) not in e.value.detail   # internal paths are not exposed
    assert "<repo>" in e.value.detail


def test_failed_engine_job_is_persisted_with_error(client, monkeypatch):
    def failing(*a, **k):
        raise er.EngineError("cachevision_bench_native.exe exited with code 3.", "error: simulated failure")
    monkeypatch.setattr(er, "run_process", failing)
    r = client.post("/api/experiments", json=small_config())
    assert r.status_code == 202
    d = wait_for(client, r.json()["id"], timeout=30)
    assert d["status"] == "failed"
    assert "exited with code 3" in d["error_message"]
    assert d["results"] == []            # nothing fabricated on failure


@requires_engine
def test_engine_output_mismatch_is_detected(client, monkeypatch):
    real_parse = er.parse_bench

    def drop_a_row(job_dir, build_variant="native"):
        rows, samples, system = real_parse(job_dir, build_variant)
        return rows[:1], samples, system
    monkeypatch.setattr(er, "parse_bench", drop_a_row)
    r = client.post("/api/experiments/compare",
                    json=small_config(strategies=[{"strategy": "row_major"}, {"strategy": "morton"}]))
    d = wait_for(client, r.json()["id"], timeout=120)
    assert d["status"] == "failed"
    assert "does not match the requested strategies" in d["error_message"]
