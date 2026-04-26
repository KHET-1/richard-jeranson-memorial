# Richard Jeranson Memorial

A small private website for the family — bio page, memory submission form, family-research guide.

**Password-gated** (HTTP Basic Auth). Family-only access; not crawlable.

## Run locally

```bash
cd /home/rathin/projects/tools/richard-jeranson-memorial
pip install -r requirements.txt
MEMORIAL_PASSWORD="the-shared-family-password" python3 app.py
```

Open `http://127.0.0.1:8087/` in a browser. The browser will prompt for username + password.
- Username: any value (e.g. "family")
- Password: whatever you set `MEMORIAL_PASSWORD` to

If `MEMORIAL_PASSWORD` is unset, a placeholder is used and a warning prints.
Always set the env var in production.

## Pages

- `/` — His story (bio: Duluth birth 1927, adoption by Ernst, V-6 USNR Corpus Christi 1946, Korean War, wood pattern shop, music, patents, Fridley, Mercy Hospital, Prescott AZ, Fort Snelling May 20)
- `/memories` — All submitted memories, newest first
- `/add` — Form for any family member to submit a memory + photos
- `/research` — Phone numbers, websites, forms for digging up more (NPRC SF-180, Fold3, Navy Memorial, MN Historical Society, FamilySearch census, funeral homes, etc.)

## Sharing with Mom (or anyone off this rig)

Three options, easiest first:

**1. Cloudflare tunnel (free, no setup, public URL in seconds)**
```bash
cloudflared tunnel --url http://127.0.0.1:8087
```
Output gives a `https://<random>.trycloudflare.com` URL. Send that to mom. Tunnel dies when you Ctrl+C the command.

**2. ngrok (similar, also free)**
```bash
ngrok http 8087
```

**3. LAN access (if mom is on the same network)**
Find this rig's IP:
```bash
hostname -I | awk '{print $1}'
```
Then mom opens `http://<that-ip>:8087/` from her device. Make sure firewall allows it:
```bash
sudo ufw allow 8087
```

## Storage

- Memories saved atomically to `data/memories.json` (fcntl.flock + fsync + os.replace)
- Photos saved to `data/photos/` with timestamped, slugged, UUID-suffixed filenames (no overwrite risk)
- 25 MB per photo; JPEG/PNG/GIF/WEBP/HEIC

## Backup

```bash
tar czf ~/Desktop/memorial-backup-$(date +%F).tgz \
    /home/rathin/projects/tools/richard-jeranson-memorial/data/
```

Run that the morning of May 20 and again after the funeral to capture everything mom and the family added.

## Adding things to the bio page

Edit `templates/index.html` directly. The bio is structured as `bio-card` divs — copy one as a template. No restart needed if you set `debug=True` in `app.py`; otherwise restart Flask.

## Adding photos for the bio (not user-submitted memories)

Drop them in `static/` and reference as `{{ url_for('static', filename='your-photo.jpg') }}` from a template.

## Health check

```bash
curl http://127.0.0.1:8087/healthz
# {"ok": true, "memories": <count>}
```
