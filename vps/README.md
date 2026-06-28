# VPS update mirror

The filtered gov machine can't reach GitHub (HTTPS out blocked) but **SSH out
works**. So updates flow through the VPS (`shalom.5784.link`, 149.28.57.61):

```
CI (unfiltered)  --HTTPS POST-->  VPS  <--SSH scp pull--  gov machine
   build+release    (token)      mirror     (root key)     (Kivun app)
```

- **CI → VPS**: each tagged installer is POSTed to `/api/kivun/upload` over
  HTTPS (the `Push installer to VPS mirror` step in
  `.github/workflows/build-release.yml`).
- **VPS → gov**: the app `scp`-pulls `latest.json` + `Setup-latest.exe` and
  verifies the sha256 — see `src/core/update_checker.py`.

## How it's deployed (already live)

The upload endpoint is **not** a standalone service — it's a single additive
route in the existing `shalom.5784.link` Express app
(`/root/vultr-configs/shalom.5784.link/server.js`), which already runs behind the
`my-nginx-proxy` container (TLS via Let's Encrypt, Cloudflare in front). This
reuses the existing routing/TLS and adds no new container (the box has ~1 GB RAM).

- The route is `vps/kivun-upload-route.js` in this repo — appended verbatim to
  `server.js` (after `app.listen`; Express matches routes per-request so order
  vs `listen()` doesn't matter). A backup sits at `server.js.kivun.bak`.
- It writes into `kivun-updates/` under the app's host-mounted project dir →
  on the box: `/root/vultr-configs/shalom.5784.link/kivun-updates/`
  (`Setup-latest.exe` atomic + `latest.json {version,file,sha256}`).
  Overwrite-latest = **zero disk accumulation**.
- nginx needs **no change**: `/api/...` falls under `location /` → app:3000,
  which already allows `client_max_body_size 500m`.

### To update the route

Edit `vps/kivun-upload-route.js` here, then on the box replace the block in
`server.js` and restart only the app service:

```sh
cd /root/vultr-configs/shalom.5784.link
docker exec my-node-app node --check /usr/src/app/server.js   # validate first
docker compose restart app                                     # ~2s downtime
```

To remove the feature entirely: restore `server.js.kivun.bak`, delete the
`KIVUN_UPLOAD_TOKEN` line in `.env`, `docker compose restart app`.

## Auth

A **dedicated** bearer token (`KIVUN_UPLOAD_TOKEN` in the app's `.env`),
constant-time compared — deliberately *not* the dashboard Basic-auth creds,
which also unlock `run-backup`/`run-git`.

## Gov-machine read access

The app pulls with the **same SSH key/host already used for the log mirror**
(`SSH_KEY_PATH`, host parsed from `SSH_REMOTE`). That user is `root`, which owns
`kivun-updates/`, so no extra ACL is needed.

## GitHub secrets (repo → Settings → Secrets → Actions)

| Secret | Value |
|--------|-------|
| `KIVUN_UPLOAD_URL`   | `https://shalom.5784.link/api/kivun/upload` |
| `KIVUN_UPLOAD_TOKEN` | the token in the app's `.env` |

Without these the CI push step skips silently (the GitHub Release still
publishes), so the open-network channel keeps working regardless.
