# DigitalOcean Console (DOConsole)

`DOConsole` is a command-line console for tinkering in DigitalOcean fast: spin up a droplet, run an Ansible playbook against it, SSH in, tear it down. It's a personal tool, not infrastructure-as-code — there's no persisted droplet state, just a thin wrapper over the DigitalOcean API.

## Features

- **Manage Droplets**: list, create (single or multiple at once), destroy, and tag DigitalOcean droplets.
- **Select by index, name, or tag**: `set droplet 0`, `set droplet web-1`, or `set droplet tag:web` to act on a group at once.
- **TTL auto-destroy**: `create droplet foo --ttl 2h` schedules the droplet to destroy itself later, even if you close the console.
- **Cloud-init support**: `--user-data <path>` bootstraps a droplet at boot without needing SSH/Ansible.
- **Snapshots**: snapshot a configured droplet, then boot new droplets from it instantly.
- **Default SSH-only firewall**: new droplets are attached to a shared "SSH only" Cloud Firewall unless turned off.
- **Cost visibility**: estimated running cost shown in `show droplets`/`show info`.
- **Color and readable tables**: output is rendered with `rich` — bordered tables, and droplet status colored (green/yellow/red for active/transitional/off). Falls back to plain output automatically when not attached to a real terminal.
- **Run Ansible Playbooks**: execute Ansible playbooks against a droplet (or a tag/`all` selection).
- **SSH Access**: SSH into a droplet directly from the console.
- **Scriptable**: `--exec "cmd1; cmd2"` runs commands non-interactively and exits.
- **Customizable Defaults**: region, size, image, and VPC for new droplets, persisted between sessions, picked via arrow-key menus.
- **Persistent command history** across sessions.

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
     set <droplet|playbook|token|ssh_key|region|size|image|vpc|firewall>
     ```
     - `set droplet <index|name|all|tag:<name>>` — select one droplet by index or exact name, all of them, or every droplet carrying a tag.
     - `set region`/`set size`/`set image`/`set vpc` open an arrow-key picker (sizes show hourly/monthly price).
     - `set firewall <on|off>` — toggle whether new droplets get the default SSH-only firewall.
     - Example: `set droplet web-1`, `set droplet tag:staging`
   - **Show Information**:
     ```sh
     show <droplets|playbooks|tags|target|info|snapshots|leases>
     ```
     - `show droplets`/`show info` include an estimated running cost.
     - `show snapshots` lists your droplet snapshots (feeds `create droplet --from-snapshot`).
     - `show leases` lists pending TTL auto-destroys.
     - Example: `show droplets`
   - **Create Droplet**:
     ```sh
     create droplet <name> [--count N] [--ttl 2h] [--user-data <path>] [--from-snapshot <id_or_index>] [--no-firewall]
     ```
     - `--count N` creates `<name>-1..<name>-N` in a single API call.
     - `--ttl 2h` (also `90m`, `1d`, `30s`) schedules the droplet to auto-destroy later, even after you close the console — see `show leases`/`cancel ttl` below.
     - `--user-data <path>` passes a cloud-init script to run at boot.
     - `--from-snapshot <id_or_index>` boots from a snapshot instead of `set image`'s default (index is from `show snapshots`).
     - `--no-firewall` skips attaching the default SSH-only firewall for this create.
     - Example: `create droplet my-new-droplet --ttl 3h`
   - **Create Snapshot**:
     ```sh
     create snapshot <name>
     ```
     - Snapshots the single selected target droplet. Example: `create snapshot golden-image`
   - **Add Tag**:
     ```sh
     add tag <tag_name>
     ```
     - Example: `add tag production`
   - **Run Playbook**:
     ```sh
     run playbook <playbook_path>
     ```
     - Runs against every droplet in the current target (single, `all`, or a tag selection).
     - Example: `run playbook setup.yml`
   - **Destroy Droplet**:
     ```sh
     destroy [-y|--yes]
     ```
     - `--yes` skips the confirmation prompt, for scripting.
   - **Cancel a pending auto-destroy**:
     ```sh
     cancel ttl <name_or_id>
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

