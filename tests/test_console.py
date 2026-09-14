import doconsole as dc


class FakeAPI:
    def __init__(self):
        self.droplets = [
            {
                "id": 1,
                "name": "web-1",
                "status": "active",
                "created_at": "2024-01-01T00:00:00Z",
                "memory": 1024,
                "vcpus": 1,
                "disk": 25,
                "kernel": None,
                "features": [],
                "tags": [],
                "size_slug": "s-1vcpu-1gb",
                "networks": {
                    "v4": [
                        {"type": "public", "ip_address": "1.2.3.4", "netmask": "255.255.255.0", "gateway": "1.2.3.1"},
                        {"type": "private", "ip_address": "10.0.0.2", "netmask": "255.255.255.0", "gateway": "10.0.0.1"},
                    ]
                },
            }
        ]
        self.destroyed = []
        self.tags_created = []
        self.tagged = []

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


def test_refresh_droplets_does_not_duplicate(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.refresh_droplets()
    assert len(console.droplets) == 1


def test_set_droplet_by_index(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")
    assert console.target["Name"] == "web-1"
    assert "web-1" in console.prompt


def test_add_tag_creates_and_assigns(tmp_path):
    console = make_console(tmp_path)
    console.refresh_droplets()
    console.onecmd("set droplet 0")
    console.onecmd("add tag prod")
    assert console.api.tags_created == ["prod"]
    assert console.api.tagged == [("prod", [1])]


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


def test_set_token_updates_client(tmp_path):
    console = make_console(tmp_path)
    console.onecmd("set token new-token")
    assert console.token == "new-token"
