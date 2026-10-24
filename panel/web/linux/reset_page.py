#!/usr/bin/env python3
import argparse, subprocess, sys, os
ap = argparse.ArgumentParser()
ap.add_argument("--port", default="9334")
ap.add_argument("--url", required=True)
ap.add_argument("--wait", type=float, default=12)
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "cdp_tool.py"), "navigate", a.url, "--wait", str(a.wait)], check=False)
