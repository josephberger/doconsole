import json

import pytest
import responses

from do_api import DOAPIClient, DOAPIError

BASE = "https://api.digitalocean.com/v2"


@responses.activate
def test_list_droplets():
    responses.add(
        responses.GET,
        f"{BASE}/droplets",
        json={"droplets": [{"id": 1, "name": "test"}], "links": {}},
        status=200,
    )
    client = DOAPIClient("fake-token")
    droplets = client.list_droplets()
    assert droplets == [{"id": 1, "name": "test"}]


@responses.activate
def test_auth_error_raises_doapierror():
    responses.add(
        responses.GET,
        f"{BASE}/account",
        json={"message": "Unable to authenticate you."},
        status=401,
    )
    client = DOAPIClient("bad-token")
    with pytest.raises(DOAPIError):
        client.get_account()


@responses.activate
def test_create_droplet_waits_for_active():
    responses.add(
        responses.POST,
        f"{BASE}/droplets",
        json={"droplet": {"id": 42, "name": "box", "status": "new"}},
        status=202,
    )
    responses.add(
        responses.GET,
        f"{BASE}/droplets/42",
        json={
            "droplet": {
                "id": 42,
                "name": "box",
                "status": "active",
                "networks": {"v4": [{"type": "public", "ip_address": "1.2.3.4"}]},
            }
        },
        status=200,
    )
    client = DOAPIClient("fake-token")
    droplet = client.create_droplet(
        name="box", region="nyc1", size="s-1vcpu-1gb", image="ubuntu-24-04-x64", ssh_key_ids=[]
    )
    assert droplet["status"] == "active"
    assert droplet["id"] == 42


@responses.activate
def test_create_droplet_times_out():
    responses.add(
        responses.POST,
        f"{BASE}/droplets",
        json={"droplet": {"id": 42, "name": "box", "status": "new"}},
        status=202,
    )
    responses.add(
        responses.GET,
        f"{BASE}/droplets/42",
        json={"droplet": {"id": 42, "name": "box", "status": "new", "networks": {"v4": []}}},
        status=200,
    )
    client = DOAPIClient("fake-token")
    with pytest.raises(DOAPIError):
        client.create_droplet(
            name="box", region="nyc1", size="s-1vcpu-1gb", image="ubuntu-24-04-x64",
            ssh_key_ids=[], wait_timeout=0,
        )


@responses.activate
def test_create_droplet_passes_user_data():
    captured = {}

    def request_callback(request):
        captured["body"] = json.loads(request.body)
        return (202, {}, json.dumps({"droplet": {"id": 5, "name": "box", "status": "new"}}))

    responses.add_callback(responses.POST, f"{BASE}/droplets", callback=request_callback,
                            content_type="application/json")
    responses.add(
        responses.GET,
        f"{BASE}/droplets/5",
        json={"droplet": {"id": 5, "name": "box", "status": "active",
                           "networks": {"v4": [{"type": "public", "ip_address": "1.2.3.4"}]}}},
        status=200,
    )
    client = DOAPIClient("fake-token")
    client.create_droplet(name="box", region="nyc1", size="s-1vcpu-1gb", image="ubuntu-24-04-x64",
                           ssh_key_ids=[], user_data="#cloud-config\n")
    assert captured["body"]["user_data"] == "#cloud-config\n"


@responses.activate
def test_create_droplets_bulk_waits_for_all():
    responses.add(
        responses.POST,
        f"{BASE}/droplets",
        json={"droplets": [{"id": 1, "name": "web-1", "status": "new"}, {"id": 2, "name": "web-2", "status": "new"}]},
        status=202,
    )
    responses.add(
        responses.GET,
        f"{BASE}/droplets/1",
        json={"droplet": {"id": 1, "name": "web-1", "status": "active",
                           "networks": {"v4": [{"type": "public", "ip_address": "1.1.1.1"}]}}},
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE}/droplets/2",
        json={"droplet": {"id": 2, "name": "web-2", "status": "active",
                           "networks": {"v4": [{"type": "public", "ip_address": "2.2.2.2"}]}}},
        status=200,
    )
    client = DOAPIClient("fake-token")
    droplets = client.create_droplets(names=["web-1", "web-2"], region="nyc1", size="s-1vcpu-1gb",
                                       image="ubuntu-24-04-x64", ssh_key_ids=[])
    assert [d["name"] for d in droplets] == ["web-1", "web-2"]


@responses.activate
def test_wait_for_action_completes():
    responses.add(responses.GET, f"{BASE}/actions/555", json={"action": {"id": 555, "status": "completed"}}, status=200)
    client = DOAPIClient("fake-token")
    action = client.wait_for_action(555)
    assert action["status"] == "completed"


