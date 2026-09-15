# DigitalOcean Console (DOConsole)

`DOConsole` is a command-line console for tinkering in DigitalOcean fast: spin up a droplet, run an Ansible playbook against it, SSH in, tear it down. It's a personal tool, not infrastructure-as-code — there's no persisted droplet state, just a thin wrapper over the DigitalOcean API.

## Features

- **Manage Droplets**: list, create (single or multiple at once), destroy, and tag DigitalOcean droplets.
- **Auto-uploads your SSH key**: `create droplet` registers `DOCONSOLE_SSH_KEY`'s `.pub` file with your DO account if it isn't there yet (matched by fingerprint, so it never tries to re-upload one that's already registered — that mismatch is what used to cause "duplicate key" errors). On by default; see Configuration below to turn it off.
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
- **Power actions**: `power on|off|reboot|cycle|shutdown` without destroying the droplet.
- **Resize**: `resize <size> [--disk]` for an existing (powered-off) droplet.
- **Live watch**: `watch droplets` auto-refreshes the table until you Ctrl-C.
- **Self-check**: `show doctor` verifies Ansible/SSH are on PATH, the SSH key exists, the token is valid, and (on Linux/WSL) that a package manager is present.
- **Profiles**: `--profile <name>` for separate saved defaults, and optionally a separate saved token, per DigitalOcean account.
- **Random droplet names**: omit the name on `create droplet` for a Docker-style `adjective-noun-NN` name.

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
     show <droplets|playbooks|tags|target|info|snapshots|leases|doctor|firewalls>
     ```
     - `show droplets`/`show info` include an estimated running cost.
     - `show snapshots` lists your droplet snapshots (feeds `create droplet --from-snapshot`).
     - `show leases` lists pending TTL auto-destroys (with a dramatic countdown under a minute).
     - `show doctor` runs environment self-checks (Ansible/SSH on PATH, SSH key exists, token valid, playbooks present).
     - `show firewalls` lists firewalls in the account (name, status, inbound ports, attached droplet count).
     - Example: `show droplets`
   - **Create Droplet**:
     ```sh
     create droplet [name] [--count N] [--ttl 2h] [--user-data <path>] [--from-snapshot <id_or_index>] [--no-firewall] [--tags tag1,tag2]
     ```
     - `name` is optional — omit it for a randomly generated `adjective-noun-NN` name.
     - `--count N` creates `<name>-1..<name>-N` in a single API call.
     - `--ttl 2h` (also `90m`, `1d`, `30s`) schedules the droplet to auto-destroy later, even after you close the console — see `show leases`/`cancel ttl` below.
     - `--user-data <path>` passes a cloud-init script to run at boot.
     - `--from-snapshot <id_or_index>` boots from a snapshot instead of `set image`'s default (index is from `show snapshots`).
     - `--no-firewall` skips attaching the default SSH-only firewall for this create.
     - `--tags tag1,tag2` sets the tag(s) applied to this droplet (and, if the default firewall is on, what it's targeted with), overriding `DOCONSOLE_DEFAULT_TAG` for this create only — works whether or not a default is configured.
     - Example: `create droplet my-new-droplet --ttl 3h`, or just `create droplet` for a surprise name.
   - **Create Snapshot**:
     ```sh
     create snapshot <name>
     ```
     - Snapshots the single selected target droplet. Example: `create snapshot golden-image`
   - **Create Firewall**:
     ```sh
     create firewall <name> [--ports 22,80,443] [--attach] [--tag <name>[,<name>...]]
     ```
     - `--ports` defaults to `22` (SSH-only).
     - `--attach` attaches the current target droplet(s) at creation time (requires one selected via `set droplet`) — DigitalOcean's explicit, one-time `droplet_ids` association.
     - `--tag <name>` instead targets every droplet carrying at least one of the given (comma-separated) tags, present *or future* — DigitalOcean's other, self-updating association mechanism. `--attach` and `--tag` can be combined.
     - Example: `create firewall web-only --ports 80,443`, or `create firewall ssh-only --tag doconsole` for a firewall that auto-applies to anything you tag later.
   - **Create Tag**:
     ```sh
     create tag <tag_name>
     ```
     - Creates a tag without needing a target droplet selected (unlike `add tag`, which also assigns it). Example: `create tag staging`
   - **Add Tag**:
     ```sh
     add tag <tag_name>
     ```
     - Example: `add tag production`
   - **Add to Firewall**:
     ```sh
     add firewall <name_or_id>
     ```
     - Adds the current target droplet(s) to an existing firewall (matched by exact name, or a literal ID). DigitalOcean's firewall-droplet relationship is only ever managed from the firewall's side — there's no "attach a firewall to a droplet" API call — so, like `add tag`, this reads as "attach X to my droplet(s)" from the console while making the DO-correct call underneath. Example: `add firewall web-only`
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
   - **Power actions**:
     ```sh
     power <on|off|reboot|cycle|shutdown>
     ```
     - Acts on the current target (single droplet, `all`, or a `tag:x` selection), without destroying anything.
   - **Resize**:
     ```sh
     resize <size> [--disk]
     ```
     - Target droplet must already be powered off (`power off` first). `--disk` also grows the disk and is permanent/irreversible — confirmed separately.
   - **Watch droplets live**:
     ```sh
     watch droplets [interval_seconds]
     ```
     - Refreshes the droplet table every 5 seconds (or `interval_seconds`) until Ctrl-C.
   - **SSH into Droplet**:
     ```sh
     ssh [-p|--port <port>]
     ```
     - Defaults to port 22. Example: `ssh --port 64295` for a droplet with SSH moved off the default port (e.g. a T-Pot honeypot, which relocates real SSH so port 22 can run the honeypot).

## Examples

1. **Skip the startup banner and droplet/playbook listing** (also skips the droplet-list API call that listing makes — useful if you just want a prompt fast):
   ```sh
   python doconsole.py --token YOUR_DO_TOKEN --quiet
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
- **show**: display droplets (with estimated cost), playbooks, tags, the current target, console/account info, snapshots, pending TTL auto-destroys, firewalls, or an environment self-check (`doctor`).
- **create**: create one or more new droplets with the configured defaults (optionally random-named, from cloud-init user-data or a snapshot, with a TTL), snapshot the selected droplet, create a firewall (by explicit attach and/or tag), or create a standalone tag.
- **add**: add a tag, or add to an existing firewall, for the selected droplet(s).
- **run**: run a playbook against the target droplet(s).
- **power**: power on/off/reboot/cycle/shutdown the target droplet(s) without destroying them.
- **resize**: resize the target droplet (must be powered off first).
- **watch**: auto-refresh `show droplets` until Ctrl-C.
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
- **Profiles**: pass `--profile <name>` to use `~/.doconsole/profiles/<name>.json` instead of the default config file — separate region/size/image/vpc/ssh-key defaults per profile. The token still isn't saved automatically even under a profile; run `set token <value> --save` to save it into the *active* profile (or the default config, if no `--profile` was given) — this is what makes profiles actually useful for switching between DigitalOcean accounts without retyping a token every session.
- **Auto-upload SSH key**: on by default. Set `DOCONSOLE_AUTO_UPLOAD_SSH_KEY=false` (env var or `.env`) to disable — see `.env.example`. `show doctor` reports whether your local key is currently registered.
- **Default tag(s)**: off (unset) by default. Set `DOCONSOLE_DEFAULT_TAG=<name>` (env var or `.env`), or a comma-separated list (`DOCONSOLE_DEFAULT_TAG=doconsole,ssh-only`), to auto-tag every new droplet with all of them. When set, the default SSH-only firewall (see `set firewall`) is created targeting those tags instead of explicit per-droplet IDs, so it auto-applies to any droplet carrying at least one of them — present or future — with no per-droplet attach call needed. This is how you'd reuse a firewall you already manage this way outside doconsole: point `DOCONSOLE_DEFAULT_TAG` at that exact same tag (check the spelling/case with `show tags` first — tag matching is an exact string match), and consider `set firewall off` so doconsole doesn't also spin up its own separate firewall.

### TTL auto-destroy caveats

`--ttl` works by spawning a small detached background process that sleeps until the deadline, then destroys the droplet directly via the API — it survives you closing the console. That also means it's an unattended process: if the machine (or WSL instance) restarts before the deadline, the watcher dies silently and the droplet will *not* be auto-destroyed. `show leases` flags this as `STALE` when it detects the watcher process is gone, so you're not left trusting a safety net that's no longer armed.

## Project layout

- `doconsole.py` — the `cmd.Cmd` console and CLI entrypoint.
- `do_api.py` — thin `requests`-based client for the DigitalOcean REST API.
- `formatting.py` — `rich`-based table/column/status output helpers (color, borders).
- `config.py` — loads/saves `~/.doconsole/config.json` (or a named profile under `~/.doconsole/profiles/`).
- `ttl.py` — TTL lease bookkeeping and the detached auto-destroy watcher process.
- `pickers.py` — thin `questionary` wrapper for the arrow-key selection menus.
- `playbooks/` — sample Ansible playbooks, runnable via `run playbook` (see below).
- `tests/` — pytest suite (formatting is tested directly, `do_api` against mocked HTTP via `responses`, `ttl` with `subprocess.Popen` mocked, and the console via `cmd.Cmd.onecmd` against a fake API client).

## Included playbooks

All playbooks target `hosts: all` and use `-e name=value` for non-interactive overrides of any `vars:` they define, so they work equally well run interactively (`run playbook`, which inherits the console's own terminal, so `vars_prompt` prompts work fine) or scripted via `--exec`/CI with `-e`.

- `add_user.yml` — create a user (prompts for username/password).
- `esential_tools.yml` — installs `curl`, `vim`, `htop`.
- `update_droplet.yml` — updates the apt cache.
- `transfer_folder.yml` — copies a local folder to the remote home directory, nested under its own name (prompts for the folder path).
- `transfer_directory_contents.yml` — copies the *contents* of a chosen local directory into a chosen remote directory (not nested under the source folder's name), preserving file permissions. Prompts interactively for both the source and destination directory.
- `install_docker.yml` — installs Docker CE + the Compose plugin on Ubuntu; override `-e docker_users='["someuser"]'` to add non-root users to the `docker` group.
- `install_nginx.yml` — installs and starts nginx with a placeholder page; override `-e nginx_index_message="..."` to customize it.
- `create_swap.yml` — creates and enables a swap file (defaults to 1GB, handy on the default `s-1vcpu-1gb` size); override `-e swap_size_gb=2`.

## Development

```sh
pip install -r requirements-dev.txt
pytest
```

## Contribution

Feel free to submit issues or pull requests if you have any improvements or bug fixes.

## License

This project is licensed under the [MIT License](LICENSE).