3. **Spin up a throwaway box that cleans up after itself**:
   ```sh
   create droplet scratch --ttl 2h
   ```

4. **Script a full create/configure/destroy cycle non-interactively**:
   ```sh
   python doconsole.py --exec "create droplet scratch --ttl 1h; run playbook setup.yml; destroy -y"
   ```

## Command Details

- **set**: configure the target droplet (by index/name/`all`/`tag:x`), active playbook, API token (session-only), SSH key, the default region/size/image/vpc (via arrow-key pickers) for new droplets, and whether the default SSH-only firewall is attached.
- **show**: display droplets (with estimated cost), playbooks, tags, the current target, console/account info, snapshots, or pending TTL auto-destroys.
- **create**: create one or more new droplets with the configured defaults (optionally from cloud-init user-data or a snapshot, with a TTL), or snapshot the selected droplet.
- **add**: add a tag to the selected droplet(s).
- **run**: run a playbook against the target droplet(s).
- **destroy**: destroy the selected droplet(s), with a confirmation prompt (skippable with `--yes`).
- **cancel**: cancel a pending TTL auto-destroy.
- **ssh**: start an SSH session to the target droplet.

## Configuration

- **API Token**: your DigitalOcean API token. Resolved in order: `--token` flag, `DO_API_TOKEN` environment variable, `DO_API_TOKEN` in `.env`. Never written to disk by the console itself.
- **SSH Key**: path to your SSH private key, used for both `ssh` and `run playbook`. Resolved in order: `--key` flag, `DOCONSOLE_SSH_KEY` environment variable, `DOCONSOLE_SSH_KEY` in `.env`, else `~/.ssh/id_rsa`.
- **Ansible Playbooks Directory**: resolved in order: `--playbooks` flag, `DOCONSOLE_PLAYBOOKS_DIR` environment variable, `DOCONSOLE_PLAYBOOKS_DIR` in `.env`, else `./playbooks`.
- **`.env` file**: copy `.env.example` to `.env` to set any of the above without passing flags or exporting real environment variables. A real environment variable of the same name always overrides the value in `.env`. `.env` is listed in `.gitignore` and must never be committed.
- **Other defaults** (`region`, `size`, `image`, `vpc`, `attach_ssh_firewall`): saved to `~/.doconsole/config.json` whenever changed via `set`, so they carry over between sessions.
- **Command history**: persisted at `~/.doconsole/history` across sessions.
- **TTL leases**: tracked at `~/.doconsole/leases.json` (see `show leases`).

### TTL auto-destroy caveats

`--ttl` works by spawning a small detached background process that sleeps until the deadline, then destroys the droplet directly via the API — it survives you closing the console. That also means it's an unattended process: if the machine (or WSL instance) restarts before the deadline, the watcher dies silently and the droplet will *not* be auto-destroyed. `show leases` flags this as `STALE` when it detects the watcher process is gone, so you're not left trusting a safety net that's no longer armed.

## Project layout

- `doconsole.py` — the `cmd.Cmd` console and CLI entrypoint.
- `do_api.py` — thin `requests`-based client for the DigitalOcean REST API.
- `formatting.py` — `rich`-based table/column/status output helpers (color, borders).
- `config.py` — loads/saves `~/.doconsole/config.json`.
- `ttl.py` — TTL lease bookkeeping and the detached auto-destroy watcher process.
- `pickers.py` — thin `questionary` wrapper for the arrow-key selection menus.
- `tests/` — pytest suite (formatting is tested directly, `do_api` against mocked HTTP via `responses`, `ttl` with `subprocess.Popen` mocked, and the console via `cmd.Cmd.onecmd` against a fake API client).

## Development

```sh
pip install -r requirements-dev.txt
pytest
```

## Contribution

Feel free to submit issues or pull requests if you have any improvements or bug fixes.

## License

This project is licensed under the [MIT License](LICENSE).
