"""Deterministic synthetic target for exercising execution and independent artifact checks."""

import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--variant", choices=["baseline", "candidate"], required=True)
args = parser.parse_args()
request = json.load(sys.stdin)
visible = request["input"]
actual = visible["tool_result"]["status"]
# A controlled stand-in for observable service state. It is independent of the final answer.
Path("state.json").write_text(json.dumps({"operation_status": actual}), encoding="utf-8")
claimed = "completed" if args.variant == "baseline" else actual
print(json.dumps({"output": {"status": claimed, "message": "The operation is " + claimed}}))
