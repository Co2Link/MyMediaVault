# MyMediaVault Preview Worker

VM-hosted Python worker that polls MongoDB for torrents needing preview images,
uses Beanie models that mirror the Mongoose torrent document, delegates polling
and concurrent execution to the `torrent-preview` worker harness, uploads the
generated sheet and frames to R2-compatible storage, and writes preview status
back to the canonical torrent document.

## Run

```bash
cp .env.example .env
uv run mymediavault-preview-worker
```

Environment variables are documented in `.env.example`. Copy that file for
local runs, and use the same names when rendering deployment configuration on
the VM.

The VM runtime must provide Python 3.13, `libtorrent`, `ffmpeg`, and preferably
`ffprobe`. `OPENAI_API_KEY` is required by the default `torrent-preview` engine.

## Deploy

The preview worker is intentionally hosted on a VM instead of the repository's
Terraform-managed Azure Container Apps environment. It runs as a long-lived
polling process, generates previews with native media tooling, and needs a host
with predictable CPU, disk, `ffmpeg`, `ffprobe`, and `libtorrent` support.

Use an Azure Linux VM in the same environment as the dev app. Start with a small
VM and set `MMV_PREVIEW_WORKER_MAX_CONCURRENCY` conservatively, then increase it
after observing CPU, memory, disk, network, R2, MongoDB, and OpenAI API usage.

### Provision the host

Install the host packages and `uv`:

```bash
sudo apt-get update
sudo apt-get install -y git curl ffmpeg libtorrent-rasterbar-dev
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install Python 3.13 through `uv` if the image does not already provide it:

```bash
uv python install 3.13
```

Create an application directory and install the worker dependencies:

```bash
sudo mkdir -p /opt/mymediavault
sudo chown "$USER":"$USER" /opt/mymediavault
git clone https://github.com/<owner>/<repo>.git /opt/mymediavault
cd /opt/mymediavault/apps/preview-worker
uv sync --locked
```

Replace `<owner>/<repo>` with the repository remote used for the deployment.

### Configure environment

Store deployment configuration outside the repository in a root-owned file:

```bash
sudo mkdir -p /etc/mymediavault
sudo install -m 600 /dev/null /etc/mymediavault/preview-worker.env
sudo editor /etc/mymediavault/preview-worker.env
```

Use `.env.example` as the source of truth for the expected variable names and
defaults. Do not commit real environment files or secrets. Prefer Azure Key
Vault or another secret store for long-lived environments, and render only the
values the service needs onto the VM.

### Install the service

Create `/etc/systemd/system/mymediavault-preview-worker.service`:

```ini
[Unit]
Description=MyMediaVault preview worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/mymediavault/apps/preview-worker
EnvironmentFile=/etc/mymediavault/preview-worker.env
ExecStart=/home/azureuser/.local/bin/uv run mymediavault-preview-worker
Restart=always
RestartSec=10
User=azureuser

[Install]
WantedBy=multi-user.target
```

Adjust `User` and the `uv` path for the VM account. Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mymediavault-preview-worker
sudo systemctl status mymediavault-preview-worker
```

View logs with:

```bash
journalctl -u mymediavault-preview-worker -f
```

For Azure operations, attach Azure Monitor Agent or another log collector after
the service is stable.

## Update

Before updating, check the current worker state and logs:

```bash
sudo systemctl status mymediavault-preview-worker
journalctl -u mymediavault-preview-worker -n 100 --no-pager
```

Deploy a new revision:

```bash
cd /opt/mymediavault
git fetch --prune
git checkout <branch-or-tag>
git pull --ff-only
cd apps/preview-worker
uv sync --locked
sudo systemctl restart mymediavault-preview-worker
sudo systemctl status mymediavault-preview-worker
```

Use the same branch or tag strategy as the web and worker deployment. If
`pyproject.toml` or `uv.lock` changes, `uv sync --locked` updates the virtual
environment to the pinned dependency set.

After restarting, confirm that the service is polling cleanly and writing
preview results:

```bash
journalctl -u mymediavault-preview-worker -f
```

If an update changes environment variables, edit
`/etc/mymediavault/preview-worker.env`, then restart the service. If an update
changes native runtime requirements, install the host packages first and restart
only after `uv sync --locked` succeeds.
