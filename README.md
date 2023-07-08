# DOConsole

DOConsole is a command-line tool that provides an interactive console for managing DigitalOcean resources and running Ansible playbooks on droplets.

## Installation

To use DOConsole, follow these steps:

1. Clone the repository or download the script to your local machine.
2. Ensure you have Python 3 installed.
3. Install the required dependencies by running the following command:
   ```
   pip install -r requirements.txt
   ```

## Usage

To start the DOConsole, run the script with the required arguments:

```
python doconsole.py --token <DIGITALOCEAN_API_TOKEN> --key <PATH_TO_SSH_KEY> [--playbooks <PLAYBOOKS_DIRECTORY>] [--init]
```

Replace `<DIGITALOCEAN_API_TOKEN>` with your DigitalOcean API token and `<PATH_TO_SSH_KEY>` with the path to your SSH key.

### Arguments

- `--token <DIGITALOCEAN_API_TOKEN>`: DigitalOcean API token. It can also be provided as the `DO_API_TOKEN` environment variable.
- `--key <PATH_TO_SSH_KEY>`: Path to the SSH key used for droplet access.
- `--playbooks <PLAYBOOKS_DIRECTORY>`: Path to the directory containing Ansible playbooks. (Optional)
- `--init`: Run `show_droplets` and `list_playbooks` commands on startup. (Optional)

## Commands

DOConsole provides the following commands:

- `set_token`: Set the DigitalOcean API token.
- `set_ssh_key`: Set the SSH key.
- `show_info`: Show information about the current console.
- `show_droplets`: Show the status of all droplets.
- `set_droplet`: Set the target droplet by its index.
- `create_droplet`: Create a new droplet.
- `run_playbook`: Run the active playbook on a droplet.
- `quit`: Quit the console.
- `list_playbooks`: List all available Ansible playbooks.
- `set_playbook`: Set the active playbook by index.
- `destroy`: Destroy the target droplet.

## Examples

1. Show the status of all droplets:
   ```
   show_droplets
   ```

2. Create a new droplet with a specific name:
   ```
   create_droplet <DROPLET_NAME>
   ```

3. Run the active playbook on the target droplet:
   ```
   run_playbook
   ```

4. Set the active playbook by index:
   ```
   set_playbook <PLAYBOOK_INDEX>
   ```

5. Destroy the target droplet:
   ```
   destroy
   ```

## Credits

DOConsole uses the DigitalOcean Python Library to interact with the DigitalOcean API and Ansible to run playbooks on droplets.

## License

This project is licensed under the [MIT License](LICENSE).

Feel free to contribute to this project by reporting issues or submitting pull requests on GitHub.
