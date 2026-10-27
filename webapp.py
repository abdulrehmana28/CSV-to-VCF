#!/usr/bin/env python3
"""
Local web interface for the Seerah WhatsApp VCF converter.

Run:
    python3 webapp.py

Then open http://127.0.0.1:8000 (the browser opens automatically).
The server binds to localhost only and never sends data anywhere.
"""

import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import make_vcf

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_OUTPUT_DIR = BASE_DIR / "vcf_output"
REPORT_NAME = "vcf_skipped_rows.csv"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PREVIEW_LIMIT = 200
SKIPPED_PREVIEW_LIMIT = 200


class Handler(BaseHTTPRequestHandler):
    server_version = "SeerahContacts/1.0"
    output_dir = DEFAULT_OUTPUT_DIR

    # ---------- helpers ----------

    def _host_allowed(self):
        host_header = (self.headers.get("Host") or "").strip()
        if host_header.startswith("[") and "]" in host_header:
            host = host_header[1:host_header.index("]")].lower()
        else:
            host = host_header.rsplit(":", 1)[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def _send(self, status, content_type, body, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'",
        )
        if filename:
            ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "")
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
            )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def _send_error_json(self, status, message, columns=None):
        payload = {"ok": False, "error": message}
        if columns:
            payload["columns"] = columns
        self._send_json(status, payload)

    def _read_body(self, length):
        chunks = []
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            print(f"[web] {fmt % args}")

    # ---------- GET ----------

    def do_GET(self):
        if not self._host_allowed():
            self._send(403, "text/plain; charset=utf-8", b"Forbidden")
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._serve_static("index.html")
            return

        if path == "/favicon.ico":
            self._send(204, "image/x-icon", b"")
            return

        if path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
            return

        if path.startswith("/download/"):
            self._serve_download(unquote(path[len("/download/"):]))
            return

        if path == "/api/status":
            self._send_json(200, {"ok": True, "outputs": str(self.output_dir)})
            return

        self._send(404, "text/plain; charset=utf-8", b"Not found")

    def do_HEAD(self):
        self.do_GET()

    def _serve_static(self, relative):
        try:
            candidate = (STATIC_DIR / relative).resolve()
            if STATIC_DIR.resolve() not in candidate.parents:
                raise ValueError
        except (ValueError, OSError):
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return

        if not candidate.is_file():
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return

        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript", "application/json",
        ):
            content_type += "; charset=utf-8"
        self._send(200, content_type, candidate.read_bytes())

    def _serve_download(self, name):
        if Path(name).name != name or "\\" in name:
            self._send(400, "text/plain; charset=utf-8", b"Invalid filename")
            return

        if not name.lower().endswith((".vcf", ".csv")):
            self._send(403, "text/plain; charset=utf-8", b"File type not allowed")
            return

        file_path = self.output_dir / name
        if not file_path.is_file():
            self._send(404, "text/plain; charset=utf-8", b"File not found")
            return

        content_type = (
            "text/vcard; charset=utf-8" if name.lower().endswith(".vcf")
            else "text/csv; charset=utf-8"
        )
        self._send(200, content_type, file_path.read_bytes(), filename=name)

    # ---------- POST ----------

    def do_POST(self):
        if not self._host_allowed():
            self._send(403, "text/plain; charset=utf-8", b"Forbidden")
            return

        parsed = urlparse(self.path)
        if parsed.path != "/api/convert":
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0

        if length <= 0:
            self._send_error_json(400, "No file was received. Please choose a file and try again.")
            return

        if length > MAX_UPLOAD_BYTES:
            self._send_error_json(413, "The file is too large. The limit is 50 MB.")
            return

        data = self._read_body(length)
        if not data:
            self._send_error_json(400, "The uploaded file is empty.")
            return

        params = parse_qs(parsed.query)
        filename = (params.get("filename") or ["upload.csv"])[0]
        code = (params.get("code") or [""])[0].strip()
        style = (params.get("style") or ["brackets"])[0]
        show_code = (params.get("show_code") or ["1"])[0] != "0"

        try:
            result = make_vcf.convert_bytes(
                data,
                filename,
                code_override=code,
                show_code=show_code,
                code_style=style,
            )

            written, report_path = make_vcf.write_outputs(
                result, self.output_dir, self.output_dir / REPORT_NAME
            )
        except make_vcf.InputError as error:
            self._send_error_json(400, str(error), error.columns)
            return
        except Exception as error:  # keep the UI useful if something unexpected happens
            print(f"[web] conversion failed: {error!r}")
            self._send_error_json(500, f"Could not generate the files: {error}")
            return

        batches = []
        for batch in result["batches"]:
            batches.append({
                "code": batch["code"],
                "contacts": batch["contacts"],
                "filename": batch["filename"],
                "download_url": "/download/" + quote(batch["filename"]),
                "preview": batch["preview"][:PREVIEW_LIMIT],
                "preview_limited": len(batch["preview"]) > PREVIEW_LIMIT,
            })

        skipped = result["skipped"]
        self._send_json(200, {
            "ok": True,
            "total_rows": result["total_rows"],
            "total_contacts": result["total_contacts"],
            "skipped_total": len(skipped),
            "batches": batches,
            "skipped": skipped[:SKIPPED_PREVIEW_LIMIT],
            "skipped_limited": len(skipped) > SKIPPED_PREVIEW_LIMIT,
            "report_url": "/download/" + quote(report_path.name),
            "columns": result["columns"],
            "written": [path.name for path in written],
        })


class AppServer(ThreadingHTTPServer):
    daemon_threads = True


def find_server(start_port, max_tries=20):
    for port in range(start_port, start_port + max_tries):
        try:
            return AppServer(("127.0.0.1", port), Handler), port
        except OSError:
            continue
    raise SystemExit(
        f"ERROR: No free port found between {start_port} and {start_port + max_tries - 1}."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local web interface for the VCF converter.")
    parser.add_argument("--port", type=int, default=8000, help="Port to use (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Where generated VCF files are saved")
    args = parser.parse_args(argv)

    if not (STATIC_DIR / "index.html").is_file():
        raise SystemExit(f"ERROR: Web interface files are missing from {STATIC_DIR}")

    Handler.output_dir = Path(args.output_dir).resolve()
    Handler.output_dir.mkdir(parents=True, exist_ok=True)

    server, port = find_server(args.port)
    url = f"http://127.0.0.1:{port}/"

    print()
    print("  Seerah Contacts — local VCF generator")
    print(f"  Open: {url}")
    print(f"  Files save to: {Handler.output_dir}")
    print("  Press Ctrl+C to stop.")
    print()

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
