import argparse
import cmd
import glob
import os
import shutil
import subprocess
import sys

from dotenv import load_dotenv

import config
import formatting
from do_api import DOAPIClient, DOAPIError


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


class DOConsole(cmd.Cmd):
    """
    DigitalOcean Console.
    """

    prompt = '(DOConsole) '

    def __init__(self, token, ssh_key, playbooks_dir=None):
        super().__init__()

        self.subcommands = {
            'set': ['droplet', 'playbook', 'token', 'ssh_key', 'region', 'size', 'image', 'vpc'],
            'show': ['droplets', 'playbooks', 'tags', 'target', 'info'],
            'create': ['droplet'],
            'add': ['tag'],
            'run': ['playbook'],
        }

        self.config = config.load_config()

        self.token = token
        self.api = DOAPIClient(token)
        self.ssh_key = ssh_key or self.config.get("ssh_key")
        self.droplets = []
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
        })
        config.save_config(self.config)

    def do_set(self, line):
        """Set: droplet, playbook, token, ssh_key, region, size, image, vpc."""
        args = line.split()
        if len(args) == 0:
            print("Usage: set <droplet|playbook|token|ssh_key|region|size|image|vpc>")
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
        else:
            print(f"Unknown subcommand: {command}")

    def set_droplet(self, index):
        """Set the target droplet by its index in the self.droplets list."""

        if index == "all":
            self.target = "all"
            self.prompt = '(DOConsole) all-droplets> '
            return

        try:
            index = int(index)
            self.target = self.droplets[index]
            self.prompt = f'(DOConsole) {self.target["Name"]}> '
        except (IndexError, ValueError):
            print("Invalid droplet index. Use 'show droplets' to see available droplets and their indices.")

    def set_playbook(self, index):
        """Set the active playbook by index."""
        try:
            index = int(index)
            self.active_playbook = self.playbooks[index]
            print(f"Active playbook set to: {os.path.basename(self.active_playbook)}")
        except (IndexError, ValueError):
            print("Invalid index. Please provide a valid index number.")

    def set_token(self, token):
        """Set the DigitalOcean API token for this session."""
        if not token:
            print("Please provide a valid API token.")
            return
        self.token = token
        self.api = DOAPIClient(token)
        print("API token set successfully.")

    def set_ssh_key(self, ssh_key_path):
        """Set the SSH key."""
        if not ssh_key_path:
            print("Please provide a valid path to the SSH key.")
            return
        self.ssh_key = ssh_key_path
        self._save_config()
        print(f"SSH key set: {self.ssh_key}")

    def set_region(self):
        """Set the default region for new droplets."""
        try:
            regions = self.api.list_regions()
        except DOAPIError as e:
            print(f"Could not fetch regions: {e}")
            return

        print("Available regions:")
        for region in regions:
            print(region["slug"])

        new_region = input(f"Enter the new default region [{self.region}]: ").strip()
        if not new_region:
            print("Default region not changed.")
            return
        if new_region not in [r["slug"] for r in regions]:
            print("Invalid region.")
            return
        self.region = new_region
        self._save_config()
        print(f"Default region set to {new_region}.")

    def set_size(self):
        """Set the default size for new droplets."""
        try:
            sizes = self.api.list_sizes()
        except DOAPIError as e:
            print(f"Could not fetch sizes: {e}")
            return

        print("Available sizes:")
        print(formatting.format_list_into_columns([size["slug"] for size in sizes]))

        new_size = input(f"Enter the new default size [{self.size}]: ").strip()
        if not new_size:
            print("Default size not changed.")
            return
        if new_size not in [size["slug"] for size in sizes]:
            print("Invalid size.")
            return
        self.size = new_size
        self._save_config()
        print(f"Default size set to {new_size}.")

    def set_image(self):
        """Set the default image for new droplets."""
        try:
            images = self.api.list_images()
        except DOAPIError as e:
            print(f"Could not fetch images: {e}")
            return

        print("Available images:")
        print(formatting.format_list_into_columns([image["slug"] for image in images if image.get("slug")]))

        new_image = input(f"Enter the new default image [{self.image}]: ").strip()
        if not new_image:
            print("Default image not changed.")
            return
        if new_image not in [image.get("slug") for image in images]:
            print("Invalid image.")
            return
        self.image = new_image
        self._save_config()
        print(f"Default image set to {new_image}.")

    def set_vpc(self):
        """Set the VPC for new droplets."""
        try:
            vpcs = self.api.list_vpcs()
        except DOAPIError as e:
            print(f"Could not fetch VPCs: {e}")
            return

        if not vpcs:
            print("No VPCs found.")
            return

        data = []
        for i, vpc in enumerate(vpcs):
            data.append({
                "Index": i,
                "ID": vpc["id"],
                "Name": vpc["name"],
                "Region": vpc["region"],
            })

        headers = {
            "-": "Index",
            "Name": "Name",
            "Region": "Region",
            "ID": "ID",
        }

        preamble = "Available VPCs"
        preamble += f"\n{'-' * len(preamble)}"
        print(formatting.format_table(headers, data, preamble=preamble))

        selection = input("Enter the VPC index: ").strip()
        try:
            selection = int(selection)
            if selection < 0 or selection >= len(vpcs):
                raise ValueError
        except ValueError:
            print("Invalid VPC index.")
            return

        selected = vpcs[selection]
        if selected["region"] != self.region:
            print("The selected VPC is not in the current region. Change the region to match the VPC region.")
            return

        self.vpc_id = selected["id"]
        self._save_config()
        print(f"VPC set to {selected['name']}.")

    # Show Commands
    def do_show(self, line):
        """Show: droplets, playbooks, tags, target, info."""
        args = line.split()
        if len(args) == 0:
            print("Usage: show <droplets|playbooks|tags|target|info>")
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
        else:
            print(f"Unknown subcommand: {command}")

    def refresh_droplets(self):
        """Refresh self.droplets from the API. Always reassigns, never appends."""
        try:
            droplets = self.api.list_droplets()
        except DOAPIError as e:
            print(f"Could not fetch droplets: {e}")
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

        preamble = "Droplet Status"
        preamble += f"\n{'-' * len(preamble)}"

        if len(droplet_list) > 0:
            footer = ["Use 'set droplet <index>' command to select a droplet."]
        else:
            footer = None

        print(formatting.format_table(headers, droplet_list, preamble=preamble, footer=footer))

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

        preamble = "Available Playbooks"
        preamble += f"\n{'-' * len(preamble)}"

        if len(playbooks) > 0:
            footer = ["Use 'set playbook <index>' command to select a playbook."]
        else:
            footer = None

        print(formatting.format_table(headers, playbooks, preamble=preamble, footer=footer))

        self.playbooks = playbook_files

    def show_tags(self):
        """Show all available tags."""
        try:
            tags = self.api.list_tags()
        except DOAPIError as e:
            print(f"Could not fetch tags: {e}")
            return

        if not tags:
            print("No tags found.")
            return

        print("Available Tags")
        print("-" * 15)
        print(formatting.format_list_into_columns([tag["name"] for tag in tags]))

    def show_target(self):
        """Show information about the target droplet."""

        if not self.target:
            print("No target droplet selected.")
            return

        if self.target == "all":
            data = []
            for droplet in self.droplets:
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

            preamble = "All Droplets"
            preamble += f"\n{'-' * len(preamble)}"
            print(formatting.format_table(headers, data, preamble=preamble))
            return

        data = {
            "ID": self.target['ID'],
            "Name": self.target['Name'],
            "Status": self.target['Status'],
            "Public IP": self.target['Public IP'],
            "Created at": self.target['Created at'],
            "Memory": self.target['Memory'],
            "vCPUs": self.target['vCPUs'],
            "Tags": self.target['Tags'] if self.target['Tags'] else "None",
        }

        for i, network in enumerate(self.target['Networks']['v4']):
            data[f"IPv4 Address {i+1}"] = network['ip_address']
            data[f"Netmask {i+1}"] = network['netmask']
            data[f"Gateway {i+1}"] = network['gateway']
            data[f"Type {i+1}"] = network['type']

        preamble = "Target Droplet"
        preamble += f"\n{'-' * len(preamble)}"

        print(formatting.format_single_dict(data, preamble=preamble))

    def show_info(self):
        """Show information about the current console."""
        try:
            account = self.api.get_account()
        except DOAPIError as e:
            print(f"Could not fetch account info: {e}")
            account = None

        preamble = "DigitalOcean Console Info"
        preamble += f"\n{'-' * len(preamble)}"

        if self.target == "all":
            droplet_name = "All Droplets"
        elif self.target:
            droplet_name = self.target['Name']
        else:
            droplet_name = "None"

        data = {
            "Account Email": account.get("email") if account else "Unknown",
            "Target Droplet": droplet_name,
            "Active Playbook": self.active_playbook,
            "Playbooks Directory": self.ansible_playbooks,
            "SSH Key": self.ssh_key
        }
        print(formatting.format_single_dict(data, preamble=preamble))

        preamble = "Default Values"
        preamble += f"\n{'-' * len(preamble)}"
        data = {
            "Default Region": self.region,
            "Default Image": self.image,
            "Default Size": self.size,
            "Default VPC": self.vpc_id or "None",
        }

        print(formatting.format_single_dict(data, preamble=preamble))

    # Create Commands
    def do_create(self, line):
        """ Create: droplet."""
        args = line.split()
        if len(args) == 0:
            print("Usage: create <droplet>")
            return

        command = args[0]
        if command == "droplet":
            self.create_droplet(" ".join(args[1:]))
        else:
            print(f"Unknown subcommand: {command}")

    def create_droplet(self, name):
        """Create a new droplet."""

        if not name:
            print("Please provide a name for the new droplet.")
            return

        try:
            ssh_key_ids = [key["id"] for key in self.api.list_ssh_keys()]

            print("Creating droplet. This may take a few minutes.", end="", flush=True)
            droplet = self.api.create_droplet(
                name=name,
                region=self.region,
                size=self.size,
                image=self.image,
                ssh_key_ids=ssh_key_ids,
                vpc_id=self.vpc_id,
                on_poll=lambda: print(".", end="", flush=True),
            )
            print()
        except DOAPIError as e:
            print(f"\nAn error occurred while creating the droplet: {e}")
            return

        preamble = "New Droplet"
        preamble += f"\n{'-' * len(preamble)}"
        print(formatting.format_single_dict(_droplet_row(droplet), preamble=preamble))
        self.refresh_droplets()

    # Add Commands
    def do_add(self, line):
        """Add: tag."""
        args = line.split()
        if len(args) == 0:
            print("Usage: add <tag>")
            return

        command = args[0]
        if command == "tag":
            self.add_tag(" ".join(args[1:]))
        else:
            print(f"Unknown subcommand: {command}")

    def add_tag(self, tag_name):
        """Add a tag to the target droplet(s)."""
        if self.target is None:
            print("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if not tag_name:
            print("Please provide the name of the tag to add.")
            return

        if self.target == "all":
            droplet_ids = [droplet['ID'] for droplet in self.droplets]
            droplet_names = [droplet['Name'] for droplet in self.droplets]
        else:
            droplet_ids = [self.target['ID']]
            droplet_names = [self.target['Name']]

        try:
            self.api.create_tag(tag_name)
        except DOAPIError as e:
            if "already exists" not in str(e).lower():
                print(f"An error occurred while adding the tag: {e}")
                return

        try:
            self.api.tag_resources(tag_name, droplet_ids)
        except DOAPIError as e:
            print(f"An error occurred while adding the tag: {e}")
            return

        print(f"Tag '{tag_name}' has been added to droplet '{','.join(droplet_names)}' successfully.")

    # Run Commands
    def do_run(self, line):
        """Run: playbook."""
        args = line.split()
        if len(args) == 0:
            print("Usage: run <playbook>")
            return

        command = args[0]
        if command == "playbook":
            self.run_playbook(" ".join(args[1:]))
        else:
            print(f"Unknown subcommand: {command}")

    def run_playbook(self, playbook_path):
        """Run the active playbook, or the given playbook path, on the target droplet."""

        if self.target is None:
            print("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if self.target == "all":
            droplet_ip = ",".join(droplet['Public IP'] for droplet in self.droplets)
        else:
            droplet_ip = self.target['Public IP']

        if not playbook_path:
            if self.active_playbook is None:
                print("Please set a playbook or provide a path to a playbook.")
                return
            playbook_path = self.active_playbook
        elif not os.path.exists(playbook_path):
            print(f"Playbook not found: {playbook_path}")
            return

        ansible_path = shutil.which('ansible-playbook')
        if ansible_path is None:
            print("ansible-playbook is not installed. Please install Ansible. Typically 'sudo apt install ansible' on Ubuntu.")
            return

        command = [ansible_path, "-i", f"{droplet_ip},", "-u", "root",
                   f"--private-key={self.ssh_key}", playbook_path]
        subprocess.run(command)

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

    def complete_subcommands(self, command, text):
        if not text:
            return self.subcommands[command][:]
        else:
            return [s for s in self.subcommands[command] if s.startswith(text)]

    def do_destroy(self, line):
        """Destroy the target droplet(s)."""
        if self.target is None:
            print("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if self.target == "all":
            print("Are you sure you want to destroy all droplets? This action cannot be undone.")
            confirmation = input("Type 'yes' to confirm: ")
            if confirmation.lower() != "yes":
                print("Droplet destruction cancelled.")
                return

            for d in self.droplets:
                try:
                    self.api.destroy_droplet(d['ID'])
                    print(f"Droplet {d['Name']} has been destroyed.")
                except DOAPIError as e:
                    print(f"An unexpected error occurred while destroying {d['Name']}: {e}")

            self.refresh_droplets()
            self.prompt = '(DOConsole) '
            self.target = None
        else:
            confirmation = input(f"Are you sure you want to destroy the droplet {self.target['Name']}? (yes/no) ")
            if confirmation.lower() != "yes":
                print("Droplet destruction cancelled.")
                return

            try:
                self.api.destroy_droplet(self.target['ID'])
                print(f"Droplet {self.target['Name']} has been destroyed.")
            except DOAPIError as e:
                print(f"An unexpected error occurred while destroying {self.target['Name']}: {e}")

            self.refresh_droplets()
            self.prompt = '(DOConsole) '
            self.target = None

    def do_ssh(self, line):
        """Start an SSH session to the target droplet."""
        if self.target is None:
            print("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if self.target == "all":
            print("Cannot SSH into multiple droplets at once. Please select a single droplet.")
            return

        droplet_ip = self.target.get('Public IP')
        if droplet_ip is None:
            print("Droplet IP address is not available.")
            return

        ssh_path = shutil.which('ssh')
        if ssh_path is None:
            print("ssh is not installed or not on PATH.")
            return

        command = [ssh_path, f"root@{droplet_ip}"]
        if self.ssh_key:
            command += ["-i", self.ssh_key]

        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error occurred while connecting: {e}")
        except KeyboardInterrupt:
            print("SSH session interrupted.")

    def do_quit(self, line):
        """Quit the console."""
        return True

    def do_exit(self, line):
        """Quit the console."""
        return True


def resolve_settings(args, env=None):
    """Resolve token/ssh_key/playbooks_dir with precedence: CLI arg > env var (real or from .env) > default."""
    env = env if env is not None else os.environ
    token = args.token or env.get('DO_API_TOKEN')
    ssh_key = args.key or env.get('DOCONSOLE_SSH_KEY') or os.path.expanduser(os.path.join('~', '.ssh', 'id_rsa'))
    playbooks_dir = args.playbooks or env.get('DOCONSOLE_PLAYBOOKS_DIR') or os.path.join(os.getcwd(), 'playbooks')
    return token, ssh_key, playbooks_dir


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='DigitalOcean console.')
    parser.add_argument('-t', '--token', type=str, default=None,
                         help='DigitalOcean API token. Defaults to DO_API_TOKEN env var or .env file')
    parser.add_argument('-k', '--key', type=str, default=None,
                         help='Path to the SSH key. Defaults to DOCONSOLE_SSH_KEY env var/.env, else ~/.ssh/id_rsa')
    parser.add_argument('--init', action='store_true', help='Show droplets and playbooks on startup')
    parser.add_argument('--playbooks', type=str, default=None,
                         help='Path to the Ansible playbooks directory. Defaults to DOCONSOLE_PLAYBOOKS_DIR env var/.env, else ./playbooks')

    args = parser.parse_args()

    token, ssh_key, playbooks_dir = resolve_settings(args)
    if token is None:
        print("DigitalOcean API token not provided. Set --token, DO_API_TOKEN, or put DO_API_TOKEN in a .env file.")
        sys.exit(1)

    console = DOConsole(token, ssh_key, playbooks_dir)

    try:
        console.api.get_account()
    except DOAPIError as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)

    if args.init:
        print("DigitalOcean Console Initialized")
        print("-------------------------------\n")
        console.do_show('droplets')
        print()
        console.do_show('playbooks')
        print()

    console.cmdloop()


if __name__ == '__main__':
    main()
