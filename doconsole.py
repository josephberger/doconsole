import argparse
import base64
import cmd
import glob
import hashlib
import os
import random
import shlex
import shutil
import socket
import subprocess
import sys
import time

from dotenv import load_dotenv

import config
import formatting
import pickers
import ttl
from do_api import DEFAULT_OUTBOUND_RULES, DOAPIClient, DOAPIError

OCTOPUS_BANNER = r"""
    .---.
   /     \
   \.@-@./
   /`\_/`\
  //  _  \\
 | \     )|_
/`\_`>  <_/ \
\__/'---'\__/
"""

_NAME_ADJECTIVES = [
    "clever", "brave", "quiet", "swift", "lucky", "sunny", "mighty", "gentle",
    "curious", "bold", "sneaky", "chunky", "spicy", "dizzy", "feisty", "jolly",
    "plucky", "zippy",
]
_NAME_NOUNS = [
    "narwhal", "otter", "falcon", "yak", "koala", "walrus", "lynx", "gecko",
    "puffin", "octopus", "wombat", "ferret", "badger", "heron", "marmot",
    "toucan", "weasel", "urchin",
]

_CREATE_MESSAGES = [
    "Inflating the cloud...",
    "Waking up the hamsters...",
    "Feeding the bits...",
    "Untangling the cables...",
    "Asking nicely for an IP address...",
    "Summoning your droplet...",
    "Convincing electrons to cooperate...",
]
_SNAPSHOT_MESSAGES = [
    "Taking a mental picture...",
    "Freezing this moment in time...",
    "Say cheese...",
    "Preserving your droplet for posterity...",
    "Bottling this droplet's essence...",
]


def _random_droplet_name():
    adjective = random.choice(_NAME_ADJECTIVES)
    noun = random.choice(_NAME_NOUNS)
    suffix = random.randint(10, 99)
    return f"{adjective}-{noun}-{suffix}"


def _ssh_key_fingerprint(public_key_line):
    """MD5 fingerprint (DigitalOcean's format) of an OpenSSH public key line, or
    None if it can't be parsed. Used to detect an already-registered key so we
    never try to re-upload one DigitalOcean would reject as a duplicate."""
    parts = public_key_line.strip().split()
    if len(parts) < 2:
        return None
    try:
        key_bytes = base64.b64decode(parts[1])
    except ValueError:
        return None
    digest = hashlib.md5(key_bytes).hexdigest()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def _extract_ips(droplet):
    public_ip = None
    private_ip = None
    for network in droplet.get("networks", {}).get("v4", []):
        if network["type"] == "public":
            public_ip = network["ip_address"]
        elif network["type"] == "private":
            private_ip = network["ip_address"]
    return public_ip, private_ip


def _droplet_row(droplet):
    public_ip, private_ip = _extract_ips(droplet)
    return {
        "ID": droplet["id"],
        "Name": droplet["name"],
        "Status": droplet["status"],
        "Public IP": public_ip,
        "Private IP": private_ip,
        "Created at": droplet["created_at"],
        "Memory": droplet["memory"],
        "vCPUs": droplet["vcpus"],
        "Disk": droplet["disk"],
        "Kernel": droplet.get("kernel"),
        "Features": droplet.get("features"),
        "Networks": droplet.get("networks"),
        "Tags": droplet.get("tags"),
        "Size": droplet.get("size_slug"),
    }


def _build_create_droplet_parser():
    parser = argparse.ArgumentParser(prog="create droplet", add_help=True)
    parser.add_argument("name", nargs="?", default=None,
                         help="Defaults to a randomly generated name if omitted")
    parser.add_argument("--count", type=int, default=1, help="Create N droplets named <name>-1..<name>-N")
    parser.add_argument("--ttl", default=None, help="Auto-destroy after this long, e.g. 90m, 2h, 1d")
    parser.add_argument("--user-data", dest="user_data", default=None, help="Path to a cloud-init/user-data file")
    parser.add_argument("--from-snapshot", dest="from_snapshot", default=None,
                         help="Snapshot ID, or index from 'show snapshots', to use as the image")
    parser.add_argument("--no-firewall", dest="no_firewall", action="store_true",
                         help="Skip attaching the default SSH-only firewall for this create")
    return parser


def _build_create_firewall_parser():
    parser = argparse.ArgumentParser(prog="create firewall", add_help=True)
    parser.add_argument("name")
    parser.add_argument("--ports", default="22",
                         help="Comma-separated inbound TCP ports to allow, e.g. 22,80,443 (default: 22)")
    parser.add_argument("--attach", action="store_true",
                         help="Attach the current target droplet(s) to the new firewall")
    parser.add_argument("--tag", default=None,
                         help="Comma-separated tag(s); targets every droplet carrying at least one of them, "
                              "present or future (DO's native tag-based firewall targeting - no per-droplet "
                              "attach needed)")
    return parser


def _build_ssh_parser():
    parser = argparse.ArgumentParser(prog="ssh", add_help=True)
    parser.add_argument("-p", "--port", type=int, default=None, help="SSH port (default: 22)")
    return parser


