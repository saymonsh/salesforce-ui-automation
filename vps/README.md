# VPS update mirror

The filtered gov machine can't reach GitHub (HTTPS out blocked) but **SSH out
works**. So updates flow through the VPS:

```
CI (unfiltered)  --HTTPS POST-->  VPS  <--SSH scp pull--  gov machine
   build+release      (token)    mirror     (key)          (dev-mode app)
```

- **CI → VPS**: `kivun_update_server.py` receives each tagged installer over
  HTTPS and writes `Setup-latest.exe` + `latest.json` to `/srv/kivun-updates`.
- **VPS → gov**: the app `scp`-pulls those two files (reusing the log-mirror SSH
  key/host) and verifies the sha256 — see `src/core/update_checker.py`.

The contract (paths, header names, manifest shape) is shared by
`kivun_update_server.py`, `src/core/update_checker.py`, and the
`Push installer to VPS mirror` step in `.github/workflows/build-release.yml`.
Change one, change all three.

## Deploy the upload endpoint

```sh
# 1. Dedicated low-priv user + mirror dir
sudo useradd -r -s /usr/sbin/nologin kivun
sudo mkdir -p /srv/kivun-updates && sudo chown kivun:kivun /srv/kivun-updates

# 2. App + service
sudo mkdir -p /opt/kivun
sudo cp kivun_update_server.py /opt/kivun/
sudo cp kivun-update.service /etc/systemd/system/
sudoedit /etc/systemd/system/kivun-update.service   # set KIVUN_UPLOAD_TOKEN
sudo systemctl daemon-reload && sudo systemctl enable --now kivun-update

# 3. Self-check (optional, before wiring nginx)
python3 test_update_server.py
```

Bind localhost only and front it with the existing TLS reverse proxy. Example
nginx location (maps a public HTTPS path to the local server):

```nginx
location /api/kivun/upload {
    proxy_pass http://127.0.0.1:8099/;
    client_max_body_size 200m;   # installer is ~65 MB
}
```

## Gov-machine read access

The app pulls with the **same SSH key/host already configured for the log
mirror** (`SSH_KEY_PATH`, host parsed from `SSH_REMOTE`). That key's user just
needs **read** access to `/srv/kivun-updates`:

```sh
sudo setfacl -R -m u:<ssh-user>:rx /srv/kivun-updates   # or chmod o+rx
```

## GitHub secrets (repo → Settings → Secrets → Actions)

| Secret | Value |
|--------|-------|
| `KIVUN_UPLOAD_URL`   | `https://shalom.5784.link/api/kivun/upload` |
| `KIVUN_UPLOAD_TOKEN` | the same token set in the service env |

Without these the CI push step skips silently (the GitHub Release still
publishes), so the open-network channel keeps working regardless.
