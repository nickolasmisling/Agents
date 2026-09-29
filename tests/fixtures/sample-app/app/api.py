"""Minimal JSON API over the batch records."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import DB_PATH, batches, db, signatures, utils


def _summary(row):
    return {
        "id": row["id"],
        "batchNo": row["batch_no"],
        "product": row["product"],
        "site": row["site"],
        "status": row["status"],
        "plannedQty": row["planned_qty"],
    }


class BatchHandler(BaseHTTPRequestHandler):
    db_path = DB_PATH

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _route(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        return parts, query

    def do_GET(self):
        parts, query = self._route()
        with db.session(self.db_path) as conn:
            if parts == ["batches"]:
                rows = batches.list_batches(
                    conn, product=query.get("product"), site=query.get("site"), status=query.get("status")
                )
                page = batches.paginate(rows, int(query.get("page", 1)), int(query.get("page_size", 25)))
                self._send({"items": [_summary(r) for r in page], "total": len(rows)})
            elif len(parts) == 2 and parts[0] == "batches":
                batch = batches.get_batch(conn, int(parts[1]))
                if batch is None:
                    self._send({"error": "batch not found"})
                else:
                    self._send(batch)
            elif len(parts) == 3 and parts[0] == "batches" and parts[2] == "release":
                batch_id = int(parts[1])
                changed = batches.release_batch(conn, batch_id, int(query.get("user_id", 0)))
                self._send({"batchId": batch_id, "status": "released", "changed": changed})
            elif len(parts) == 3 and parts[0] == "batches" and parts[2] == "signatures":
                self._send({"items": signatures.signatures_for_batch(conn, int(parts[1]))})
            else:
                self._send({"error": f"no route for {self.path}"})

    def do_POST(self):
        parts, _ = self._route()
        data = self._read_json()
        if parts == ["batches"]:
            try:
                batch_no = utils.clean_batch_no(data["batchNo"])
            except (KeyError, ValueError) as exc:
                self._send({"error": f"invalid batchNo: {exc}"})
                return
            with db.session(self.db_path) as conn:
                batch_id = batches.create_batch(
                    conn, batch_no, data.get("product"), data.get("site"), utils.to_float(data.get("plannedQty"))
                )
            self._send({"id": batch_id, "batchNo": batch_no}, status=201)
        elif len(parts) == 3 and parts[0] == "batches" and parts[2] == "signatures":
            with db.session(self.db_path) as conn:
                sig_id = signatures.sign_batch(
                    conn, int(parts[1]), data["user_id"], data["signed_at"], data.get("meaning")
                )
            self._send({"signature_id": sig_id}, status=201)
        else:
            self._send({"error": f"no route for {self.path}"})


def serve(host="127.0.0.1", port=8080, db_path=DB_PATH):
    BatchHandler.db_path = db_path
    with db.session(db_path) as conn:
        db.init_db(conn)
    server = ThreadingHTTPServer((host, port), BatchHandler)
    print(f"batchtrack API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    serve()