class DOConsole(cmd.Cmd):
    """
    DigitalOcean Console.
    """

    prompt = '(DOConsole) '

    def __init__(self, token, ssh_key, playbooks_dir=None, profile=None, auto_upload_ssh_key=True,
                 default_tags=None):
        super().__init__()

        self.subcommands = {
            'set': ['droplet', 'playbook', 'token', 'ssh_key', 'region', 'size', 'image', 'vpc', 'firewall'],
            'show': ['droplets', 'playbooks', 'tags', 'target', 'info', 'snapshots', 'leases', 'doctor', 'firewalls'],
            'create': ['droplet', 'snapshot', 'firewall', 'tag'],
            'add': ['tag', 'firewall'],
            'run': ['playbook'],
            'cancel': ['ttl'],
            'power': ['on', 'off', 'reboot', 'cycle', 'shutdown'],
            'watch': ['droplets'],
        }

        self.profile = profile
        self.config = config.load_config(profile=profile)
        self.auto_upload_ssh_key = auto_upload_ssh_key
        self.default_tags = default_tags or []

        self.token = token or self.config.get("token")
        self.api = DOAPIClient(self.token)
        self.ssh_key = ssh_key or self.config.get("ssh_key")
        self.droplets = []
        self.snapshots = []
        self.target = None
        self.ansible_playbooks = playbooks_dir or self.config.get("playbooks_dir") or os.path.join(os.getcwd(), 'playbooks')
        self.playbooks = []
        self.active_playbook = None
        self.region = self.config.get("region")
        self.size = self.config.get("size")
        self.image = self.config.get("image")
        self.vpc_id = self.config.get("vpc_id")

    def _save_config(self):
        self.config.update({
            "region": self.region,
            "size": self.size,
            "image": self.image,
            "vpc_id": self.vpc_id,
            "ssh_key": self.ssh_key,
            "playbooks_dir": self.ansible_playbooks,
            "attach_ssh_firewall": self.config.get("attach_ssh_firewall", True),
        })
        config.save_config(self.config, profile=self.profile)

    def preloop(self):
        try:
            import readline
            os.makedirs(config.CONFIG_DIR, exist_ok=True)
            if os.path.exists(config.HISTORY_PATH):
                readline.read_history_file(config.HISTORY_PATH)
            readline.set_history_length(1000)
        except ImportError:
            pass

    def postloop(self):
        try:
            import readline
            os.makedirs(config.CONFIG_DIR, exist_ok=True)
            readline.write_history_file(config.HISTORY_PATH)
        except ImportError:
            pass

    # Target selection helpers

    def _target_droplets(self):
        """Return the list of droplet rows the current target refers to, regardless of shape."""
        if self.target is None:
            return []
        if self.target == "all":
            return self.droplets
        if isinstance(self.target, str) and self.target.startswith("tag:"):
            tag = self.target[len("tag:"):]
            return [d for d in self.droplets if tag in (d.get("Tags") or [])]
        return [self.target]

    def _target_label(self):
        if self.target is None:
            return "None"
        if self.target == "all":
            return "All Droplets"
        if isinstance(self.target, str) and self.target.startswith("tag:"):
            tag = self.target[len("tag:"):]
            return f"tag:{tag} ({len(self._target_droplets())} droplets)"
        return self.target["Name"]

    def _resolve_snapshot_id(self, value):
        try:
            index = int(value)
        except ValueError:
            return value
        if 0 <= index < len(self.snapshots):
            return self.snapshots[index]["id"]
        return index

    def _local_pub_key_fingerprint(self):
        if not self.ssh_key:
            return None
        pub_key_path = self.ssh_key + ".pub"
        if not os.path.isfile(pub_key_path):
            return None
        try:
            with open(pub_key_path, "r") as f:
                return _ssh_key_fingerprint(f.read())
        except OSError:
            return None

    def _ensure_ssh_key_registered(self):
        """Best-effort: upload the local public key to this DO account if it isn't
        registered yet. Matches by fingerprint first so we never attempt to
        re-upload a key that's already there (which DigitalOcean rejects as a
        duplicate) - that mismatch was the source of the old duplicate-key errors."""
        if not self.auto_upload_ssh_key:
            return

        pub_key_path = (self.ssh_key or "") + ".pub"
        if not self.ssh_key or not os.path.isfile(pub_key_path):
            return

        try:
            with open(pub_key_path, "r") as f:
                pub_key_content = f.read().strip()
        except OSError:
            return

        fingerprint = _ssh_key_fingerprint(pub_key_content)
        if fingerprint is None:
            return

        try:
            existing_keys = self.api.list_ssh_keys()
        except DOAPIError:
            return

        if any(key.get("fingerprint") == fingerprint for key in existing_keys):
            return

        key_name = f"doconsole-{socket.gethostname()}"
        try:
            self.api.create_ssh_key(key_name, pub_key_content)
            formatting.success(f"Uploaded local SSH key to DigitalOcean as '{key_name}'.")
        except DOAPIError as e:
            formatting.warning(f"Could not upload local SSH key to DigitalOcean: {e}")

    def _estimate_running_cost(self):
        try:
            sizes = self.api.list_sizes()
        except DOAPIError:
            return None
        price_by_slug = {s["slug"]: s for s in sizes}
        hourly_total = 0.0
        monthly_total = 0.0
        for droplet in self.droplets:
            size = price_by_slug.get(droplet.get("Size"))
            if size:
                hourly_total += size.get("price_hourly") or 0
                monthly_total += size.get("price_monthly") or 0
        return hourly_total, monthly_total

    def do_set(self, line):
        """Set: droplet, playbook, token, ssh_key, region, size, image, vpc, firewall."""
        args = line.split()
        if len(args) == 0:
            formatting.error("Usage: set <droplet|playbook|token|ssh_key|region|size|image|vpc|firewall>")
            return

        command = args[0]
        if command == "droplet":
            self.set_droplet(" ".join(args[1:]))
        elif command == "playbook":
            self.set_playbook(" ".join(args[1:]))
        elif command == "token":
            self.set_token(" ".join(args[1:]))
        elif command == "ssh_key":
            self.set_ssh_key(" ".join(args[1:]))
        elif command == "region":
            self.set_region()
        elif command == "size":
            self.set_size()
        elif command == "image":
            self.set_image()
        elif command == "vpc":
            self.set_vpc()
        elif command == "firewall":
            self.set_firewall(" ".join(args[1:]))
        else:
            formatting.error(f"Unknown subcommand: {command}")

    def set_droplet(self, selector):
        """Set the target droplet by index, exact name, 'all', or 'tag:<name>'."""
        selector = selector.strip()
        if not selector:
            formatting.error("Usage: set droplet <index|name|all|tag:<name>>")
            return

        if selector == "all":
            self.target = "all"
            self.prompt = '(DOConsole) all-droplets> '
            return

        if selector.startswith("tag:"):
            tag = selector[len("tag:"):]
            matches = [d for d in self.droplets if tag in (d.get("Tags") or [])]
            if not matches:
                formatting.error(f"No droplets found with tag '{tag}'.")
                return
            self.target = f"tag:{tag}"
            self.prompt = f'(DOConsole) tag:{tag}> '
            return

        try:
            index = int(selector)
        except ValueError:
            matches = [d for d in self.droplets if d["Name"] == selector]
            if not matches:
                formatting.error(f"No droplet named '{selector}'. Use 'show droplets' to see available droplets.")
                return
            self.target = matches[0]
            self.prompt = f'(DOConsole) {self.target["Name"]}> '
            return

        try:
            self.target = self.droplets[index]
        except IndexError:
            formatting.error("Invalid droplet index. Use 'show droplets' to see available droplets and their indices.")
            return
        self.prompt = f'(DOConsole) {self.target["Name"]}> '

    def set_playbook(self, index):
        """Set the active playbook by index."""
        try:
            index = int(index)
            self.active_playbook = self.playbooks[index]
            formatting.success(f"Active playbook set to: {os.path.basename(self.active_playbook)}")
        except (IndexError, ValueError):
            formatting.error("Invalid index. Please provide a valid index number.")

    def set_token(self, line):
        """Set the DigitalOcean API token. Usage: set token <value> [--save]"""
        parts = line.split()
        save = "--save" in parts
        token = " ".join(p for p in parts if p != "--save").strip()
        if not token:
            formatting.error("Please provide a valid API token.")
            return
        self.token = token
        self.api = DOAPIClient(token)
        if save:
            self.config["token"] = token
            self._save_config()
            formatting.success(f"API token set and saved to profile '{self.profile or 'default'}'.")
        else:
            formatting.success("API token set successfully (session only).")

    def set_ssh_key(self, ssh_key_path):
        """Set the SSH key."""
        if not ssh_key_path:
            formatting.error("Please provide a valid path to the SSH key.")
            return
        self.ssh_key = ssh_key_path
        self._save_config()
        formatting.success(f"SSH key set: {self.ssh_key}")

    def set_firewall(self, value):
        """Turn the default SSH-only firewall attachment on or off for future creates."""
        value = value.strip().lower()
        if value not in ("on", "off"):
            formatting.error("Usage: set firewall <on|off>")
            return
        self.config["attach_ssh_firewall"] = (value == "on")
        self._save_config()
        formatting.success(f"Default SSH-only firewall attachment is now {value}.")

    def set_region(self):
        """Set the default region for new droplets."""
        try:
            regions = self.api.list_regions()
        except DOAPIError as e:
            formatting.error(f"Could not fetch regions: {e}")
            return

        choices = [(r["slug"], r["slug"]) for r in regions]
        new_region = pickers.select("Select the new default region:", choices)
        if new_region is None:
            print("Default region not changed.")
            return
        self.region = new_region
        self._save_config()
        formatting.success(f"Default region set to {new_region}.")

    def set_size(self):
        """Set the default size for new droplets."""
        try:
            sizes = self.api.list_sizes()
        except DOAPIError as e:
            formatting.error(f"Could not fetch sizes: {e}")
            return

        choices = [
            (f"{size['slug']} \u2014 ${size.get('price_hourly', 0):.3f}/hr, ${size.get('price_monthly', 0):.2f}/mo",
             size["slug"])
            for size in sizes
        ]
        new_size = pickers.select("Select the new default size:", choices)
        if new_size is None:
            print("Default size not changed.")
            return
        self.size = new_size
        self._save_config()
        formatting.success(f"Default size set to {new_size}.")

    def set_image(self):
        """Set the default image for new droplets."""
        try:
            images = self.api.list_images()
        except DOAPIError as e:
            formatting.error(f"Could not fetch images: {e}")
            return

        choices = [(image["slug"], image["slug"]) for image in images if image.get("slug")]
        new_image = pickers.select("Select the new default image:", choices)
        if new_image is None:
            print("Default image not changed.")
            return
        self.image = new_image
        self._save_config()
        formatting.success(f"Default image set to {new_image}.")

    def set_vpc(self):
        """Set the VPC for new droplets."""
        try:
            vpcs = self.api.list_vpcs()
        except DOAPIError as e:
            formatting.error(f"Could not fetch VPCs: {e}")
            return

        if not vpcs:
            print("No VPCs found.")
            return

        choices = [(f"{vpc['name']} ({vpc['region']})", vpc) for vpc in vpcs]
        selected = pickers.select("Select a VPC:", choices)
        if selected is None:
            print("VPC not changed.")
            return

        if selected["region"] != self.region:
            formatting.error("The selected VPC is not in the current region. Change the region to match the VPC region.")
            return

        self.vpc_id = selected["id"]
        self._save_config()
        formatting.success(f"VPC set to {selected['name']}.")

    # Show Commands
    def do_show(self, line):
        """Show: droplets, playbooks, tags, target, info, snapshots, leases, doctor, firewalls."""
        args = line.split()
        if len(args) == 0:
            formatting.error("Usage: show <droplets|playbooks|tags|target|info|snapshots|leases|doctor|firewalls>")
            return

        command = args[0]
        if command == "droplets":
            self.show_droplets()
        elif command == "playbooks":
            self.show_playbooks()
        elif command == "tags":
            self.show_tags()
        elif command == "target":
            self.show_target()
        elif command == "info":
            self.show_info()
        elif command == "snapshots":
            self.show_snapshots()
        elif command == "leases":
            self.show_leases()
        elif command == "doctor":
            self.show_doctor()
        elif command == "firewalls":
            self.show_firewalls()
        else:
            formatting.error(f"Unknown subcommand: {command}")

    def refresh_droplets(self):
        """Refresh self.droplets from the API. Always reassigns, never appends."""
        try:
            droplets = self.api.list_droplets()
        except DOAPIError as e:
            formatting.error(f"Could not fetch droplets: {e}")
            return
        self.droplets = [_droplet_row(d) for d in droplets]

    def show_droplets(self):
        """Show the status of all droplets."""
        self.refresh_droplets()

        droplet_list = []
        for index, droplet in enumerate(self.droplets):
            droplet_list.append({**{'Index': index}, **droplet})

        headers = {
            "-": "Index",
            "ID": "ID",
            "Name": "Name",
            "Status": "Status",
            "Public IP": "Public IP",
            "Private IP": "Private IP",
            "Created at": "Created at"
        }

        if len(droplet_list) > 0:
            footer = ["Use 'set droplet <index|name|tag:x>' command to select a droplet."]
            cost = self._estimate_running_cost()
            if cost:
                hourly, monthly = cost
                footer.append(f"Estimated running cost: ${hourly:.3f}/hr (${monthly:.2f}/mo if left running).")
        else:
            footer = None

        formatting.print_table(headers, droplet_list, preamble="Droplet Status", footer=footer)

    def show_playbooks(self):
        """Show all available Ansible playbooks."""
        playbook_files = glob.glob(os.path.join(self.ansible_playbooks, '*.yml'))

        playbooks = []
        for index, playbook in enumerate(playbook_files):
            playbooks.append({
                "Index": index,
                "Playbook": os.path.basename(playbook)
            })

        headers = {
            "-": "Index",
            "Playbook": "Playbook"
        }

        if len(playbooks) > 0:
            footer = ["Use 'set playbook <index>' command to select a playbook."]
        else:
            footer = None

        formatting.print_table(headers, playbooks, preamble="Available Playbooks", footer=footer)

        self.playbooks = playbook_files

    def show_tags(self):
        """Show all available tags."""
        try:
            tags = self.api.list_tags()
        except DOAPIError as e:
            formatting.error(f"Could not fetch tags: {e}")
            return

        if not tags:
            print("No tags found.")
            return

        formatting.print_columns([tag["name"] for tag in tags], preamble="Available Tags")

    def show_firewalls(self):
        """Show all firewalls in the account."""
        try:
            firewalls = self.api.list_firewalls()
        except DOAPIError as e:
            formatting.error(f"Could not fetch firewalls: {e}")
            return

        if not firewalls:
            print("No firewalls found.")
            return

        rows = []
        for index, fw in enumerate(firewalls):
            inbound_ports = ",".join(r.get("ports", "?") for r in fw.get("inbound_rules", [])) or "none"
            rows.append({
                "Index": index,
                "ID": fw["id"],
                "Name": fw["name"],
                "Status": fw.get("status", "unknown"),
                "Inbound Ports": inbound_ports,
                "Droplets": len(fw.get("droplet_ids", [])),
            })

        headers = {
            "-": "Index",
            "ID": "ID",
            "Name": "Name",
            "Status": "Status",
            "Inbound Ports": "Inbound Ports",
            "Droplets": "Droplets",
        }
        formatting.print_table(headers, rows, preamble="Firewalls")

    def show_snapshots(self):
        """Show all droplet snapshots in the account."""
        try:
            snapshots = self.api.list_snapshots()
        except DOAPIError as e:
            formatting.error(f"Could not fetch snapshots: {e}")
            return

        self.snapshots = snapshots

        rows = []
        for index, snap in enumerate(snapshots):
            rows.append({
                "Index": index,
                "ID": snap["id"],
                "Name": snap["name"],
                "Regions": ",".join(snap.get("regions", [])),
                "Size (GB)": snap.get("min_disk_size"),
                "Created at": snap.get("created_at"),
            })

        headers = {
            "-": "Index",
            "ID": "ID",
            "Name": "Name",
            "Regions": "Regions",
            "Size (GB)": "Size (GB)",
            "Created at": "Created at",
        }

        footer = ["Use 'create droplet <name> --from-snapshot <index>' to boot from one."] if rows else None
        formatting.print_table(headers, rows, preamble="Droplet Snapshots", footer=footer)

    def show_leases(self):
        """Show pending TTL auto-destroys."""
        leases = ttl.list_leases()
        if not leases:
            print("No pending auto-destroys.")
            return

        rows = []
        for lease in leases:
            remaining = lease["seconds_remaining"]
            if lease["stale"]:
                status = formatting.Text("STALE (watcher process is not running - will not auto-destroy)",
                                          style="red")
            elif remaining <= 0:
                status = formatting.Text("expired (destroying soon)", style="bold red")
            elif remaining <= 60:
                status = formatting.Text(f"SELF-DESTRUCT IN {int(remaining)}s!", style="bold red")
            else:
                status = formatting.Text(f"{int(remaining // 60)}m {int(remaining % 60)}s remaining", style="yellow")
            rows.append({
                "Droplet ID": lease["droplet_id"],
                "Name": lease["name"],
                "Expires at": lease["expires_at"],
                "Status": status,
            })

        headers = {
            "Droplet ID": "Droplet ID",
            "Name": "Name",
            "Expires at": "Expires at",
            "Status": "Status",
        }

        footer = ["Use 'cancel ttl <name>' to cancel one."]
        formatting.print_table(headers, rows, preamble="Pending Auto-Destroys", footer=footer)

    def show_doctor(self):
        """Run environment/setup self-checks."""
        rows = []

        def check(label, ok, detail=""):
            rows.append({"Check": label, "Status": "OK" if ok else "ISSUE", "Detail": detail})

        ansible_path = shutil.which('ansible-playbook')
        check("ansible-playbook on PATH", ansible_path is not None,
              ansible_path or "not found - 'run playbook' will fail")

        ssh_path = shutil.which('ssh')
        check("ssh on PATH", ssh_path is not None, ssh_path or "not found - 'ssh'/'run playbook' will fail")

        if self.ssh_key:
            check("SSH key file exists", os.path.isfile(self.ssh_key), self.ssh_key)
        else:
            check("SSH key configured", False, "no SSH key set")

        fingerprint = self._local_pub_key_fingerprint()
        if fingerprint:
            try:
                existing = self.api.list_ssh_keys()
                registered = any(k.get("fingerprint") == fingerprint for k in existing)
                if registered:
                    detail = fingerprint
                elif self.auto_upload_ssh_key:
                    detail = "will be auto-uploaded on next 'create droplet'"
                else:
                    detail = "auto-upload is off (DOCONSOLE_AUTO_UPLOAD_SSH_KEY=false)"
                check("SSH key registered with DO", registered, detail)
            except DOAPIError as e:
                check("SSH key registered with DO", False, str(e))
        else:
            check("Local .pub key file found", False,
                  f"expected at {self.ssh_key}.pub" if self.ssh_key else "no SSH key configured")

        try:
            account = self.api.get_account()
            check("API token valid", True, account.get("email", ""))
        except DOAPIError as e:
            check("API token valid", False, str(e))

        playbook_files = glob.glob(os.path.join(self.ansible_playbooks, '*.yml'))
        check("Playbooks directory has .yml files", len(playbook_files) > 0, self.ansible_playbooks)

        if os.name != "nt":
            has_pkg_manager = any(shutil.which(pm) for pm in ("apt", "apt-get", "dnf", "yum", "apk"))
            check("Package manager present", has_pkg_manager,
                  "none found - this may be a minimal/container environment, not a full Linux distro")

        headers = {"Check": "Check", "Status": "Status", "Detail": "Detail"}
        formatting.print_table(headers, rows, preamble="Environment Doctor")

    def show_target(self):
        """Show information about the target droplet(s)."""

        if not self.target:
            formatting.error("No target droplet selected.")
            return

        targets = self._target_droplets()
        if not targets:
            formatting.error("No droplets match the current target.")
            return

        if len(targets) == 1:
            droplet = targets[0]
            data = {
                "ID": droplet['ID'],
                "Name": droplet['Name'],
                "Status": droplet['Status'],
                "Public IP": droplet['Public IP'],
                "Created at": droplet['Created at'],
                "Memory": droplet['Memory'],
                "vCPUs": droplet['vCPUs'],
                "Tags": droplet['Tags'] if droplet['Tags'] else "None",
            }

            for i, network in enumerate(droplet['Networks']['v4']):
                data[f"IPv4 Address {i+1}"] = network['ip_address']
                data[f"Netmask {i+1}"] = network['netmask']
                data[f"Gateway {i+1}"] = network['gateway']
                data[f"Type {i+1}"] = network['type']

            formatting.print_dict(data, preamble="Target Droplet")
            return

        data = []
        for droplet in targets:
            data.append({
                "ID": droplet['ID'],
                "Name": droplet['Name'],
                "Status": droplet['Status'],
                "Public IP": droplet['Public IP'],
                "Private IP": droplet['Private IP'],
                "Created at": droplet['Created at']
            })

        headers = {
            "ID": "ID",
            "Name": "Name",
            "Status": "Status",
            "Public IP": "Public IP",
            "Private IP": "Private IP",
            "Created at": "Created at"
        }

        formatting.print_table(headers, data, preamble=f"Target Droplets ({self._target_label()})")

    def show_info(self):
        """Show information about the current console."""
        try:
            account = self.api.get_account()
        except DOAPIError as e:
            formatting.error(f"Could not fetch account info: {e}")
            account = None

        self.refresh_droplets()

        cost = self._estimate_running_cost()
        cost_str = f"${cost[0]:.3f}/hr (${cost[1]:.2f}/mo if left running)" if cost else "Unknown"

        data = {
            "Profile": self.profile or "default",
            "Account Email": account.get("email") if account else "Unknown",
            "Target Droplet": self._target_label(),
            "Active Playbook": self.active_playbook,
            "Playbooks Directory": self.ansible_playbooks,
            "SSH Key": self.ssh_key,
            "Est. Running Cost": cost_str,
        }
        formatting.print_dict(data, preamble="DigitalOcean Console Info")

        data = {
            "Default Region": self.region,
            "Default Image": self.image,
            "Default Size": self.size,
            "Default VPC": self.vpc_id or "None",
            "Default SSH-only Firewall": "on" if self.config.get("attach_ssh_firewall", True) else "off",
            "Auto-upload SSH Key": "on" if self.auto_upload_ssh_key else "off",
            "Default Tag(s)": ", ".join(self.default_tags) if self.default_tags else "none",
        }
        formatting.print_dict(data, preamble="Default Values")

    # Create Commands
    def do_create(self, line):
        """ Create: droplet, snapshot, firewall, tag."""
        parts = line.split(maxsplit=1)
        if len(parts) == 0:
            formatting.error("Usage: create <droplet|snapshot|firewall|tag>")
            return

        command = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if command == "droplet":
            self.create_droplet(rest)
        elif command == "snapshot":
            self.create_snapshot(rest.strip())
        elif command == "firewall":
            self.create_firewall(rest)
        elif command == "tag":
            self.create_tag(rest.strip())
        else:
            formatting.error(f"Unknown subcommand: {command}")

    def create_droplet(self, line):
        """Create a new droplet. Usage: create droplet [name] [--count N] [--ttl 2h]
        [--user-data path] [--from-snapshot id_or_index] [--no-firewall]
        A random name is generated if none is given."""

        try:
            # shlex treats backslash as an escape character, which mangles Windows-style
            # paths (C:\Users\... -> C:Users...) passed to e.g. --user-data. Doubling
            # backslashes first makes shlex's escape handling round-trip them intact.
            raw_line = line.replace("\\", "\\\\") if os.name == "nt" else line
            argv = shlex.split(raw_line)
        except ValueError as e:
            formatting.error(f"Could not parse arguments: {e}")
            return

        parser = _build_create_droplet_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            return

        name = args.name or _random_droplet_name()

        ttl_seconds = None
        if args.ttl:
            try:
                ttl_seconds = ttl.parse_duration(args.ttl)
            except ValueError as e:
                formatting.error(str(e))
                return

        user_data = None
        if args.user_data:
            try:
                with open(args.user_data, "r") as f:
                    user_data = f.read()
            except OSError as e:
                formatting.error(f"Could not read user-data file: {e}")
                return

        image = self.image
        if args.from_snapshot:
            image = self._resolve_snapshot_id(args.from_snapshot)

        names = [name] if args.count <= 1 else [f"{name}-{i}" for i in range(1, args.count + 1)]

        self._ensure_ssh_key_registered()

        try:
            ssh_key_ids = [key["id"] for key in self.api.list_ssh_keys()]

            with formatting.console.status(random.choice(_CREATE_MESSAGES), spinner="dots") as status:
                def on_poll():
                    status.update(random.choice(_CREATE_MESSAGES))

                if args.count <= 1:
                    droplets = [self.api.create_droplet(
                        name=names[0], region=self.region, size=self.size, image=image,
                        ssh_key_ids=ssh_key_ids, vpc_id=self.vpc_id, user_data=user_data, on_poll=on_poll,
                    )]
                else:
                    droplets = self.api.create_droplets(
                        names=names, region=self.region, size=self.size, image=image,
                        ssh_key_ids=ssh_key_ids, vpc_id=self.vpc_id, user_data=user_data, on_poll=on_poll,
                    )
        except DOAPIError as e:
            formatting.error(f"An error occurred while creating the droplet(s): {e}")
            return

        for tag in self.default_tags:
            try:
                self.api.create_tag(tag)
            except DOAPIError as e:
                if "already exists" not in str(e).lower():
                    formatting.warning(f"Could not create default tag '{tag}': {e}")
            try:
                self.api.tag_resources(tag, [d["id"] for d in droplets])
            except DOAPIError as e:
                formatting.warning(f"Could not tag new droplet(s) with default tag '{tag}': {e}")

        if not args.no_firewall and self.config.get("attach_ssh_firewall", True):
            try:
                firewall_id = self.api.ensure_default_firewall(tags=self.default_tags)
                if not self.default_tags:
                    # No default tags, so the firewall can't auto-apply via tag membership -
                    # explicitly attach these droplets by id instead.
                    self.api.add_droplets_to_firewall(firewall_id, [d["id"] for d in droplets])
            except DOAPIError as e:
                formatting.warning(f"Warning: could not attach default SSH-only firewall: {e}")

        if ttl_seconds:
            for droplet in droplets:
                expires_at = ttl.schedule_destroy(self.token, droplet["id"], droplet["name"], ttl_seconds)
                formatting.success(f"'{droplet['name']}' will auto-destroy at {expires_at}.")

        if len(droplets) == 1:
            formatting.print_dict(_droplet_row(droplets[0]), preamble="New Droplet")
        else:
            rows = [{**{"Index": i}, **_droplet_row(d)} for i, d in enumerate(droplets)]
            headers = {
                "-": "Index", "ID": "ID", "Name": "Name", "Status": "Status",
                "Public IP": "Public IP", "Private IP": "Private IP",
            }
            formatting.print_table(headers, rows, preamble="New Droplets")

        self.refresh_droplets()

    def create_snapshot(self, name):
        """Create a snapshot of the target droplet. Usage: create snapshot <name>"""
        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if not name:
            formatting.error("Please provide a name for the snapshot.")
            return

        targets = self._target_droplets()
        if len(targets) != 1:
            formatting.error("Select exactly one droplet with 'set droplet' before creating a snapshot.")
            return

        droplet = targets[0]
        try:
            with formatting.console.status(random.choice(_SNAPSHOT_MESSAGES), spinner="dots") as status:
                def on_poll():
                    status.update(random.choice(_SNAPSHOT_MESSAGES))

                snapshot = self.api.create_snapshot(droplet['ID'], name, on_poll=on_poll)
        except DOAPIError as e:
            formatting.error(f"An error occurred while creating the snapshot: {e}")
            return

        formatting.print_dict({
            "ID": snapshot["id"],
            "Name": snapshot["name"],
            "Regions": ",".join(snapshot.get("regions", [])),
            "Size (GB)": snapshot.get("min_disk_size"),
            "Created at": snapshot.get("created_at"),
        }, preamble="New Snapshot")

    def create_firewall(self, line):
        """Create a firewall. Usage: create firewall <name> [--ports 22,80,443] [--attach] [--tag <name>]"""
        try:
            argv = shlex.split(line)
        except ValueError as e:
            formatting.error(f"Could not parse arguments: {e}")
            return

        parser = _build_create_firewall_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            return

        ports = [p.strip() for p in args.ports.split(",") if p.strip()]
        if not ports:
            formatting.error("Provide at least one port with --ports.")
            return

        droplet_ids = None
        if args.attach:
            targets = self._target_droplets()
            if not targets:
                formatting.error("No droplets match the current target. Select one with 'set droplet', or drop --attach.")
                return
            droplet_ids = [d["ID"] for d in targets]

        tags = [t.strip() for t in args.tag.split(",") if t.strip()] if args.tag else None

        inbound_rules = [
            {"protocol": "tcp", "ports": port, "sources": {"addresses": ["0.0.0.0/0", "::/0"]}}
            for port in ports
        ]

        try:
            firewall = self.api.create_firewall(args.name, inbound_rules, DEFAULT_OUTBOUND_RULES,
                                                 droplet_ids=droplet_ids, tags=tags)
        except DOAPIError as e:
            formatting.error(f"Could not create firewall: {e}")
            return

        formatting.print_dict({
            "ID": firewall["id"],
            "Name": firewall["name"],
            "Status": firewall.get("status", "unknown"),
            "Inbound Ports": ",".join(ports),
            "Attached Droplets": len(droplet_ids) if droplet_ids else 0,
            "Tag(s)": ", ".join(tags) if tags else "none",
        }, preamble="New Firewall")

    def create_tag(self, name):
        """Create a tag without assigning it to any droplet. Usage: create tag <name>"""
        if not name:
            formatting.error("Please provide a name for the tag.")
            return

        try:
            self.api.create_tag(name)
        except DOAPIError as e:
            if "already exists" in str(e).lower():
                formatting.warning(f"Tag '{name}' already exists.")
                return
            formatting.error(f"Could not create tag: {e}")
            return

        formatting.success(f"Tag '{name}' created.")

    # Add Commands
    def do_add(self, line):
        """Add: tag, firewall."""
        args = line.split()
        if len(args) == 0:
            formatting.error("Usage: add <tag|firewall>")
            return

        command = args[0]
        if command == "tag":
            self.add_tag(" ".join(args[1:]))
        elif command == "firewall":
            self.add_firewall(" ".join(args[1:]))
        else:
            formatting.error(f"Unknown subcommand: {command}")

    def _resolve_firewall_id(self, name):
        try:
            firewalls = self.api.list_firewalls()
        except DOAPIError:
            return None
        for fw in firewalls:
            if fw.get("name") == name or str(fw.get("id")) == str(name):
                return fw["id"]
        return None

    def add_firewall(self, name):
        """Add the target droplet(s) to an existing firewall. Usage: add firewall <name_or_id>"""
        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if not name:
            formatting.error("Please provide the name (or ID) of the firewall to add to.")
            return

        targets = self._target_droplets()
        if not targets:
            formatting.error("No droplets match the current target.")
            return

        firewall_id = self._resolve_firewall_id(name)
        if firewall_id is None:
            formatting.error(f"No firewall named '{name}' found. Use 'show firewalls' to see available firewalls.")
            return

        droplet_ids = [d['ID'] for d in targets]
        droplet_names = [d['Name'] for d in targets]

        try:
            self.api.add_droplets_to_firewall(firewall_id, droplet_ids)
        except DOAPIError as e:
            formatting.error(f"Could not add droplet(s) to firewall: {e}")
            return

        formatting.success(f"Added droplet(s) '{','.join(droplet_names)}' to firewall '{name}'.")

    def add_tag(self, tag_name):
        """Add a tag to the target droplet(s)."""
        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if not tag_name:
            formatting.error("Please provide the name of the tag to add.")
            return

        targets = self._target_droplets()
        if not targets:
            formatting.error("No droplets match the current target.")
            return

        droplet_ids = [d['ID'] for d in targets]
        droplet_names = [d['Name'] for d in targets]

        try:
            self.api.create_tag(tag_name)
        except DOAPIError as e:
            if "already exists" not in str(e).lower():
                formatting.error(f"An error occurred while adding the tag: {e}")
                return

        try:
            self.api.tag_resources(tag_name, droplet_ids)
        except DOAPIError as e:
            formatting.error(f"An error occurred while adding the tag: {e}")
            return

        formatting.success(f"Tag '{tag_name}' has been added to droplet '{','.join(droplet_names)}' successfully.")

    # Run Commands
    def do_run(self, line):
        """Run: playbook."""
        args = line.split()
        if len(args) == 0:
            formatting.error("Usage: run <playbook>")
            return

        command = args[0]
        if command == "playbook":
            self.run_playbook(" ".join(args[1:]))
        else:
            formatting.error(f"Unknown subcommand: {command}")

    def run_playbook(self, playbook_path):
        """Run the active playbook, or the given playbook path, on the target droplet(s)."""

        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        targets = self._target_droplets()
        if not targets:
            formatting.error("No droplets match the current target.")
            return

        droplet_ip = ",".join(d['Public IP'] for d in targets)

        if not playbook_path:
            if self.active_playbook is None:
                formatting.error("Please set a playbook or provide a path to a playbook.")
                return
            playbook_path = self.active_playbook
        elif not os.path.exists(playbook_path):
            formatting.error(f"Playbook not found: {playbook_path}")
            return

        ansible_path = shutil.which('ansible-playbook')
        if ansible_path is None:
            formatting.error("ansible-playbook is not installed. Please install Ansible. Typically 'sudo apt install ansible' on Ubuntu.")
            return

        command = [ansible_path, "-i", f"{droplet_ip},", "-u", "root",
                   f"--private-key={self.ssh_key}", playbook_path]
        subprocess.run(command)

    # Power Commands
    def do_power(self, line):
        """Power: on, off, reboot, cycle, shutdown."""
        args = line.split()
        if not args:
            formatting.error("Usage: power <on|off|reboot|cycle|shutdown>")
            return

        action_map = {
            "on": "power_on",
            "off": "power_off",
            "reboot": "reboot",
            "cycle": "power_cycle",
            "shutdown": "shutdown",
        }
        command = args[0]
        if command not in action_map:
            formatting.error(f"Unknown subcommand: {command}")
            return

        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        targets = self._target_droplets()
        if not targets:
            formatting.error("No droplets match the current target.")
            return

        for d in targets:
            try:
                self.api.droplet_action(d['ID'], action_map[command])
                formatting.success(f"Sent '{command}' to droplet {d['Name']}.")
            except DOAPIError as e:
                formatting.error(f"Could not {command} {d['Name']}: {e}")

        self.refresh_droplets()

    # Resize
    def do_resize(self, line):
        """Resize the target droplet. Usage: resize <size> [--disk]"""
        parts = line.split()
        if not parts:
            formatting.error("Usage: resize <size> [--disk]")
            return

        size_slug = parts[0]
        grow_disk = "--disk" in parts[1:]

        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        targets = self._target_droplets()
        if len(targets) != 1:
            formatting.error("Select exactly one droplet with 'set droplet' before resizing.")
            return

        droplet = targets[0]
        if droplet['Status'] != 'off':
            formatting.error(
                f"Droplet must be powered off before resizing. Run 'power off' first (current status: {droplet['Status']}).")
            return

        if grow_disk:
            formatting.warning("Disk resize is permanent - it cannot be undone or reversed to a smaller size.")

        suffix = " including disk" if grow_disk else ""
        confirmation = input(f"Resize '{droplet['Name']}' to '{size_slug}'{suffix}? Type 'yes' to confirm: ")
        if confirmation.lower() != "yes":
            print("Resize cancelled.")
            return

        try:
            self.api.resize_droplet(droplet['ID'], size_slug, disk=grow_disk)
            formatting.success(f"Resize to '{size_slug}' requested for '{droplet['Name']}'.")
        except DOAPIError as e:
            formatting.error(f"Could not resize droplet: {e}")
            return

        self.refresh_droplets()

    # Watch
    def do_watch(self, line):
        """Watch: droplets. Auto-refreshes until Ctrl-C. Usage: watch droplets [interval_seconds]"""
        args = line.split()
        if not args or args[0] != "droplets":
            formatting.error("Usage: watch droplets [interval_seconds]")
            return

        interval = 5
        if len(args) > 1:
            try:
                interval = max(1, int(args[1]))
            except ValueError:
                formatting.error("Interval must be a whole number of seconds.")
                return

        print("Watching droplets. Press Ctrl-C to stop.")
        try:
            while True:
                formatting.console.clear()
                self.show_droplets()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopped watching.")

    # Cancel Commands
    def do_cancel(self, line):
        """Cancel: ttl."""
        args = line.split()
        if len(args) < 2:
            formatting.error("Usage: cancel ttl <name_or_id>")
            return

        command = args[0]
        if command == "ttl":
            target = " ".join(args[1:])
            if ttl.cancel_lease(target):
                formatting.success(f"Cancelled auto-destroy for '{target}'.")
            else:
                formatting.error(f"No pending auto-destroy found for '{target}'.")
        else:
            formatting.error(f"Unknown subcommand: {command}")

    # Complete methods
    def complete_show(self, text, line, begidx, endidx):
        return self.complete_subcommands('show', text)

    def complete_set(self, text, line, begidx, endidx):
        return self.complete_subcommands('set', text)

    def complete_create(self, text, line, begidx, endidx):
        return self.complete_subcommands('create', text)

    def complete_add(self, text, line, begidx, endidx):
        return self.complete_subcommands('add', text)

    def complete_run(self, text, line, begidx, endidx):
        return self.complete_subcommands('run', text)

    def complete_cancel(self, text, line, begidx, endidx):
        return self.complete_subcommands('cancel', text)

    def complete_power(self, text, line, begidx, endidx):
        return self.complete_subcommands('power', text)

    def complete_watch(self, text, line, begidx, endidx):
        return self.complete_subcommands('watch', text)

    def complete_subcommands(self, command, text):
        if not text:
            return self.subcommands[command][:]
        else:
            return [s for s in self.subcommands[command] if s.startswith(text)]

    def do_destroy(self, line):
        """Destroy the target droplet(s). Usage: destroy [-y|--yes]"""
        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        skip_confirm = any(flag in line.split() for flag in ("-y", "--yes"))

        targets = self._target_droplets()
        if not targets:
            formatting.error("No droplets match the current target.")
            return

        if not skip_confirm:
            names = ", ".join(d['Name'] for d in targets)
            if len(targets) > 1:
                formatting.warning(f"About to destroy {len(targets)} droplets ({names}). This action cannot be undone.")
            else:
                formatting.warning(f"About to destroy the droplet {names}. This action cannot be undone.")
            confirmation = input("Type 'yes' to confirm: ")
            if confirmation.lower() != "yes":
                print("Droplet destruction cancelled.")
                return

        for d in targets:
            try:
                self.api.destroy_droplet(d['ID'])
                formatting.success(f"Droplet {d['Name']} has been destroyed.")
                ttl.cancel_lease(d['ID'])
            except DOAPIError as e:
                formatting.error(f"An unexpected error occurred while destroying {d['Name']}: {e}")

        self.refresh_droplets()
        self.prompt = '(DOConsole) '
        self.target = None

    def do_ssh(self, line):
        """Start an SSH session to the target droplet. Usage: ssh [-p|--port <port>]"""
        if self.target is None:
            formatting.error("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if self.target == "all" or (isinstance(self.target, str) and self.target.startswith("tag:")):
            formatting.error("Cannot SSH into multiple droplets at once. Please select a single droplet.")
            return

        try:
            argv = shlex.split(line)
        except ValueError as e:
            formatting.error(f"Could not parse arguments: {e}")
            return

        parser = _build_ssh_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit:
            return

        droplet_ip = self.target.get('Public IP')
        if droplet_ip is None:
            formatting.error("Droplet IP address is not available.")
            return

        ssh_path = shutil.which('ssh')
        if ssh_path is None:
            formatting.error("ssh is not installed or not on PATH.")
            return

        command = [ssh_path, f"root@{droplet_ip}"]
        if args.port:
            command += ["-p", str(args.port)]
        if self.ssh_key:
            command += ["-i", self.ssh_key]

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            formatting.error(f"Error occurred while connecting: {e}")
        except KeyboardInterrupt:
            print("SSH session interrupted.")

    def do_quit(self, line):
        """Quit the console."""
        return True

    def do_exit(self, line):
        """Quit the console."""
        return True


def _parse_bool_env(value, default=True):
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def resolve_settings(args, env=None):
    """Resolve settings with precedence: CLI arg > env var (real or from .env) > default."""
    env = env if env is not None else os.environ
    token = args.token or env.get('DO_API_TOKEN')
    ssh_key = args.key or env.get('DOCONSOLE_SSH_KEY') or os.path.expanduser(os.path.join('~', '.ssh', 'id_rsa'))
    playbooks_dir = args.playbooks or env.get('DOCONSOLE_PLAYBOOKS_DIR') or os.path.join(os.getcwd(), 'playbooks')
    auto_upload_ssh_key = _parse_bool_env(env.get('DOCONSOLE_AUTO_UPLOAD_SSH_KEY'), default=True)
    default_tags = [t.strip() for t in (env.get('DOCONSOLE_DEFAULT_TAG') or "").split(",") if t.strip()]
    return token, ssh_key, playbooks_dir, auto_upload_ssh_key, default_tags


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='DigitalOcean console.')
    parser.add_argument('-t', '--token', type=str, default=None,
                         help='DigitalOcean API token. Defaults to DO_API_TOKEN env var or .env file')
    parser.add_argument('-k', '--key', type=str, default=None,
                         help='Path to the SSH key. Defaults to DOCONSOLE_SSH_KEY env var/.env, else ~/.ssh/id_rsa')
    parser.add_argument('-q', '--quiet', action='store_true',
                         help='Skip the startup banner and droplet/playbook listing on launch '
                              '(also skips the droplet-list API call that listing makes)')
    parser.add_argument('--playbooks', type=str, default=None,
                         help='Path to the Ansible playbooks directory. Defaults to DOCONSOLE_PLAYBOOKS_DIR env var/.env, else ./playbooks')
    parser.add_argument('--exec', dest='exec_commands', default=None,
                         help='Run semicolon-separated commands non-interactively and exit, e.g. "show droplets; set droplet 0"')
    parser.add_argument('--profile', type=str, default=None,
                         help='Use a named profile (separate saved defaults/token) from ~/.doconsole/profiles/<name>.json')

    args = parser.parse_args()

    token, ssh_key, playbooks_dir, auto_upload_ssh_key, default_tags = resolve_settings(args)

    console = DOConsole(token, ssh_key, playbooks_dir, profile=args.profile,
                         auto_upload_ssh_key=auto_upload_ssh_key, default_tags=default_tags)

    if console.token is None:
        formatting.error("DigitalOcean API token not provided. Set --token, DO_API_TOKEN, put DO_API_TOKEN in a "
                          ".env file, or 'set token ... --save' under a --profile.")
        sys.exit(1)

    try:
        console.api.get_account()
    except DOAPIError as e:
        formatting.error(f"Authentication failed: {e}")
        sys.exit(1)

    if args.exec_commands:
        for cmd_str in args.exec_commands.split(';'):
            cmd_str = cmd_str.strip()
            if not cmd_str:
                continue
            if console.onecmd(cmd_str):
                break
        return

    if not args.quiet:
        formatting.console.print(OCTOPUS_BANNER, style="cyan")
        print("DigitalOcean Console Initialized")
        print("-------------------------------\n")
        console.do_show('droplets')
        print()
        console.do_show('playbooks')
        print()

    console.cmdloop()


if __name__ == '__main__':
    main()
