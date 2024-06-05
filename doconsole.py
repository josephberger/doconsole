import shutil
import argparse
import subprocess
import cmd
import os
import sys
import time
import glob
import ast

import digitalocean


class DOConsole(cmd.Cmd):
    """
    DigitalOcean Console.
    """

    prompt = '(DOConsole) '

    def __init__(self, token, ssh_key, playbooks_dir=None, init=False):
        """
        Initialize the DOConsole.

        Args:
            token (str): DigitalOcean API token.
            ssh_key (str): Path to the SSH key.
            playbooks_dir (str, optional): Path to the Ansible playbooks directory. Defaults to None.
            init (bool, optional): Flag to run get_status and list_playbooks on startup. Defaults to False.
        """
        super().__init__()

        self.subcommands = {
            'set': ['droplet', 'playbook', 'token', 'ssh_key', 'reigon', 'size', 'image', 'vpc'],
            'show': ['droplets', 'playbooks', 'tags','target', 'info'],
            'create': ['droplet'],
            'add': ['tag'],
            'run': ['playbook'],
        }

        self.token = token
        self.ssh_key = ssh_key
        self.manager = digitalocean.Manager(token=self.token)
        self.droplets = []
        self.target = None
        self.ansible_playbooks = playbooks_dir or os.path.join(os.getcwd(), 'playbooks')
        self.playbooks = []
        self.active_playbook = None
        self.account = {}
        self.drop_reigon = "nyc1"
        self.drop_size = "s-1vcpu-1gb"
        self.drop_image = "ubuntu-20-04-x64"
        self.vpc = None
        if init:
            print("DigitalOcean Console Initialized")
            print("-------------------------------\n")
            self.do_show('droplets')
            print()
            self.do_show('playbooks')
            print()

    def do_set(self, line):
        """Set: droplet, playbook, token, ssh_key, reigon, size, image."""
        args = line.split()
        if len(args) == 0:
            print("Usage: set <droplet|playbook|token|ssh_key|reigon|size|image>")
            return
        
        command = args[0]
        if command == "droplet":
            self.set_droplet(" ".join(args[1:]))
        elif command == "playbook":
            self.set_playbook(" ".join(args[1:]))
        elif command == "token":
            self.do_set_token(" ".join(args[1:]))
        elif command == "ssh_key":
            self.set_ssh_key(" ".join(args[1:]))
        elif command == "reigon":
            self.set_reigon()
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
            print("Invalid droplet index. Use list_droplets to see available droplets and their indices.")
    
    def set_playbook(self, index):
        """Set the active playbook by index."""
        try:
            index = int(index)
            self.active_playbook = self.playbooks[index]
            print(f"Active playbook set to: {os.path.basename(self.active_playbook)}")
        except (IndexError, ValueError):
            print("Invalid index. Please provide a valid index number.")

    def set_token(self, token):
        """Set the DigitalOcean API token."""
        self.token = token
        print("API token set successfully.")

    def set_ssh_key(self, ssh_key_path):
        """Set the SSH key."""
        if ssh_key_path:
            self.ssh_key = ssh_key_path
            print(f"SSH key set: {self.ssh_key}")
        else:
            print("Please provide a valid path to the SSH key.")

    def set_reigon(self):
        """Set the default region for new droplets."""
        regions = self.manager.get_all_regions()
        print("Available regions:")
        for region in regions:
            print(region.slug)

        new_region = input(f"Enter the new default region [{self.drop_reigon}]: ").strip()
        if new_region:
            # verify if the region is valid
            if new_region not in [region.slug for region in regions]:
                print("Invalid region.")
                return
            self.drop_reigon = new_region
            print(f"Default region set to {new_region}.")
        else:
            print("Default region not changed.")

    def set_size(self):
        """Set the default size for new droplets."""
        sizes = self.manager.get_all_sizes()
        print("Available sizes:")
        print(self.format_list_into_columns([size.slug for size in sizes]))

        new_size = input(f"Enter the new default size [{self.drop_size}]: ").strip()
        if new_size:
            # verify if the size is valid
            if new_size not in [size.slug for size in sizes]:
                print("Invalid size.")
                return
            self.drop_size = new_size
            print(f"Default size set to {new_size}.")
        else:
            print("Default size not changed.")

    def set_image(self):
        """Set the default image for new droplets."""
        images = self.manager.get_all_images()
        print("Available images:")
        print(self.format_list_into_columns([image.slug for image in images]))

        new_image = input(f"Enter the new default image [{self.drop_image}]: ").strip()
        if new_image:
            # verify if the image is valid
            if new_image not in [image.slug for image in images]:
                print("Invalid image.")
                return
            self.drop_image = new_image
            print(f"Default image set to {new_image}.")
        else:
            print("Default image not changed.")

    def set_vpc(self):
        """Set the VPC for new droplets."""
        # get the VPCs based on the current default region
        vpcs = self.manager.get_all_vpcs()
        if not vpcs:
            print("No VPCs found.")
            return
        
        data = []
        for i,vpc in enumerate(vpcs):
            data.append({
                "Index": i,
                "ID": vpc.id,
                "Name": vpc.name,
                "Region": vpc.region
            })

        headers = {
            "-": "Index", 
            "Name": "Name",
            "Region": "Region",
            "ID": "ID",
        }

        preamble = "Available VPCs"
        preamble += f"\n{'-' * len(preamble)}"
        print(self.format_table(headers, data, preamble=preamble))

        new_vpc_id = input("Enter the new VPC ID: ").strip()

        # Validate Selection
        try:
            new_vpc_id = int(new_vpc_id)
            if new_vpc_id < 0 or new_vpc_id >= len(vpcs):
                print("Invalid VPC index.")
                return
        except ValueError:
            print("Invalid VPC index.")
            return
        
        # Validate new_vpc_is in the self.region
        if vpcs[new_vpc_id].region != self.drop_reigon:
            print("The selected VPC is not in the current region.  Change the region to match the VPC region.")
            return
        
        self.vpc = vpcs[new_vpc_id]['ID']

        print(f"VPC set to {vpcs[new_vpc_id].name}. (this is currently reserved for future use and has no effect on droplet creation)")
    
    # Show Commands
    def do_show(self, line):
        """Show: droplets, playbooks, tags, target, info."""
        args = line.split()
        if len(args) == 0:
            print("Usage: show <droplets|playbooks|tags>")
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

    def show_droplets(self):
        """Show the status of all droplets."""
        self.droplets = []
        self.update_droplets()

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

        print(self.format_table(headers, droplet_list, preamble=preamble, footer=footer))

    def show_playbooks(self):
        """Show all available Ansible playbooks."""
        playbook_files = glob.glob(os.path.join(self.ansible_playbooks, '*.yml'))
        self.playbooks.clear()

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

        print(self.format_table(headers, playbooks, preamble=preamble, footer=footer))

        self.playbooks = playbook_files

    def show_tags(self):
        """Show all available tags."""
        tags = self.manager.get_all_tags()

        if not tags:
            print("No tags found.")
            return

        print("Available Tags")
        print("-" * 15)
        for tag in tags:
            print(self.format_list_into_columns([tag.name]))

    def show_target(self):
        """Show information about the target droplet."""
        
        if not self.target:
            print("No target droplet selected.")
            return
        
        # If the target is all droplets, show a table of all droplets
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
                print(self.format_table(headers, data, preamble=preamble))
            return
        
        # If the target is a single droplet, show a single droplet info
        else:
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

            print(self.format_single_dict(data, preamble=preamble))

    def show_info(self):
        """Show information about the current console."""

        # use format_single_dict method for Digital Ocean Console Info
        self.account = self.manager.get_account()
        preamble = "DigitalOcean Console Info"
        preamble += f"\n{'-' * len(preamble)}"

        if self.target == "all":
            droplet_name = "All Droplets"
        elif self.target:
            droplet_name = self.target['Name']
        else:
            droplet_name = "None"

        data = {
            "Target Droplet": droplet_name,
            "Active Playbook": self.active_playbook,
            "Playbooks Directory": self.ansible_playbooks,
            "SSH Key": self.ssh_key
        }
        print(self.format_single_dict(data, preamble=preamble))

        # use format_table method for Default Values
        preamble = "Default Values"
        preamble += f"\n{'-' * len(preamble)}"
        data = {
            "Default Region": self.drop_reigon,
            "Default Image": self.drop_image,
            "Default Size": self.drop_size
        }

        print(self.format_single_dict(data, preamble=preamble))

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
        
        my_ssh_keys = self.manager.get_all_sshkeys()


        new_droplet = digitalocean.Droplet(token=self.token,
                                           name=name,
                                           region=self.drop_reigon,
                                           image=self.drop_image,
                                           size_slug=self.drop_size,
                                           ssh_keys=my_ssh_keys,
                                           backups=False)
        
        try:
            new_droplet.create()
            print("Creating droplet. This may take a few minutes.")
            # Wait until droplet is completed
            actions = new_droplet.get_actions()
            status = ""
            # Wait for the droplet to become active
            while status != "completed":
                actions = new_droplet.get_actions()
                for action in actions:
                    action.load()
                    print(".", end="", flush=True)
                    status = action.status
                    if action.status == "completed":
                        print("!", flush=True)
                        break
                    time.sleep(1)

            while True:
                new_droplet.load()
                if new_droplet.ip_address:
                    break
                time.sleep(1)

            new_droplet.load()
        except digitalocean.DataReadError as e:
            print(f"An error occurred while creating the droplet: {e}")
            return
        except digitalocean.Exception as e:
            print(f"An unexpected error occurred: {e}")
            return
        
        data = {
            "ID": new_droplet.id,
            "Name": new_droplet.name,
            "Status": new_droplet.status,
            "Public IP": new_droplet.ip_address,
            "Private IP": new_droplet.private_ip_address if new_droplet.private_ip_address else "None",
            "Created at": new_droplet.created_at
        }

        preamble = "New Droplet"
        preamble += f"\n{'-' * len(preamble)}"

        print(self.format_single_dict(data, preamble=preamble))
        self.update_droplets()

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
        """Add a tag to the target droplet."""
        if self.target is None:
            print("No droplet selected. Use 'set droplet' command to select a droplet.")
            return

        if not tag_name:
            print("Please provide the name of the tag to add.")
            return
        
        if self.target == "all":
            droplet = [self.manager.get_droplet(droplet['ID']) for droplet in self.droplets]
        else:
            droplet = [self.manager.get_droplet(self.target['ID'])]

        # Create a Tag object with the provided name
        tag = digitalocean.Tag(token=self.token, name=tag_name)
        try:
            tag.create()
            # Add the Tag to the Droplet
            tag.add_droplets(droplet)
            droplet_names = ",".join([droplet.name for droplet in droplet])
            print(f"Tag '{tag_name}' has been added to droplet '{droplet_names}' successfully.")
        except digitalocean.DataReadError as e:
            print(f"An error occurred while adding the tag: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

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
        """Run the active playbook on a droplet."""

        if self.target is None:
            print("No droplet selected. Use 'use' command to select a droplet.")
            return
        
        if self.target == "all":
            # make a list of all droplets ip_address
            droplet_ip = ",".join(droplet['Public IP'] for droplet in self.droplets)
        else:
            droplet_ip = self.target['Public IP']

        if not os.path.exists(playbook_path):
            if self.active_playbook is None:
                print("Please set a playbook or provide a path to a playbook.")
                return
            playbook_path = os.path.join(self.ansible_playbooks, self.active_playbook)

        ansible_path = shutil.which('ansible-playbook')

        if ansible_path is None:
            print("Ansible-playbook is not installed. Please install Ansible. Typically 'sudo apt install ansible' on Ubuntu.")
            return

        ansible_command = f"{ansible_path} -i {droplet_ip}, -u root --private-key={self.ssh_key} {playbook_path}"

        subprocess.run(ansible_command, shell=True)

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

    def update_droplets(self):
        """
        Update the list of droplets.
        """

        droplets = self.manager.get_all_droplets()

        for index, droplet in enumerate(droplets):
            # get the private IP if available
            private_ip = None
            for network in droplet.networks['v4']:
                if network['type'] == 'private':
                    private_ip = network['ip_address']
                    break

            droplet_info = {
                'ID': droplet.id,
                'Name': droplet.name,
                'Status': droplet.status,
                'Public IP': droplet.ip_address,
                'Private IP': private_ip,
                'Created at': droplet.created_at,
                'Memory': droplet.memory,
                'vCPUs': droplet.vcpus,
                'Disk': droplet.disk,
                'Kernel': droplet.kernel,
                'Features': droplet.features,
                'Networks': droplet.networks,
                'Tags': droplet.tags,
                'Size': droplet.size,
            }
            self.droplets.append(droplet_info)

    def do_destroy(self, line):
        """Destroy the target droplet."""
        if self.target is None:
            print("No droplet selected. Use 'set droplet' command to select a droplet.")
            return
        
        if self.target == "all":
            print("Are you sure you want to destroy all droplets? This action cannot be undone.")
            confirmation = input("Type 'yes' to confirm: ")
            if confirmation.lower() == "yes":
                for d in self.droplets:
                    try:
                        droplet = self.manager.get_droplet(d['ID'])
                        droplet.destroy()
                        print(f"Droplet {droplet.name} has been destroyed.")
                    except digitalocean.NotFoundError as e:
                        print(f"Error: DigitalOcean dropplet; {droplet.name} not found.")
                    except Exception as e:
                        print(f"An unexpected error occurred while destroying {droplet.name}: {e}")
                        continue
                self.update_droplets()  # Refresh droplet status
                self.prompt = '(DOConsole) '  # Reset prompt
                self.target = None  # Reset target
            else:
                print("Droplet destruction cancelled.")
        else:
            confirmation = input(f"Are you sure you want to destroy the droplet {self.target['Name']}? (yes/no) ")
            if confirmation.lower() == "yes":
                try:
                    droplet = self.manager.get_droplet(self.target['ID'])
                    droplet.destroy()
                    print(f"Droplet {self.target['Name']} has been destroyed.")
                except digitalocean.NotFoundError as e:
                    print(f"Error: DigitalOcean dropplet; {self.target['Name']} not found.")
                except Exception as e:
                    print(f"An unexpected error occurred while destroying {self.target['Name']}: {e}")
                self.update_droplets()  # Refresh droplet status
                self.prompt = '(DOConsole) '  # Reset prompt
                self.target = None  # Reset target
            else:
                print("Droplet destruction cancelled.")

    ## Start of new features content

    def do_ssh(self, line):
        """Start an SSH session to the target droplet."""
        if self.target is None:
            print("No droplet selected. Use 'use' command to select a droplet.")
            return
        
        if self.target == "all":
            print("Cannot SSH into multiple droplets at once. Please select a single droplet.")
            return

        droplet_ip = self.target.get('Public IP')
        if droplet_ip is None:
            print("Droplet IP address is not available.")
            return

        ssh_username = 'root'  # Replace with the appropriate username for your droplet
        ssh_command = f"ssh {ssh_username}@{droplet_ip}"

        try:
            subprocess.run(ssh_command, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error occurred while connecting: {e}")
        except KeyboardInterrupt:
            print("SSH session interrupted.")

    # Utilities for formatting output

    def format_table(self, headers, results=None, preamble=None, footer=None):
        def calculate_max_widths():
            max_widths = {}
            for header, key in headers.items():
                header_width = len(str(header))
                value_width = max(len(str(r[key])) for r in results)
                max_widths[header] = max(header_width, value_width)
            return max_widths

        def create_format_string(max_widths):
            spacing = 2
            return " ".join(f"{{:<{width+spacing}}}" for width in max_widths.values())

        def format_header(format_string):
            header_str = format_string.format(*headers.keys())
            return header_str

        def format_data(format_string):
            data_strs = []
            for r in results:
                result_values = [r[key] for key in headers.values()]
                result_str = format_string.format(*result_values)
                data_strs.append(result_str)
            return "\n".join(data_strs)

        output = ""

        if preamble:
            output += preamble + "\n\n"

        if results:
            max_widths = calculate_max_widths()
            format_string = create_format_string(max_widths)

            header_str = format_header(format_string)
            data_str = format_data(format_string)

            output += header_str + "\n" + data_str

        if footer:
            if results:
                output += "\n\n"
            output += "\n".join(footer)

        return output + "\n"

    def format_single_dict(self, data, preamble=None, footer=None):
        def calculate_max_widths():
            max_key_width = max(len(str(key)) for key in data.keys())
            return max_key_width

        def format_data(max_key_width):
            spacing = 2
            lines = []
            for key, value in data.items():
                lines.append(f"{key:<{max_key_width + spacing}}{value}")
            return "\n".join(lines)

        output = ""

        if preamble:
            output += preamble + "\n\n"  # This correctly places the preamble at the top

        max_key_width = calculate_max_widths()
        data_str = format_data(max_key_width)

        output += data_str

        if footer:
            output += "\n\n" + "\n".join(footer)  # Footer will be placed at the bottom

        return output + "\n"

    def format_list_into_columns(self, data, num_columns=None, auto=True):
        if auto:
            if num_columns is not None:
                raise ValueError("Auto mode is enabled, num_columns argument should not be provided")
            
            total_items = len(data)
            
            if total_items <= 40:
                num_columns = 1
            elif total_items <= 80:
                num_columns = 2
            elif total_items <= 180:
                num_columns = 3
            else:
                num_columns = 4
        
        if num_columns is not None and (num_columns < 1 or num_columns > 4):
            raise ValueError("Number of columns must be between 1 and 4")

        if num_columns is None:
            raise ValueError("Number of columns must be specified when auto mode is disabled")

        # Calculate the number of rows needed
        num_rows = (len(data) + num_columns - 1) // num_columns

        # Create a list of rows, each containing num_columns elements
        rows = [data[i * num_columns:(i + 1) * num_columns] for i in range(num_rows)]

        # Calculate the maximum width of each column
        col_widths = [max(len(str(rows[row][col])) for row in range(len(rows)) if col < len(rows[row])) for col in range(num_columns)]

        # Format the rows into columns
        formatted_rows = []
        for row in rows:
            formatted_row = "".join(f"{str(item):<{col_widths[i] + 2}}" for i, item in enumerate(row))
            formatted_rows.append(formatted_row)

        return "\n".join(formatted_rows)

    def do_quit(self, line):
        """Quit the console."""
        return True
    
    def do_exit(self, line):
        """Quit the console."""
        return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DigitalOcean console.')
    parser.add_argument('-t', '--token', type=str, help='DigitalOcean API token. Defaults to DO_API_TOKEN env var')
    parser.add_argument('-k', '--key', type=str, default=os.path.expanduser(os.path.join('~', '.ssh', 'id_rsa')), help='Path to the SSH key.')
    parser.add_argument('--init', action='store_true', help='Run get_status and list_playbooks on startup')
    parser.add_argument('--playbooks', type=str, help='Path to the Ansible playbooks directory.')

    # Parse arguments
    args = parser.parse_args()

    # Check if token is provided or in environment variables
    token = args.token or os.environ.get('DO_API_TOKEN')

    if token is None:
        print("DigitalOcean API token not provided and DO_API_TOKEN environment variable not set.")
        sys.exit(1)

    ssh_key = args.key

    if ssh_key is None:
        print("SSH key not provided.")
        sys.exit(1)

    playbooks_dir = args.playbooks or os.path.join(os.getcwd(), 'playbooks')

    try:
        DOConsole(token, ssh_key, playbooks_dir, init=args.init).cmdloop()
    except digitalocean.DataReadError as e:
        if 'Unable to authenticate' in str(e):
            print("Authentication failed. Please check the API token.")
        else:
            print(f"An error occurred: {e}")
