import pytest

import config as config_module
import doconsole as dc


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never let tests read/write the real ~/.doconsole config."""
    monkeypatch.setattr(config_module, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_module, "HISTORY_PATH", str(tmp_path / "history"))


def _make_droplet(id_, name, tags=None, public_ip="1.2.3.4"):
    return {
        "id": id_,
        "name": name,
        "status": "active",
        "created_at": "2024-01-01T00:00:00Z",
        "memory": 1024,
        "vcpus": 1,
        "disk": 25,
        "kernel": None,
        "features": [],
        "tags": tags or [],
        "size_slug": "s-1vcpu-1gb",
        "networks": {
            "v4": [
                {"type": "public", "ip_address": public_ip, "netmask": "255.255.255.0", "gateway": "1.2.3.1"},
                {"type": "private", "ip_address": "10.0.0.2", "netmask": "255.255.255.0", "gateway": "10.0.0.1"},
            ]
        },
    }


class FakeAPI:
    def __init__(self):
        self.droplets = [
            _make_droplet(1, "web-1", tags=["prod"]),
            _make_droplet(2, "web-2", tags=["prod", "web"], public_ip="1.2.3.5"),
        ]
        self.destroyed = []
        self.tags_created = []
        self.tagged = []
        self.created_single = []
        self.created_multi = []
        self.firewalls_ensured = 0
        self.firewall_attachments = []
        self.snapshots = []
        self.snapshot_created = None
        self._next_id = 100

    def list_droplets(self):
        return self.droplets

    def destroy_droplet(self, droplet_id):
        self.destroyed.append(droplet_id)
        self.droplets = [d for d in self.droplets if d["id"] != droplet_id]

    def create_tag(self, name):
        self.tags_created.append(name)
        return {"name": name}

    def tag_resources(self, tag_name, droplet_ids):
        self.tagged.append((tag_name, list(droplet_ids)))

    def get_account(self):
        return {"email": "test@example.com"}

    def list_sizes(self):
        return [{"slug": "s-1vcpu-1gb", "price_hourly": 0.007, "price_monthly": 4.0}]

    def list_ssh_keys(self):
        return [{"id": 111}]

    def list_snapshots(self):
        return self.snapshots

    def create_snapshot(self, droplet_id, name, on_poll=None):
        snap = {"id": 999, "name": name, "regions": ["nyc1"], "min_disk_size": 25,
                "created_at": "2024-01-01T00:00:00Z"}
        self.snapshot_created = snap
        return snap

    def list_firewalls(self):
        return []

    def create_firewall(self, name, inbound_rules, outbound_rules, droplet_ids=None):
        return {"id": "fw-1", "name": name}

    def ensure_default_firewall(self, name="doconsole-ssh-only"):
        self.firewalls_ensured += 1
        return "fw-1"

    def add_droplets_to_firewall(self, firewall_id, droplet_ids):
        self.firewall_attachments.append((firewall_id, list(droplet_ids)))

    def create_droplet(self, name, region, size, image, ssh_key_ids, vpc_id=None, user_data=None, on_poll=None):
        droplet_id = self._next_id
        self._next_id += 1
        droplet = _make_droplet(droplet_id, name)
        self.droplets.append(droplet)
        self.created_single.append({"name": name, "image": image, "user_data": user_data})
        return droplet

    def create_droplets(self, names, region, size, image, ssh_key_ids, vpc_id=None, user_data=None, on_poll=None):
        results = []
        for name in names:
            droplet_id = self._next_id
            self._next_id += 1
            droplet = _make_droplet(droplet_id, name)
            self.droplets.append(droplet)
            results.append(droplet)
        self.created_multi.append(list(names))
        return results


def make_console(tmp_path):
    console = dc.DOConsole(token="fake", ssh_key="key", playbooks_dir=str(tmp_path))
    console.api = FakeAPI()
    return console


def test_show_droplets_lists_current_droplets(tmp_path, capsys):
    console = make_console(tmp_path)
    console.onecmd("show droplets")
    out = capsys.readouterr().out
    assert "web-1" in out
    assert "1.2.3.4" in out


def test_show_droplets_shows_estimated_cost(tmp_path, capsys):
    console = make_console(tmp_path)
    console.onecmd("show droplets")
    out = capsys.readouterr().out
    assert "Estimated running cost" in out


def test_refresh_droplets_does_not_duplicate(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.refresh_droplets()
    assert len(console.droplets) == 2


def test_set_droplet_by_index(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")
    assert console.target["Name"] == "web-1"
    assert "web-1" in console.prompt


def test_set_droplet_by_name(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet web-2")
    assert console.target["Name"] == "web-2"


def test_set_droplet_by_unknown_name_leaves_target_unset(tmp_path, capsys):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet nonexistent")
    out = capsys.readouterr().out
    assert "No droplet named" in out
    assert console.target is None


def test_set_droplet_by_tag_selects_multiple(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet tag:prod")
    assert console.target == "tag:prod"
    targets = console._target_droplets()
    assert {d["Name"] for d in targets} == {"web-1", "web-2"}


def test_set_droplet_by_tag_with_no_matches(tmp_path, capsys):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet tag:nope")
    out = capsys.readouterr().out
    assert "No droplets found with tag" in out
    assert console.target is None


def test_add_tag_creates_and_assigns(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")
    console.onecmd("add tag prod2")
    assert console.api.tags_created == ["prod2"]
    assert console.api.tagged == [("prod2", [1])]


def test_add_tag_to_tag_selection_tags_all_matches(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet tag:prod")
    console.onecmd("add tag extra")
    assert console.api.tagged == [("extra", [1, 2])]


def test_destroy_requires_confirmation(tmp_path, monkeypatch):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    console.onecmd("destroy")
    assert console.api.destroyed == [1]
    assert console.target is None


def test_destroy_cancelled_without_yes(tmp_path, monkeypatch):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")
    monkeypatch.setattr("builtins.input", lambda _: "no")
    console.onecmd("destroy")
    assert console.api.destroyed == []
    assert console.target is not None


def test_destroy_with_yes_flag_skips_confirmation(tmp_path, monkeypatch):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")

    def fail_if_called(_):
        raise AssertionError("input() should not be called with --yes")

    monkeypatch.setattr("builtins.input", fail_if_called)
    console.onecmd("destroy --yes")
    assert console.api.destroyed == [1]


def test_set_token_updates_client(tmp_path):
    console = make_console(tmp_path)
    console.onecmd("set token new-token")
    assert console.token == "new-token"


def test_set_firewall_toggle_persists(tmp_path):
    console = make_console(tmp_path)
    console.onecmd("set firewall off")
    assert console.config["attach_ssh_firewall"] is False


def test_create_droplet_attaches_default_firewall(tmp_path):
    console = make_console(tmp_path)
    console.onecmd("create droplet newbox")
    assert len(console.api.created_single) == 1
    assert console.api.firewalls_ensured == 1
    assert len(console.api.firewall_attachments) == 1


def test_create_droplet_no_firewall_flag_skips_attach(tmp_path):
    console = make_console(tmp_path)
    console.onecmd("create droplet newbox --no-firewall")
    assert console.api.firewalls_ensured == 0
    assert console.api.firewall_attachments == []


def test_create_droplet_count_creates_multiple(tmp_path):
    console = make_console(tmp_path)
    console.onecmd("create droplet web --count 3")
    assert console.api.created_multi == [["web-1", "web-2", "web-3"]]
    firewall_id, attached_ids = console.api.firewall_attachments[0]
    assert len(attached_ids) == 3


def test_create_droplet_with_ttl_schedules_lease(tmp_path, monkeypatch):
    console = make_console(tmp_path)
    calls = []
    monkeypatch.setattr(dc.ttl, "schedule_destroy", lambda token, did, name, secs: calls.append((did, name, secs)) or "2099-01-01T00:00:00")
    console.onecmd("create droplet newbox --ttl 2h")
    assert len(calls) == 1
    assert calls[0][2] == 7200


def test_create_snapshot_of_target(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")
    console.onecmd("create snapshot mysnap")
    assert console.api.snapshot_created["name"] == "mysnap"


def test_create_snapshot_requires_single_target(tmp_path, capsys):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet all")
    console.onecmd("create snapshot mysnap")
    out = capsys.readouterr().out
    assert "exactly one droplet" in out
    assert console.api.snapshot_created is None


def test_show_snapshots_populates_cache(tmp_path):
    console = make_console(tmp_path)
    console.api.snapshots = [{"id": 42, "name": "golden", "regions": ["nyc1"], "min_disk_size": 25,
                               "created_at": "2024-01-01T00:00:00Z"}]
    console.onecmd("show snapshots")
    assert console.snapshots == console.api.snapshots


def test_create_droplet_from_snapshot_index(tmp_path):
    console = make_console(tmp_path)
    console.snapshots = [{"id": 555, "name": "golden"}]
    console.onecmd("create droplet fromsnap --from-snapshot 0")
    assert console.api.created_single[0]["image"] == 555


def test_create_droplet_user_data_path_with_windows_backslashes(tmp_path, monkeypatch):
    monkeypatch.setattr(dc.os, "name", "nt")
    user_data_file = tmp_path / "init.sh"
    user_data_file.write_text("#!/bin/sh\necho hi\n")
    windows_style_path = str(user_data_file).replace("/", "\\")

    console = make_console(tmp_path)
    console.onecmd(f"create droplet fromfile --user-data {windows_style_path}")
    assert console.api.created_single[0]["user_data"] == "#!/bin/sh\necho hi\n"
