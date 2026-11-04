"""POST {"q": ...} -> SearXNG GET format=json -> results[] bridge.

Claude Desktop's managed "Web search" server posts {"q"} to a custom URL and
expects a results[] array back; SearXNG only answers JSON on GET with
format=json. This bridge speaks the desktop contract and forwards to SearXNG,
so Cowork/Chat web search runs on this PC without any search API key.
"""
import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ.get("SEARX_UPSTREAM", "http://searxng:8080")
MAX_RESULTS = int(os.environ.get("SEARX_MAX_RESULTS", "10"))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path.split("?", 1)[0] != "/search":
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("content-length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid json"}, 400)
            return
        query = str(body.get("q") or "").strip()
        if not query:
            self._json({"error": "missing q"}, 400)
            return
        url = "%s/search?%s" % (
            UPSTREAM,
            urllib.parse.urlencode({"q": query, "format": "json"}),
        )
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.loads(response.read())
        except Exception as exc:  # noqa: BLE001 - report upstream failure as 502
            self._json({"error": "upstream failed: %s" % exc}, 502)
            return
        results = []
        for item in (data.get("results") or [])[:MAX_RESULTS]:
            content = item.get("content") or ""
            results.append(
                {
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    # SearXNG calls the snippet "content"; Brave calls it
                    # "description". Emit both so either reader is satisfied.
                    "content": content,
                    "description": content,
                }
            )
        payload = {"results": results}
        unresponsive = data.get("unresponsive_engines")
        if unresponsive:
            payload["unresponsive_engines"] = unresponsive
        self._json(payload)

    def _json(self, payload, status=200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8090), Handler)
    # Claude Desktop requires an https custom search URL. TLS_CERT/TLS_KEY are
    # set in compose and hold the self-signed localhost pair whose CA the
    # setup installed into the current user's trusted root store.
    cert, key = os.environ.get("TLS_CERT"), os.environ.get("TLS_KEY")
    if cert and key:
        import ssl

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
