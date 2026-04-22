"""
Mock local do endpoint corporativo Copilot para extração de PDF.

Uso:
  python scripts/mock_copilot_extractor.py

Depois configure:
  COPILOT_EXTRACT_WEBHOOK_URL=http://127.0.0.1:8765/extract
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


HOST = "127.0.0.1"
PORT = 8765


class CopilotMockHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/extract":
            self._send_json({"error": "route not found"}, status=404)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="ignore")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, status=400)
            return

        if not payload.get("pdf_base64"):
            self._send_json({"error": "missing pdf_base64"}, status=400)
            return

        # Resposta no formato aceito pelo extractor.py
        self._send_json(
            {
                "result": {
                    "postes": [
                        {
                            "id": "P1",
                            "tipo": "C12/600",
                            "estruturas": ["N4F", "1S3"],
                            "trafo": None,
                            "estais": 0,
                            "chave": None,
                        }
                    ],
                    "cabos": [
                        {
                            "tipo": "MT",
                            "descricao": "CABO AL NU 35MM2 15KV",
                            "metros": 120,
                        }
                    ],
                    "ordem": "MOCK-0001",
                }
            }
        )


def main():
    server = HTTPServer((HOST, PORT), CopilotMockHandler)
    print(f"[MOCK-COPILOT] Endpoint ativo em http://{HOST}:{PORT}/extract")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[MOCK-COPILOT] Encerrado.")


if __name__ == "__main__":
    main()
