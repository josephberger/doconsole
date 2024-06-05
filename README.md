# DigitalOcean Console (DOConsole)

`DOConsole` is a command-line interface (CLI) tool that allows you to manage DigitalOcean droplets and run Ansible playbooks. The tool provides functionalities to set configurations, create and destroy droplets, add tags, run Ansible playbooks, and more.

## Features

- **Manage Droplets**: List, create, destroy, and tag DigitalOcean droplets.
- **Run Ansible Playbooks**: Execute Ansible playbooks on your droplets.
- **SSH Access**: SSH into your droplets directly from the console.
- **Customizable Settings**: Configure default region, size, and image for new droplets.

## Installation

1. **Clone the Repository**:
   ```sh
   git clone https://github.com/josephberger/doconsole.git
   cd doconsole
   ```

2. **Install Dependencies**:
   ```sh
   pip install -r requirements.txt
   ```

3. **Ensure Ansible is Installed**:
   ```sh
   sudo apt install ansible
   ```

## Usage

1. **Run the Console**:
   ```sh
   python doconsole.py --token YOUR_DO_TOKEN --ssh_key PATH_TO_YOUR_SSH_KEY
   ```

2. **Commands Overview**:
   - **Set Configurations**:
     ```sh
     set <droplet|playbook|token|ssh_key|reigon|size|image>
     ```
     - Example: `set droplet 1`
   - **Show Information**:
     ```sh
     show <droplets|playbooks|tags|target|info>
     ```
     - Example: `show droplets`
   - **Create Droplet**:
     ```sh
     create droplet <name>
     ```
     - Example: `create droplet my-new-droplet`
   - **Add Tag**:
     ```sh
     add tag <tag_name>
     ```
     - Example: `add tag production`
   - **Run Playbook**:
     ```sh
     run playbook <playbook_path>
     ```
     - Example: `run playbook setup.yml`
   - **Destroy Droplet**:
     ```sh
     destroy
     ```
     - Example: `destroy`
   - **SSH into Droplet**:
     ```sh
     ssh
     ```
     - Example: `ssh`

## Examples

1. **Initialize Console**:
   ```sh
   python doconsole.py --token YOUR_DO_TOKEN --ssh_key PATH_TO_YOUR_SSH_KEY --init
   ```

2. **List Droplets and Playbooks on Startup**:
   ```sh
   python doconsole.py --token YOUR_DO_TOKEN --ssh_key PATH_TO_YOUR_SSH_KEY --init
   ```

3. **Run a Playbook on a Droplet**:
   ```sh
   set droplet 1
   set playbook 0
   run playbook
   ```

## Command Details

- **set**:
  - Set various configurations such as the target droplet, active playbook, API token, SSH key, default region, size, and image.

- **show**:
  - Display information about droplets, playbooks, tags, target droplet, and console info.

- **create**:
  - Create a new droplet with the specified name using default or configured settings.

- **add**:
  - Add a tag to the selected droplet(s).

- **run**:
  - Run the specified Ansible playbook on the target droplet.

- **destroy**:
  - Destroy the selected droplet(s).

- **ssh**:
  - Start an SSH session to the target droplet.

## Configuration

- **API Token**: Your DigitalOcean API token. Required for all operations.
- **SSH Key**: Path to your SSH private key. Required for connecting to droplets and running playbooks.
- **Ansible Playbooks Directory**: Directory containing your Ansible playbooks. Defaults to `./playbooks`.

## Contribution

Feel free to submit issues or pull requests if you have any improvements or bug fixes.

## License

This project is licensed under the [MIT License](LICENSE).

Feel free to contribute to this project by reporting issues or submitting pull requests on GitHub.