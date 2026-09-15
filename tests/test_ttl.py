import subprocess

import pytest

import ttl


class FakePopen:
    def __init__(self, *args, **kwargs):
        self.pid = 12345


@pytest.fixture(autouse=True)
def isolated_leases(tmp_path, monkeypatch):
    monkeypatch.setattr(ttl, "LEASES_PATH", str(tmp_path / "leases.json"))
    monkeypatch.setattr(ttl.config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(subprocess, "Popen", FakePopen)


def test_parse_duration_variants():
    assert ttl.parse_duration("90m") == 5400
    assert ttl.parse_duration("2h") == 7200
    assert ttl.parse_duration("1d") == 86400
    assert ttl.parse_duration("30s") == 30


def test_parse_duration_invalid():
    with pytest.raises(ValueError):
        ttl.parse_duration("banana")


def test_schedule_list_and_cancel_roundtrip():
    expires_at = ttl.schedule_destroy("tok", 42, "my-box", 3600)
    assert expires_at

    leases = ttl.list_leases()
    assert len(leases) == 1
    assert leases[0]["name"] == "my-box"
    assert leases[0]["droplet_id"] == "42"
    assert leases[0]["seconds_remaining"] > 0

    assert ttl.cancel_lease("my-box") is True
    assert ttl.list_leases() == []


def test_cancel_by_droplet_id():
    ttl.schedule_destroy("tok", 7, "other-box", 60)
    assert ttl.cancel_lease("7") is True
    assert ttl.list_leases() == []


def test_cancel_unknown_lease_returns_false():
    assert ttl.cancel_lease("does-not-exist") is False


def test_stale_lease_detected_when_watcher_process_is_dead(monkeypatch):
    monkeypatch.setattr(ttl, "_pid_alive", lambda pid: False)
    ttl.schedule_destroy("tok", 1, "dead-watcher-box", 3600)
    leases = ttl.list_leases()
    assert leases[0]["stale"] is True


def test_not_stale_when_watcher_process_is_alive(monkeypatch):
    monkeypatch.setattr(ttl, "_pid_alive", lambda pid: True)
    ttl.schedule_destroy("tok", 1, "alive-watcher-box", 3600)
    leases = ttl.list_leases()
    assert leases[0]["stale"] is False
