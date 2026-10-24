#!/usr/bin/env python3
import argparse, os, subprocess, sys
ap = argparse.ArgumentParser()
ap.add_argument("--port", default="9334")
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "cdp_tool.py"), "navigate", "about:blank", "--wait", "2"], check=False)
