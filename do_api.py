import time

import requests

API_BASE = "https://api.digitalocean.com/v2"
REQUEST_TIMEOUT = 30
CREATE_DROPLET_TIMEOUT = 300

# Allow all outbound traffic - used as the default outbound policy for
# every firewall this tool creates (the point of these firewalls is
# restricting inbound access, not outbound).
DEFAULT_OUTBOUND_RULES = [
    {"protocol": "tcp", "ports": "1-65535", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
    {"protocol": "udp", "ports": "1-65535", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
    {"protocol": "icmp", "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}},
]


class DOAPIError(Exception):
    """Raised for any failure talking to the DigitalOcean API."""


class DOAPIClient:
    """Thin wrapper around the DigitalOcean REST API v2."""

    def __init__(self, token, base_url=API_BASE, timeout=REQUEST_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def _raise_for_status(self, resp):
        if resp.status_code == 401:
            raise DOAPIError("Authentication failed. Please check the API token.")
        if not resp.ok:
            message = resp.reason
            try:
                message = resp.json().get("message", message)
            except ValueError:
                pass
            raise DOAPIError(f"DigitalOcean API error ({resp.status_code}): {message}")

    def _request(self, method, path, params=None, json=None):
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, params=params, json=json, timeout=self.timeout)
        except requests.RequestException as e:
            raise DOAPIError(f"Network error calling DigitalOcean API: {e}") from e

        self._raise_for_status(resp)

        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def _get_paginated(self, path, key, params=None):
        items = []
        url = f"{self.base_url}{path}"
        request_params = dict(params or {})
        request_params.setdefault("per_page", 200)

        while url:
            try:
                resp = self.session.get(url, params=request_params, timeout=self.timeout)
            except requests.RequestException as e:
                raise DOAPIError(f"Network error calling DigitalOcean API: {e}") from e

            self._raise_for_status(resp)
            data = resp.json() if resp.content else {}
            items.extend(data.get(key, []))

            url = data.get("links", {}).get("pages", {}).get("next")
            request_params = None

        return items

    def list_droplets(self):
        return self._get_paginated("/droplets", "droplets")

    def get_droplet(self, droplet_id):
        return self._request("GET", f"/droplets/{droplet_id}")["droplet"]

    def _build_create_body(self, region, size, image, ssh_key_ids, vpc_id=None, user_data=None):
        body = {
            "region": region,
            "size": size,
            "image": image,
            "ssh_keys": ssh_key_ids,
            "backups": False,
        }
        if vpc_id:
            body["vpc_uuid"] = vpc_id
        if user_data:
            body["user_data"] = user_data
        return body

    def create_droplet(self, name, region, size, image, ssh_key_ids, vpc_id=None, user_data=None,
                        wait_timeout=CREATE_DROPLET_TIMEOUT, on_poll=None):
        body = self._build_create_body(region, size, image, ssh_key_ids, vpc_id, user_data)
        body["name"] = name

        droplet = self._request("POST", "/droplets", json=body)["droplet"]
        droplet_id = droplet["id"]

        deadline = time.monotonic() + wait_timeout
        while True:
            droplet = self.get_droplet(droplet_id)
            if droplet.get("status") == "active" and droplet.get("networks", {}).get("v4"):
                return droplet
            if time.monotonic() > deadline:
                raise DOAPIError(f"Timed out waiting for droplet '{name}' to become active.")
            if on_poll:
                on_poll()
            time.sleep(2)

    def create_droplets(self, names, region, size, image, ssh_key_ids, vpc_id=None, user_data=None,
                         wait_timeout=CREATE_DROPLET_TIMEOUT, on_poll=None):
        body = self._build_create_body(region, size, image, ssh_key_ids, vpc_id, user_data)
        body["names"] = names

        created = self._request("POST", "/droplets", json=body)["droplets"]
        droplet_ids = [d["id"] for d in created]

        deadline = time.monotonic() + wait_timeout
        results = {}
        while len(results) < len(droplet_ids):
            for droplet_id in droplet_ids:
                if droplet_id in results:
                    continue
                droplet = self.get_droplet(droplet_id)
                if droplet.get("status") == "active" and droplet.get("networks", {}).get("v4"):
                    results[droplet_id] = droplet
            if len(results) < len(droplet_ids):
                if time.monotonic() > deadline:
                    raise DOAPIError(f"Timed out waiting for droplets {names} to become active.")
                if on_poll:
                    on_poll()
                time.sleep(2)

        return [results[droplet_id] for droplet_id in droplet_ids]

    def destroy_droplet(self, droplet_id):
        self._request("DELETE", f"/droplets/{droplet_id}")

    def droplet_action(self, droplet_id, action_type):
        return self._request("POST", f"/droplets/{droplet_id}/actions", json={"type": action_type})["action"]

    def resize_droplet(self, droplet_id, size, disk=False):
        return self._request("POST", f"/droplets/{droplet_id}/actions",
                              json={"type": "resize", "size": size, "disk": disk})["action"]

    def get_action(self, action_id):
        return self._request("GET", f"/actions/{action_id}")["action"]

    def wait_for_action(self, action_id, timeout=300, on_poll=None):
        deadline = time.monotonic() + timeout
        while True:
            action = self.get_action(action_id)
            status = action.get("status")
            if status == "completed":
                return action
            if status == "errored":
                raise DOAPIError(f"Action {action_id} errored.")
            if time.monotonic() > deadline:
                raise DOAPIError(f"Timed out waiting for action {action_id}.")
            if on_poll:
                on_poll()
            time.sleep(2)

    def create_snapshot(self, droplet_id, name, wait_timeout=300, on_poll=None):
        action = self._request("POST", f"/droplets/{droplet_id}/actions",
                                json={"type": "snapshot", "name": name})["action"]
        self.wait_for_action(action["id"], timeout=wait_timeout, on_poll=on_poll)

        for snapshot in self.list_droplet_snapshots(droplet_id):
            if snapshot.get("name") == name:
                return snapshot
        raise DOAPIError(f"Snapshot '{name}' completed but could not be found afterward.")

    def list_droplet_snapshots(self, droplet_id):
        return self._get_paginated(f"/droplets/{droplet_id}/snapshots", "snapshots")

    def list_snapshots(self):
        return self._get_paginated("/snapshots", "snapshots", params={"resource_type": "droplet"})

    def list_firewalls(self):
        return self._get_paginated("/firewalls", "firewalls")

    def create_firewall(self, name, inbound_rules, outbound_rules, droplet_ids=None, tags=None):
        body = {
            "name": name,
            "inbound_rules": inbound_rules,
            "outbound_rules": outbound_rules,
        }
        if droplet_ids:
            body["droplet_ids"] = droplet_ids
        if tags:
            body["tags"] = tags
        return self._request("POST", "/firewalls", json=body)["firewall"]

    def add_droplets_to_firewall(self, firewall_id, droplet_ids):
        self._request("POST", f"/firewalls/{firewall_id}/droplets", json={"droplet_ids": droplet_ids})

    def ensure_default_firewall(self, name="doconsole-ssh-only", tag=None):
        """Find-or-create the shared SSH-only firewall. If `tag` is given, the firewall is
        created targeting that tag (DO applies it to any droplet carrying the tag, present
        or future - no per-droplet attach call needed); an existing firewall found by name
        is reused as-is either way."""
        for firewall in self.list_firewalls():
            if firewall.get("name") == name:
                return firewall["id"]

        inbound_rules = [{
            "protocol": "tcp",
            "ports": "22",
            "sources": {"addresses": ["0.0.0.0/0", "::/0"]},
        }]
        firewall = self.create_firewall(name, inbound_rules, DEFAULT_OUTBOUND_RULES,
                                         tags=[tag] if tag else None)
        return firewall["id"]

    def create_tag(self, name):
        return self._request("POST", "/tags", json={"name": name}).get("tag", {"name": name})

    def tag_resources(self, tag_name, droplet_ids):
        resources = [{"resource_id": str(d), "resource_type": "droplet"} for d in droplet_ids]
        self._request("POST", f"/tags/{tag_name}/resources", json={"resources": resources})

    def list_tags(self):
        return self._get_paginated("/tags", "tags")

    def list_regions(self):
        return self._get_paginated("/regions", "regions")

    def list_sizes(self):
        return self._get_paginated("/sizes", "sizes")

    def list_images(self, image_type="distribution"):
        params = {"type": image_type} if image_type else None
        return self._get_paginated("/images", "images", params=params)

    def list_vpcs(self):
        return self._get_paginated("/vpcs", "vpcs")

    def list_ssh_keys(self):
        return self._get_paginated("/account/keys", "ssh_keys")

    def create_ssh_key(self, name, public_key):
        return self._request("POST", "/account/keys", json={"name": name, "public_key": public_key})["ssh_key"]

    def get_account(self):
        return self._request("GET", "/account")["account"]
