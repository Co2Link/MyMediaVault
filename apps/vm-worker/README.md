# MyMediaVault VM Worker

VM-hosted Python worker that polls MongoDB for torrent processing and
actor-identification work. A single FIFO torrent lifecycle resolves `.torrent`
payloads, downloads useful byte ranges, extracts clean anchor candidates,
selects preview frames with the OpenAI-backed chooser, and stores generated
sheets and frames. Sparse downloads retain their slot while capacity is
available, then save resume data and yield to the FIFO tail under queue
pressure. Sequential actor analysis consumes complete durable previews, uses
OpenCV YuNet and SFace to identify main actors, and stores reusable UUID
identities plus system-managed torrent assignments.

## Run

```bash
cp .env.example .env
uv run mymediavault-vm-worker
```

Local native runs require Python 3.13, `libtorrent`, `ffmpeg`, and preferably
`ffprobe`. Environment variables are documented in `.env.example`.

## Face Models

The offline actor-identification analyzer uses pinned OpenCV YuNet and SFace
ONNX models. The model binaries are not committed to Git. Download and verify
them from the checked-in manifest before running actor-identification
evaluation locally:

```bash
uv run python scripts/download_face_models.py --output .local/models
```

The VM-worker Docker build downloads and verifies the same model files, then
bakes them into the image. Runtime job processing does not download models.
Actor identification is enabled by default. See `.env.example` for the model
directory, polling interval, lease duration, and maximum attempt settings.

Run the strict offline fixture gate from `apps/vm-worker`:

```bash
uv run python scripts/evaluate_actor_identification.py \
  --previews ../../tmp/previews \
  --ground-truth ../../tmp/GT.json \
  --models-dir .local/models
```

The gate requires zero false merges, 100 percent recall, and zero unnecessary
identity splits.

Run the manual strict real-torrent preview gate from `apps/vm-worker` before a
preview-engine release:

```bash
uv run python tests/preview/scripts/run_test_torrents.py \
  --torrent-dir ../../tmp/test-torrents \
  --clear-cache
```

Each root-level or `strict/` fixture must produce a successful sheet with
exactly nine selected preview frames. Keep unstable sparse-swarm fixtures under
`../../tmp/test-torrents/truthful-partial` for diagnostic runs.

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
MMV_VM_WORKER_DEBUG_LOG_PATH=/var/log/mymediavault/vm-worker/debug.log
MMV_PREVIEW_CACHE_DIR=/var/cache/mymediavault/vm-worker
```

Configure R2 for artifacts and MongoDB/Cosmos for authoritative status. Persist
the rebuildable libtorrent cache across container replacement so sparse-swarm
progress is not discarded. The worker writes
human-readable `INFO` logs to Docker stdout and rotated JSON Lines `DEBUG` logs
to `/var/log/mymediavault/vm-worker/debug.log`. Store that debug path on the VM
host so it survives container replacement:

```bash
sudo install -d -m 750 -o 10001 -g 10001 /var/log/mymediavault/vm-worker
sudo install -d -m 750 -o 10001 -g 10001 /var/cache/mymediavault/vm-worker
```

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
ExecStartPre=/usr/bin/install -d -m 750 -o 10001 -g 10001 /var/log/mymediavault/vm-worker
ExecStartPre=/usr/bin/install -d -m 750 -o 10001 -g 10001 /var/cache/mymediavault/vm-worker
ExecStartPre=-/usr/bin/docker rm -f mymediavault-vm-worker
ExecStartPre=/usr/bin/docker pull ${MMV_VM_WORKER_IMAGE}
ExecStart=/usr/bin/docker run --rm --name mymediavault-vm-worker --publish 6881:6881/tcp --publish 6881:6881/udp --env-file /etc/mymediavault/vm-worker.env --mount type=bind,source=/var/log/mymediavault/vm-worker,target=/var/log/mymediavault/vm-worker --mount type=bind,source=/var/cache/mymediavault/vm-worker,target=/var/cache/mymediavault/vm-worker ${MMV_VM_WORKER_IMAGE}
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

Allow inbound TCP and UDP port `6881` through the VM host firewall and cloud
network security rules. The published ports let libtorrent accept peer
connections and DHT traffic through the worker container.

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
