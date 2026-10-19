#!/usr/bin/env python3
"""Read-only production activity projection with the live music queue attached."""
from __future__ import annotations

import argparse
import json
import sys

from management_db import ManagementDBError
from production_ledger import ProductionLedger, ProductionLedgerError
from production_runtime import read_runtime_queue


def activity(data_dir, params, *, runtime_reader=read_runtime_queue):
    return ProductionLedger(data_dir).activity(params, runtime_queue=runtime_reader(data_dir))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("activity",))
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--stdin", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(16 * 1024 * 1024 + 1).decode("utf-8")
        if len(raw.encode("utf-8")) > 16 * 1024 * 1024:
            raise ProductionLedgerError("stdin JSON이 안전 한도를 초과했습니다")
        params = json.loads(raw)
        if not isinstance(params, dict):
            raise ProductionLedgerError("JSON 객체가 필요합니다")
        print(json.dumps({"ok": True, "result": activity(args.data_dir, params)}, ensure_ascii=False, allow_nan=False))
        return 0
    except (ProductionLedgerError, ManagementDBError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": {"code": "production_activity_error", "message": str(error)}}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
