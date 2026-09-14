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
