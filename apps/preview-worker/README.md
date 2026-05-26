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

Local native runs require Python 3.13, `libtorrent`, `ffmpeg`, and preferably
`ffprobe`. Environment variables are documented in `.env.example`.

## Deploy

The preview worker runs on a manually managed VM, outside Terraform-managed
Azure Container Apps. The dev workflow builds and pushes the Docker image to the
same Docker Hub namespace as the web image:

```text
<web-image-repo>-preview-worker:<commit-sha>
```

The VM must have Docker and systemd. If the Docker Hub repository is private,
authenticate Docker on the VM with a read-scoped token:

```bash
sudo docker login
```

### Configure environment

Store deployment config outside the repository:

```bash
sudo mkdir -p /etc/mymediavault
sudo install -m 600 /dev/null /etc/mymediavault/preview-worker.env
sudo editor /etc/mymediavault/preview-worker.env
```

Use `.env.example` for worker variables. Add the exact image tag:

```bash
MMV_PREVIEW_WORKER_IMAGE=<web-image-repo>-preview-worker:<commit-sha>
```

Deployment should be stateless: configure R2 for artifacts, MongoDB/Cosmos for
status, and treat container-local files as disposable.

### Install the service

Create `/etc/systemd/system/mymediavault-preview-worker.service`:

```ini
[Unit]
Description=MyMediaVault preview worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/mymediavault/preview-worker.env
ExecStartPre=-/usr/bin/docker rm -f mymediavault-preview-worker
ExecStartPre=/usr/bin/docker pull ${MMV_PREVIEW_WORKER_IMAGE}
ExecStart=/usr/bin/docker run --rm --name mymediavault-preview-worker --env-file /etc/mymediavault/preview-worker.env ${MMV_PREVIEW_WORKER_IMAGE}
ExecStop=/usr/bin/docker stop mymediavault-preview-worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mymediavault-preview-worker
sudo systemctl status mymediavault-preview-worker
```

Logs:

```bash
sudo journalctl -u mymediavault-preview-worker -f
sudo docker logs -f mymediavault-preview-worker
```

## Update

Set `MMV_PREVIEW_WORKER_IMAGE` to the new full image reference, then restart:

```bash
sudo editor /etc/mymediavault/preview-worker.env
sudo systemctl restart mymediavault-preview-worker
sudo systemctl status mymediavault-preview-worker
sudo journalctl -u mymediavault-preview-worker -f
```

Roll back by restoring the previous image tag and restarting the service.