@responses.activate
def test_wait_for_action_errored_raises():
    responses.add(responses.GET, f"{BASE}/actions/555", json={"action": {"id": 555, "status": "errored"}}, status=200)
    client = DOAPIClient("fake-token")
    with pytest.raises(DOAPIError):
        client.wait_for_action(555)


@responses.activate
def test_create_snapshot_finds_new_snapshot_by_name():
    responses.add(responses.POST, f"{BASE}/droplets/7/actions",
                  json={"action": {"id": 900, "status": "completed"}}, status=201)
    responses.add(responses.GET, f"{BASE}/actions/900", json={"action": {"id": 900, "status": "completed"}}, status=200)
    responses.add(
        responses.GET,
        f"{BASE}/droplets/7/snapshots",
        json={"snapshots": [{"id": 1, "name": "other"}, {"id": 2, "name": "my-snap"}], "links": {}},
        status=200,
    )
    client = DOAPIClient("fake-token")
    snapshot = client.create_snapshot(7, "my-snap")
    assert snapshot["id"] == 2


@responses.activate
def test_ensure_default_firewall_creates_when_missing():
    responses.add(responses.GET, f"{BASE}/firewalls", json={"firewalls": [], "links": {}}, status=200)
    responses.add(responses.POST, f"{BASE}/firewalls",
                  json={"firewall": {"id": "fw-1", "name": "doconsole-ssh-only"}}, status=202)
    client = DOAPIClient("fake-token")
    firewall_id = client.ensure_default_firewall()
    assert firewall_id == "fw-1"


@responses.activate
def test_ensure_default_firewall_reuses_existing():
    responses.add(
        responses.GET,
        f"{BASE}/firewalls",
        json={"firewalls": [{"id": "fw-9", "name": "doconsole-ssh-only"}], "links": {}},
        status=200,
    )
    client = DOAPIClient("fake-token")
    firewall_id = client.ensure_default_firewall()
    assert firewall_id == "fw-9"


@responses.activate
def test_create_ssh_key_posts_name_and_key():
    captured = {}

    def request_callback(request):
        captured["body"] = json.loads(request.body)
        return (201, {}, json.dumps({"ssh_key": {"id": 5, "name": "doconsole-test", "fingerprint": "aa:bb"}}))

    responses.add_callback(responses.POST, f"{BASE}/account/keys", callback=request_callback,
                            content_type="application/json")
    client = DOAPIClient("fake-token")
    key = client.create_ssh_key("doconsole-test", "ssh-ed25519 AAAAC3 comment")
    assert captured["body"] == {"name": "doconsole-test", "public_key": "ssh-ed25519 AAAAC3 comment"}
    assert key["id"] == 5


@responses.activate
def test_droplet_action_posts_type():
    captured = {}

    def request_callback(request):
        captured["body"] = json.loads(request.body)
        return (201, {}, json.dumps({"action": {"id": 1, "status": "in-progress", "type": "reboot"}}))

    responses.add_callback(responses.POST, f"{BASE}/droplets/9/actions", callback=request_callback,
                            content_type="application/json")
    client = DOAPIClient("fake-token")
    action = client.droplet_action(9, "reboot")
    assert captured["body"] == {"type": "reboot"}
    assert action["type"] == "reboot"


@responses.activate
def test_resize_droplet_posts_size_and_disk_flag():
    captured = {}

    def request_callback(request):
        captured["body"] = json.loads(request.body)
        return (201, {}, json.dumps({"action": {"id": 2, "status": "in-progress", "type": "resize"}}))

    responses.add_callback(responses.POST, f"{BASE}/droplets/9/actions", callback=request_callback,
                            content_type="application/json")
    client = DOAPIClient("fake-token")
    client.resize_droplet(9, "s-2vcpu-2gb", disk=True)
    assert captured["body"] == {"type": "resize", "size": "s-2vcpu-2gb", "disk": True}


@responses.activate
def test_pagination_follows_next_link():
    next_url = f"{BASE}/regions-page-2"
    responses.add(
        responses.GET,
        f"{BASE}/regions",
        json={"regions": [{"slug": "nyc1"}], "links": {"pages": {"next": next_url}}},
        status=200,
    )
    responses.add(
        responses.GET,
        next_url,
        json={"regions": [{"slug": "sfo3"}], "links": {"pages": {}}},
        status=200,
    )
    client = DOAPIClient("fake-token")
    regions = client.list_regions()
    assert [r["slug"] for r in regions] == ["nyc1", "sfo3"]
