import time

import requests

API_BASE = "https://api.digitalocean.com/v2"
REQUEST_TIMEOUT = 30
CREATE_DROPLET_TIMEOUT = 300


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

    def create_droplet(self, name, region, size, image, ssh_key_ids, vpc_id=None,
                        wait_timeout=CREATE_DROPLET_TIMEOUT, on_poll=None):
        body = {
            "name": name,
            "region": region,
            "size": size,
            "image": image,
            "ssh_keys": ssh_key_ids,
            "backups": False,
        }
        if vpc_id:
            body["vpc_uuid"] = vpc_id

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

    def destroy_droplet(self, droplet_id):
        self._request("DELETE", f"/droplets/{droplet_id}")

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

    def get_account(self):
        return self._request("GET", "/account")["account"]
