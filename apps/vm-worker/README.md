# MyMediaVault VM Worker

VM-hosted Python worker that polls MongoDB for torrent metadata and preview
work. Metadata processing uses torrent documents as the queue, resolves
`.torrent` payloads through configured HTTP resolvers, uploads raw torrents to
R2-compatible storage, and writes parsed metadata back to the canonical torrent
document. Preview processing delegates concurrent media preview generation to
the `torrent-preview` worker harness and stores generated sheets and frames in
the same blob store.

## Run

```bash
cp .env.example .env
uv run mymediavault-vm-worker
```

Local native runs require Python 3.13, `libtorrent`, `ffmpeg`, and preferably
`ffprobe`. Environment variables are documented in `.env.example`.

## Deploy

The VM worker runs on a manually managed VM, outside Terraform-managed
Azure Container Apps. The dev workflow builds and pushes the Docker image to the
same Docker Hub namespace as the web image:

```text
<web-image-repo>-vm-worker:<commit-sha>
```

The tag is published for `linux/amd64` and `linux/arm64`; Docker pulls the VM's
matching platform automatically.

The VM must have Docker and systemd. If the Docker Hub repository is private,
authenticate Docker on the VM with a read-scoped token:

```bash
sudo docker login
```

### Configure environment

Store deployment config outside the repository:

```bash
sudo mkdir -p /etc/mymediavault
sudo install -m 600 /dev/null /etc/mymediavault/vm-worker.env
sudo editor /etc/mymediavault/vm-worker.env
```

Use `.env.example` for worker variables. Add the exact image tag:

```bash
MMV_VM_WORKER_IMAGE=<web-image-repo>-vm-worker:<commit-sha>
```

Deployment should be stateless: configure R2 for artifacts, MongoDB/Cosmos for
status, and treat container-local files as disposable.

### Install the service

Create `/etc/systemd/system/mymediavault-vm-worker.service`:

```ini
[Unit]
Description=MyMediaVault VM worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/mymediavault/vm-worker.env
ExecStartPre=-/usr/bin/docker rm -f mymediavault-vm-worker
ExecStartPre=/usr/bin/docker pull ${MMV_VM_WORKER_IMAGE}
ExecStart=/usr/bin/docker run --rm --name mymediavault-vm-worker --env-file /etc/mymediavault/vm-worker.env ${MMV_VM_WORKER_IMAGE}
ExecStop=/usr/bin/docker stop mymediavault-vm-worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mymediavault-vm-worker
sudo systemctl status mymediavault-vm-worker
```

Logs:

```bash
sudo journalctl -u mymediavault-vm-worker -f
sudo docker logs -f mymediavault-vm-worker
```

## Update

Set `MMV_VM_WORKER_IMAGE` to the new full image reference, then restart:

```bash
sudo editor /etc/mymediavault/vm-worker.env
sudo systemctl restart mymediavault-vm-worker
sudo systemctl status mymediavault-vm-worker
sudo journalctl -u mymediavault-vm-worker -f
```

Roll back by restoring the previous image tag and restarting the service.
