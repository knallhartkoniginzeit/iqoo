import argparse
import sys
from datetime import datetime, timedelta
from tabulate import tabulate
from app.ledger import ledger


def format_cost(cost_usd: float) -> str:
    if cost_usd < 0.01:
        return f"${cost_usd:.6f}"
    elif cost_usd < 1.00:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.2f}"


def cmd_spend_by_model(since_hours: int = 24, key_hash: str = None):
    print(f"\n=== Spend by Model (last {since_hours} hours) ===\n")
    rows = ledger.get_spend_by_model(api_key_hash=key_hash, hours=since_hours)
    if not rows:
        print("No spend data found for the specified period.")
        return
    table = []
    for row in rows:
        model = row.get("model", "unknown")
        count = row.get("request_count", 0)
        input_tokens = row.get("total_input_tokens", 0)
        output_tokens = row.get("total_output_tokens", 0)
        total_cost = row.get("total_cost_usd") or 0.0
        table.append([model, count, f"{input_tokens:,}", f"{output_tokens or 0:,}", format_cost(total_cost)])
    headers = ["Model", "Requests", "Input Tokens", "Output Tokens", "Total Cost"]
    print(tabulate(table, headers=headers, tablefmt="grid"))
    total = sum(row.get("total_cost_usd") or 0.0 for row in rows)
    print(f"\n{'='*60}")
    print(f"Total: {format_cost(total)}")


def cmd_key_spend(key_hash: str, since_hours: int = 24):
    print(f"\n=== Spend History for {key_hash[:8]}... (last {since_hours} hours) ===\n")
    entries = ledger.get_entries_since(api_key_hash=key_hash, hours=since_hours)
    if not entries:
        print("No entries found for the specified period.")
        return
    table = []
    total_cost = 0.0
    for entry in entries:
        created = entry.get("created_at", "unknown")
        model = entry.get("model", "unknown")
        input_tokens = entry.get("input_tokens", 0)
        estimated_cost = entry.get("estimated_cost_usd", 0.0)
        actual_cost = entry.get("actual_cost_usd")
        status = entry.get("status", "unknown")
        table.append([created, model, input_tokens, format_cost(estimated_cost), format_cost(actual_cost) if actual_cost else "N/A", status])
        total_cost += estimated_cost
    headers = ["Time", "Model", "Input Tokens", "Est. Cost", "Actual Cost", "Status"]
    print(tabulate(table, headers=headers, tablefmt="grid"))
    print(f"\n{'='*60}")
    print(f"Total Estimated: {format_cost(total_cost)}")


def cmd_summary(since_hours: int = 24):
    print(f"\n=== Token Cost Guard Summary (last {since_hours} hours) ===\n")
    rows = ledger.get_spend_by_model(hours=since_hours)
    total_requests = sum(row.get("request_count", 0) for row in rows)
    total_input = sum(row.get("total_input_tokens", 0) for row in rows)
    total_output = sum(row.get("total_output_tokens") or 0 for row in rows)
    total_cost = sum(row.get("total_cost_usd") or 0.0 for row in rows)
    print(f"Total Requests: {total_requests}")
    print(f"Total Input Tokens: {total_input:,}")
    print(f"Total Output Tokens: {total_output:,}")
    print(f"Total Cost: {format_cost(total_cost)}")
    print("\nBreakdown by Model:")
    for row in rows:
        model = row.get("model", "unknown")
        count = row.get("request_count", 0)
        cost = row.get("total_cost_usd") or 0.0
        pct = (cost / total_cost * 100) if total_cost > 0 else 0
        print(f"  {model}: {count} requests ({format_cost(cost)}) - {pct:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Token Cost Guard Ledger Report Tool")
    parser.add_argument("--since", type=int, default=24, help="Hours of history to include (default: 24)")
    parser.add_argument("--key", type=str, help="Filter by API key hash (first 8 chars)")
    parser.add_argument("command", nargs="?", default="summary", choices=["summary", "spend", "key"], help="Report type: summary (default), spend, key")
    args = parser.parse_args()
    if args.command == "summary":
        cmd_summary(args.since)
    elif args.command == "spend":
        cmd_spend_by_model(args.since, key_hash=args.key)
    elif args.command == "key":
        if not args.key:
            print("Error: --key required for 'key' command")
            sys.exit(1)
        cmd_key_spend(args.key, args.since)


if __name__ == "__main__":
    main()
