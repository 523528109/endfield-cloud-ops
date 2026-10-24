#!/usr/bin/env python3
"""Minimal CDP helper for the headless cloud page."""
import argparse, base64, json, time, urllib.request
import websocket

BASE = "http://127.0.0.1:9334"

def pages():
    with urllib.request.urlopen(BASE + "/json", timeout=5) as r:
        return json.load(r)

def pick():
    ps = [p for p in pages() if p.get("type") == "page"]
    for p in ps:
        if "endfield" in (p.get("url") or ""):
            return p
    return ps[0] if ps else None

class CDP:
    def __init__(self):
        p = pick()
        if not p:
            raise SystemExit("no page target")
        self.ws = websocket.create_connection(p["webSocketDebuggerUrl"], timeout=15)
        self.i = 0
    def call(self, method, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg
    def close(self):
        self.ws.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["screenshot", "navigate", "eval", "click", "url", "targets"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--wait", type=float, default=0)
    a = ap.parse_args()
    if a.cmd == "targets":
        for p in pages():
            print(p.get("type"), "|", p.get("url"))
        return
    if a.cmd == "url":
        p = pick(); print(p.get("url") if p else "none"); return
    c = CDP()
    if a.cmd == "screenshot":
        r = c.call("Page.captureScreenshot", format="png")
        data = base64.b64decode(r["result"]["data"])
        open(a.arg, "wb").write(data)
        print("saved", a.arg, len(data))
    elif a.cmd == "navigate":
        r = c.call("Page.navigate", url=a.arg)
        print(json.dumps(r.get("result", {}), ensure_ascii=False))
        if a.wait:
            time.sleep(a.wait)
    elif a.cmd == "click":
        x, y = [float(v) for v in a.arg.split(",")]
        c.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        c.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        c.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)
        time.sleep(0.8)
        print("clicked", x, y)
    elif a.cmd == "eval":
        r = c.call("Runtime.evaluate", expression=a.arg, returnByValue=True, awaitPromise=True)
        print(json.dumps(r.get("result", {}), ensure_ascii=False)[:2000])
    c.close()

if __name__ == "__main__":
    main()
