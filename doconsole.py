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
        if init:
            print("\n\nDigitalOcean Console Initialized")
            print("-------------------------------\n")
            self.do_list_droplets(None)
            print()
            self.do_list_playbooks(None)
            print()


    def do_set_token(self, line):
        """
        Set the DigitalOcean API token.

        Args:
            line (str): The input string containing the API token.
        """
        if line:
            self.token = line
            print("API token set successfully.")
        else:
            print("Please provide a valid API token.")


    def do_set_ssh_key(self, line):
        """
        Set the SSH key.

        Args:
            line (str): The input string containing the path to the SSH key.
        """
        if line:
            self.ssh_key = line
            print(f"SSH key set: {self.ssh_key}")
        else:
            print("Please provide a valid path to the SSH key.")


    def do_show_info(self, line):
        """Show information about the current console."""
        print("\n\nDigitalOcean Console Info")
        print("-------------------------------\n")
        print(f"{'Target Droplet:': <20} {self.get_target_info()}")
        print(f"{'Active Playbook:': <20} {self.active_playbook}")
        print(f"{'Playbooks Directory:': <20} {self.ansible_playbooks}")
        print(f"{'SSH Key:': <20} {self.ssh_key}")
        print("\nDefault Values")
        print("-------------------------------\n")
        print(f"{'Default Region:': <20} {self.drop_reigon}")
        print(f"{'Default Image:': <20} {self.drop_image}")
        print(f"{'Default Size:': <20} {self.drop_size}")
        print("\n-------------------------------\n")


    def get_target_info(self):
        """Get information about the target droplet."""
        if self.target:
            return f"ID: {self.target['ID']}, Name: {self.target['Name']}"
        else:
            return None


    def do_list_droplets(self, line):
        """Show the status of all droplets."""
        self.droplets = []
        self.update_droplets()
        self.print_droplets()


    def update_droplets(self):
        """Update the status of all droplets."""
        droplets = self.manager.get_all_droplets()

        for index, droplet in enumerate(droplets):
            droplet_info = {
                'ID': droplet.id,
                'Name': droplet.name,
                'Status': droplet.status,
                'Public IP': droplet.ip_address,
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


    def print_droplets(self):
        """Print the status of all droplets."""
        print(f"{'-': <5}{'ID': <10}{'Name': <20}{'Status': <10}{'Public IP': <20}{'Created at': <20}")

        for index, droplet in enumerate(self.droplets):
            print(f"{index: <5}{droplet['ID']: <10}{droplet['Name']: <20}{droplet['Status']: <10}{droplet['Public IP']: <20}{droplet['Created at']: <20}")


    def do_set_droplet(self, line):
        """Set the target droplet by its index in the self.droplets list."""
        try:
            index = int(line)
            self.target = self.droplets[index]
            self.prompt = f'(DOConsole) {self.target["Name"]}> '
        except (IndexError, ValueError):
            print("Invalid droplet index. Use get_status to see available droplets and their indices.")


    def do_create_droplet(self, line):
        """Create a new droplet."""

        if not line:
            print("Please provide a name for the new droplet.")
            return
        
        my_ssh_keys = self.manager.get_all_sshkeys()

        new_droplet = digitalocean.Droplet(token=self.token,
                                            name=line,
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
        except digitalocean.AuthError as e:
            print(f"Authentication error: {e}")
            return
        except digitalocean.Exception as e:
            print(f"An unexpected error occurred: {e}")
            return

        print("Droplet has been created successfully!")
        print(f"ID: {new_droplet.id}\nName: {new_droplet.name}\nStatus: {new_droplet.status}\nPublic IP: {new_droplet.ip_address}\nCreated at: {new_droplet.created_at}")
        self.update_droplets()  # Refresh droplet status


    def do_run_playbook(self, line):
        """Run the active playbook on a droplet."""

        if self.target is None:
            print("No droplet selected. Use 'use' command to select a droplet.")
            return

        if line:
            playbook_path = line
        else:
            playbook_path = os.path.join(self.ansible_playbooks, self.active_playbook)


        if not os.path.exists(playbook_path):
            print(f"Playbook not found: {playbook_path}")
            return

        droplet = self.manager.get_droplet(self.target['ID'])
        ansible_path = shutil.which('ansible-playbook')

        if ansible_path is None:
            print("Ansible-playbook is not installed. Please install Ansible.")
            return

        playbook_path = os.path.join(self.ansible_playbooks, self.active_playbook)
        ansible_command = f"{ansible_path} -i {droplet.ip_address}, -u root --private-key={self.ssh_key} {playbook_path}"

        subprocess.run(ansible_command, shell=True)

        print(f"Droplet with ID {line} has been updated.")

    
    def do_list_playbooks(self, line):
        """List all available Ansible playbooks."""
        playbook_files = glob.glob(os.path.join(self.ansible_playbooks, '*.yml'))
        self.playbooks.clear()

        # Print the header
        print(f"{'-': <5}{'Playbook': <20}")

        for index, playbook in enumerate(playbook_files):
            self.playbooks.append(playbook)
            print(f"{index: <5}{os.path.basename(playbook): <20}")


    def do_set_playbook(self, line):
        """Set the active playbook by index."""
        try:
            index = int(line)
            self.active_playbook = self.playbooks[index]
            print(f"Active playbook set to: {os.path.basename(self.active_playbook)}")
        except (IndexError, ValueError):
            print("Invalid index. Please provide a valid index number.")


    def do_destroy(self, line):
        """Destroy the target droplet."""
        if self.target is None:
            print("No droplet selected. Use 'use' command to select a droplet.")
            return

        confirmation = input(f"Are you sure you want to destroy the droplet {self.target['Name']}? (yes/no) ")
        if confirmation.lower() == "yes":
            droplet = self.manager.get_droplet(self.target['ID'])
            droplet.destroy()
            print(f"Droplet {self.target['Name']} has been destroyed.")
            self.update_droplets()  # Refresh droplet status
            self.prompt = '(DOConsole) '  # Reset prompt
            self.target = None  # Reset target
        else:
            print("Droplet destruction cancelled.")

    ## Start of new features content
    def do_list_tags(self, line):
        """List all available tags."""
        tags = self.manager.get_all_tags()

        if not tags:
            print("No tags found.")
            return

        print("Available Tags:")
        for tag in tags:
            print(tag.name)

    def do_add_tag_to_droplet(self, line):
        """Add a tag to the target droplet."""
        if self.target is None:
            print("No droplet selected. Use 'set_droplet' command to select a droplet.")
            return

        if not line:
            print("Please provide the name of the tag to add.")
            return

        droplet = self.manager.get_droplet(self.target['ID'])

        # Create a Tag object with the provided name
        tag = digitalocean.Tag(token=self.token, name=line)
        try:
            tag.create()
            # Add the Tag to the Droplet
            #droplet.add_tags([tag])
            tag.add_droplets([droplet])
            print(f"Tag '{line}' has been added to droplet '{droplet.name}'.")
        except digitalocean.DataReadError as e:
            print(f"An error occurred while adding the tag: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    def do_ssh(self, line):
        """Start an SSH session to the target droplet."""
        if self.target is None:
            print("No droplet selected. Use 'use' command to select a droplet.")
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


    def do_set_defaults(self, line):
        """Set the default values for region, size, and image of the new droplets."""
        regions = self.manager.get_all_regions()
        sizes = self.manager.get_all_sizes()
        images = self.manager.get_all_images()

        print("Current default values:")
        print(f"Region: {self.drop_reigon}")
        print(f"Size: {self.drop_size}")
        print(f"Image: {self.drop_image}")

        line_break = "\n"

        new_region = input(f"Enter the new default region {', '.join([region.slug for region in regions])} [{self.drop_reigon}]: ").strip()
        new_size = input(f"Enter the new default size {line_break.join([size.slug for size in sizes])} [{self.drop_size}]: ").strip()
        new_image = input(f"Enter the new default image {line_break.join([image.slug for image in images])} [{self.drop_image}]: ").strip()

        if new_region.strip() != "":
            self.drop_reigon = new_region
        if new_size.strip() != "":
            self.drop_size = new_size
        if new_image.strip() != "":
            self.drop_image = new_image

        print("Defaults updated successfully.")


    ## End of new features content

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

    DOConsole(token, ssh_key, playbooks_dir, init=args.init).cmdloop()
