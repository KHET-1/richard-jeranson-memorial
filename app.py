"""Richard Jeranson Memorial — Flask app for family to view bio + add memories.

Run:
    cd /home/rathin/projects/tools/richard-jeranson-memorial
    MEMORIAL_PASSWORD="your-shared-family-password" python3 app.py

Local URL: http://127.0.0.1:8087
LAN URL:   http://<rig-ip>:8087
Public:    cloudflared tunnel --url http://127.0.0.1:8087

Auth: HTTP Basic Auth.
  Username: any value (typically the family name, e.g. "family")
  Password: value of MEMORIAL_PASSWORD env var
If MEMORIAL_PASSWORD is unset, the site falls back to "REPLACE_ME_SET_ENV_VAR"
and prints a clear warning. Always set the env var in production.
"""
import json, os, fcntl, uuid, time, re, hmac
from functools import wraps
from pathlib import Path
from datetime import datetime, timezone
from flask import (
    Flask, render_template, request, redirect, url_for, send_from_directory,
    abort, Response
)
from werkzeug.utils import secure_filename

BASE = Path(__file__).parent
DATA = BASE / "data"
PHOTOS = DATA / "photos"
MEMORIES = DATA / "memories.json"
ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp", "heic"}
MAX_PHOTO_MB = 25

DATA.mkdir(exist_ok=True)
PHOTOS.mkdir(exist_ok=True)
if not MEMORIES.exists():
    MEMORIES.write_text("[]\n")

# ---- Password gate (HTTP Basic Auth) ---------------------------------------
PASSWORD = os.environ.get("MEMORIAL_PASSWORD", "REPLACE_ME_SET_ENV_VAR")
if PASSWORD == "REPLACE_ME_SET_ENV_VAR":
    print("[memorial] WARN: MEMORIAL_PASSWORD env var not set; using placeholder. "
          "Set the env var before deploying or sharing the URL.")

# Allow public health probe (uptime checks, deployment platforms, no PII)
PUBLIC_PATHS = {"/healthz"}


def _check_password(submitted: str) -> bool:
    """Constant-time password compare to defeat timing attacks."""
    return hmac.compare_digest(submitted or "", PASSWORD)


def _auth_challenge() -> Response:
    return Response(
        "Authentication required. Ask Ryan for the family password.",
        401,
        {"WWW-Authenticate": 'Basic realm="Richard Jeranson Memorial"'},
    )


def require_password(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.path in PUBLIC_PATHS:
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or not _check_password(auth.password):
            return _auth_challenge()
        return f(*args, **kwargs)
    return wrapper


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_PHOTO_MB * 1024 * 1024


@app.before_request
def _gate():
    """Apply the password gate to every request except PUBLIC_PATHS."""
    if request.path in PUBLIC_PATHS:
        return None
    auth = request.authorization
    if not auth or not _check_password(auth.password):
        return _auth_challenge()
    return None


def atomic_append_memory(entry: dict) -> None:
    """Append-with-flock + atomic-rewrite of memories.json."""
    fd = os.open(str(MEMORIES), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.fstat(fd).st_size
        body = os.read(fd, max(size, 2)).decode("utf-8") if size else "[]"
        try:
            arr = json.loads(body)
            if not isinstance(arr, list):
                arr = []
        except json.JSONDecodeError:
            arr = []
        arr.append(entry)
        new = json.dumps(arr, indent=2, ensure_ascii=False).encode("utf-8")
        tmp = str(MEMORIES) + ".tmp"
        with open(tmp, "wb") as f:
            f.write(new)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(MEMORIES))
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def load_memories() -> list:
    try:
        arr = json.loads(MEMORIES.read_text(encoding="utf-8"))
        if isinstance(arr, list):
            arr.sort(key=lambda m: m.get("ts_utc", ""), reverse=True)
            return arr
    except Exception:
        pass
    return []


def allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@app.route("/")
def home():
    return render_template("index.html", memory_count=len(load_memories()))


@app.route("/memories")
def memories():
    return render_template("memories.html", memories=load_memories())


@app.route("/add", methods=["GET", "POST"])
def add_memory():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:120]
        relation = (request.form.get("relation") or "").strip()[:120]
        title = (request.form.get("title") or "").strip()[:200]
        story = (request.form.get("story") or "").strip()[:8000]
        when_text = (request.form.get("when_text") or "").strip()[:120]
        if not (name and story):
            return render_template("add.html",
                                   error="Please share at least your name and a memory.",
                                   form=request.form)

        photo_paths = []
        for f in request.files.getlist("photos"):
            if not f or not f.filename:
                continue
            if not allowed(f.filename):
                continue
            ext = f.filename.rsplit(".", 1)[1].lower()
            stem = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower())[:24] or "guest"
            uniq = uuid.uuid4().hex[:10]
            fname = f"{int(time.time())}_{stem}_{uniq}.{ext}"
            f.save(str(PHOTOS / secure_filename(fname)))
            photo_paths.append(fname)

        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "submitter_name": name,
            "submitter_relation": relation,
            "title": title,
            "story": story,
            "when_text": when_text,
            "photos": photo_paths,
        }
        atomic_append_memory(entry)
        return redirect(url_for("memory_added", mid=entry["id"]))
    return render_template("add.html", form={}, error=None)


@app.route("/added/<mid>")
def memory_added(mid):
    mems = load_memories()
    m = next((x for x in mems if x.get("id") == mid), None)
    if not m:
        abort(404)
    return render_template("added.html", memory=m)


@app.route("/research")
def research():
    return render_template("research.html")


@app.route("/photos/<path:filename>")
def photo(filename):
    return send_from_directory(str(PHOTOS), filename)


@app.route("/healthz")
def healthz():
    return {"ok": True, "memories": len(load_memories())}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8087"))
    print(f"Memorial site running at http://127.0.0.1:{port}/")
    print(f"  Health:  http://127.0.0.1:{port}/healthz")
    print(f"  LAN:     http://<this-machine-ip>:{port}/  (if firewall allows)")
    app.run(host="0.0.0.0", port=port, debug=False)
