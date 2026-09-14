# DigitalOcean Console (DOConsole)

`DOConsole` is a command-line console for tinkering in DigitalOcean fast: spin up a droplet, run an Ansible playbook against it, SSH in, tear it down. It's a personal tool, not infrastructure-as-code — there's no persisted droplet state, just a thin wrapper over the DigitalOcean API.

## Features

- **Manage Droplets**: list, create, destroy, and tag DigitalOcean droplets.
- **Run Ansible Playbooks**: execute Ansible playbooks against a droplet.
- **SSH Access**: SSH into a droplet directly from the console.
- **Customizable Defaults**: region, size, image, and VPC for new droplets, persisted between sessions.

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

3. **Ensure Ansible is Installed** (only needed for `run playbook`):
   ```sh
   sudo apt install ansible
   ```

## Usage

1. **Run the Console**:
   ```sh
   python doconsole.py --token YOUR_DO_TOKEN --key PATH_TO_YOUR_SSH_KEY
   ```
   Instead of passing flags, copy `.env.example` to `.env` and fill in your values:
   ```sh
   cp .env.example .env
   ```
   `.env` is only a fallback — a `--token`/`--key`/`--playbooks` flag or a real environment variable of the same name always takes priority over it. `.env` is gitignored, so your token never gets committed.

2. **Commands Overview**:
   - **Set Configurations**:
     ```sh
     set <droplet|playbook|token|ssh_key|region|size|image|vpc>
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
   - **SSH into Droplet**:
     ```sh
     ssh
     ```

## Examples

1. **Show droplets and playbooks on startup**:
   ```sh
   python doconsole.py --token YOUR_DO_TOKEN --init
   ```

2. **Run a playbook on a droplet**:
   ```sh
   set droplet 1
   set playbook 0
   run playbook
   ```

## Command Details

- **set**: configure the target droplet, active playbook, API token (session-only), SSH key, and the default region/size/image/vpc for new droplets.
- **show**: display droplets, playbooks, tags, the current target, or console/account info.
- **create**: create a new droplet with the configured defaults.
- **add**: add a tag to the selected droplet(s).
- **run**: run a playbook against the target droplet.
- **destroy**: destroy the selected droplet(s), with a confirmation prompt.
- **ssh**: start an SSH session to the target droplet.

## Configuration

- **API Token**: your DigitalOcean API token. Resolved in order: `--token` flag, `DO_API_TOKEN` environment variable, `DO_API_TOKEN` in `.env`. Never written to disk by the console itself.
- **SSH Key**: path to your SSH private key, used for both `ssh` and `run playbook`. Resolved in order: `--key` flag, `DOCONSOLE_SSH_KEY` environment variable, `DOCONSOLE_SSH_KEY` in `.env`, else `~/.ssh/id_rsa`.
- **Ansible Playbooks Directory**: resolved in order: `--playbooks` flag, `DOCONSOLE_PLAYBOOKS_DIR` environment variable, `DOCONSOLE_PLAYBOOKS_DIR` in `.env`, else `./playbooks`.
- **`.env` file**: copy `.env.example` to `.env` to set any of the above without passing flags or exporting real environment variables. A real environment variable of the same name always overrides the value in `.env`. `.env` is listed in `.gitignore` and must never be committed.
- **Other defaults** (`region`, `size`, `image`, `vpc`): saved to `~/.doconsole/config.json` whenever changed via `set`, so they carry over between sessions.

## Project layout

- `doconsole.py` — the `cmd.Cmd` console and CLI entrypoint.
- `do_api.py` — thin `requests`-based client for the DigitalOcean REST API.
- `formatting.py` — table/column output helpers.
- `config.py` — loads/saves `~/.doconsole/config.json`.
- `tests/` — pytest suite (formatting is tested directly, `do_api` against mocked HTTP via `responses`, and the console via `cmd.Cmd.onecmd` against a fake API client).

## Development

```sh
pip install -r requirements-dev.txt
pytest
```

## Contribution

Feel free to submit issues or pull requests if you have any improvements or bug fixes.

## License

This project is licensed under the [MIT License](LICENSE).
