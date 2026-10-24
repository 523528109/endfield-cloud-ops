#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp_tool
c = cdp_tool.CDP()
for t in ("keyDown", "keyUp"):
    c.call("Input.dispatchKeyEvent", type=t, key="Escape", code="Escape",
           windowsVirtualKeyCode=27, nativeVirtualKeyCode=27)
c.close()
print("sent ESC")
