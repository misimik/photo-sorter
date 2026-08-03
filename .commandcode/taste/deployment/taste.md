# Deployment
- For the photo-sorter deployment, user prefers using Portainer to manage containers and GitHub as the code transfer method rather than scp/direct copy. Confidence: 0.65
- For remote NAS/network bridge workflows (WSL2 + WireGuard + CIFS), user prefers deploying directly to the home server (192.168.0.31) instead of pushing the stack through WSL2. Confidence: 0.60
- For the photo-sorter deployment, the server's photos mount path is /srv/mergerfs/pool/pool/photos/Unsorted (container /photos), with Best exported at /srv/mergerfs/pool/pool/photos/Best (not /mnt/nas/pool/photos). Confidence: 0.80
- For the photo-sorter production deployment, the app should bind to port 8420, not 8080 (8080 is unavailable on the host). Confidence: 0.60
- For the photo-sorter Portainer stack deployment, rename the env file to stack.env (Portainer convention) rather than .env (dev naming). Confidence: 0.70
- For the photo-sorter Portainer deployment, the container image is built locally (tagged photo-sorter:local from the repo's Dockerfile), not pulled from a registry; the Portainer "Build" option must be checked or redeploy fails with "pull access denied". Confidence: 0.70
- For photo-sorter, Portainer deploys `docker-compose.yml` by default rather than `compose.prod.yml`, so `docker-compose.yml` must have working defaults (e.g., `${PHOTOS_DIR:-/srv/mergerfs/pool/pool/photos/Unsorted}` and `${BEST_DIR:-/srv/.../Best}`) so empty env vars don't collapse the /photos and /export mounts. Confidence: 0.65
