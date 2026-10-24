#!/usr/bin/env python3
"""Base Address Activity Summary — x402-paid micro-service on Base mainnet.

Cheaper complement to base-oracle: fast wallet triage (ETH/USDC balance,
nonce, contract flag, code size) for agents screening many addresses.
Price: 0.001 USDC per call.
PayTo: 0x65aa59025C4AcD8CD7ba2051ecb9152abaE4fcC6

Stdlib only. Run: python3 base_address_summary.py [port]
"""
import http.server
import json
import os
import socketserver
import urllib.request
import urllib.error
from http import HTTPStatus

RPC = "https://mainnet.base.org"
PAY_TO = "0x65aa59025C4AcD8CD7ba2051ecb9152abaE4fcC6"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PRICE_UNITS = 1000  # 0.001 USDC (6 decimals)
PORT = int(os.environ.get("PORT", 8810))
USED_FILE = os.path.join(os.path.dirname(__file__), "used_txs.json")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def rpc(method, params):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["result"]


def to_int(hexstr):
    return int(hexstr, 16) if hexstr and hexstr != "0x" else 0


def load_used():
    try:
        with open(USED_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_used(used):
    try:
        with open(USED_FILE, "w") as f:
            json.dump(sorted(used), f)
    except Exception:
        pass


def summary(address):
    address = address.lower()
    bal_wei = to_int(rpc("eth_getBalance", [address, "latest"]))
    nonce = to_int(rpc("eth_getTransactionCount", [address, "latest"]))
    code = rpc("eth_getCode", [address, "latest"])
    data = "0x70a08231" + address[2:].rjust(64, "0")
    usdc_raw = to_int(rpc("eth_call", [{"to": USDC, "data": data}, "latest"]))
    return {
        "address": address,
        "eth_balance": bal_wei / 1e18,
        "usdc_balance": usdc_raw / 1e6,
        "nonce": nonce,
        "is_contract": code not in ("0x", "", None),
        "code_size": (len(code) - 2) // 2 if code else 0,
    }


def verify_payment(tx_hash):
    tx_hash = tx_hash.strip().lower()
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        return False
    if tx_hash in load_used():
        return False
    try:
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
    except Exception:
        return False
    if not receipt or receipt.get("status") != "0x1":
        return False
    for log in receipt.get("logs", []):
        if log.get("address", "").lower() != USDC.lower():
            continue
        topics = log.get("topics", [])
        if len(topics) < 3 or topics[0].lower() != TRANSFER_TOPIC:
            continue
        to_addr = "0x" + topics[2][-40:]
        if to_addr.lower() != PAY_TO.lower():
            continue
        value = to_int(log.get("data", "0x0"))
        if value >= PRICE_UNITS:
            used = load_used()
            used.add(tx_hash)
            save_used(used)
            return True
    return False


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, status, body, extra=None):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ok", "service": "base-address-summary", "price_usdc": 0.001})
            return
        if self.path.startswith("/summary"):
            tx = self.headers.get("X-Payment-Tx") or self.headers.get("Payment-Tx")
            if not tx or not verify_payment(tx):
                self._send(HTTPStatus.PAYMENT_REQUIRED, {
                    "error": "payment_required",
                    "price_usdc": 0.001,
                    "pay_to": PAY_TO,
                    "asset": USDC,
                    "chain": "base-mainnet",
                    "how": "Send 0.001 USDC to pay_to, then retry with header X-Payment-Tx: <tx_hash>",
                })
                return
            addr = None
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if part.startswith("address="):
                        addr = part.split("=", 1)[1]
            if not addr or not addr.startswith("0x") or len(addr) != 42:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "missing_or_invalid_address"})
                return
            try:
                self._send(HTTPStatus.OK, summary(addr))
            except Exception as e:
                self._send(HTTPStatus.BAD_GATEWAY, {"error": str(e)})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/summary":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        tx = self.headers.get("X-Payment-Tx") or self.headers.get("Payment-Tx")
        if not tx or not verify_payment(tx):
            self._send(HTTPStatus.PAYMENT_REQUIRED, {
                "error": "payment_required",
                "price_usdc": 0.001,
                "pay_to": PAY_TO,
                "asset": USDC,
                "chain": "base-mainnet",
            })
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return
        addr = body.get("address")
        if not addr or not addr.startswith("0x") or len(addr) != 42:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "missing_or_invalid_address"})
            return
        try:
            self._send(HTTPStatus.OK, summary(addr))
        except Exception as e:
            self._send(HTTPStatus.BAD_GATEWAY, {"error": str(e)})

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}", flush=True)


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        print(f"base-address-summary listening on :{PORT}", flush=True)
        httpd.serve_forever()
