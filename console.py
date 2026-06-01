"""
Fabrikam Data Engineering — Interactive Console
Run: python console.py
"""

import cmd
import json
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

BANNER = """
============================================================
  FABRIKAM RETAIL — Data Engineering Console
  Medallion Lakehouse  |  Bronze / Silver / Gold
============================================================
Type 'help' for available commands.
"""

HELP_TEXT = """
Commands:
  status          Show pipeline status and record counts
  ingest          Run batch ingestion for all 6 sources
  quality         Run quality checks on Bronze data
  hook            Test Gold PreToolUse hook (clean + PII write)
  scorecard       Run WS-7 entity matcher eval (needs API key)
  swarm           Run WS-9 parallel swamp health dashboard (needs API key)
  catalog <name>  Show catalogue entry (customer/transaction/product/store/loyalty)
  bronze          List Bronze landing files
  gold            Show Gold schema contract
  full            Run full pipeline end-to-end
  quit / exit     Exit console
"""


def _count_bronze():
    counts = {}
    path = "bronze/data"
    if not os.path.exists(path):
        return counts
    for f in os.listdir(path):
        if not f.endswith(".jsonl") or "error" in f or "dead" in f:
            continue
        source = f.split("_")[0]
        n = sum(1 for line in open(os.path.join(path, f)) if line.strip())
        counts[source] = counts.get(source, 0) + n
    return counts


def _print_status():
    counts = _count_bronze()
    print("\n  Bronze zone records:")
    if counts:
        for src, n in sorted(counts.items()):
            bar = "#" * min(n * 2, 20)
            print(f"    {src:<12} {bar} {n}")
    else:
        print("    (empty — run 'ingest' first)")

    baseline = "quality/scorecard/baseline.json"
    if os.path.exists(baseline):
        b = json.loads(open(baseline).read())
        print(f"\n  Scorecard baseline: FCR={b.get('false_confidence_rate', 'N/A')}")
    else:
        print("\n  Scorecard baseline: not yet run")

    swamp = "quality/swamp_health.json"
    if os.path.exists(swamp):
        s = json.loads(open(swamp).read())
        print(f"  Swamp health:       {s.get('overall_health_score', '?')}/100  ({s.get('elapsed_seconds', '?')}s)")
    else:
        print("  Swamp health:       not yet run")
    print()


def _run_ingest():
    from bronze.ingestion.batch_ingestion import ingest_batch_file, validate_pos_record, validate_crm_record
    sources = [
        ("data/fixtures/pos.csv",       "pos",       validate_pos_record),
        ("data/fixtures/ecommerce.csv", "ecommerce", validate_crm_record),
        ("data/fixtures/crm.csv",       "crm",       validate_crm_record),
        ("data/fixtures/loyalty.csv",   "loyalty",   validate_crm_record),
        ("data/fixtures/merger_a.csv",  "merger_a",  validate_pos_record),
        ("data/fixtures/merger_c.csv",  "merger_c",  validate_crm_record),
    ]
    total = 0
    for path, name, validator in sources:
        if not os.path.exists(path):
            print(f"  {name:<12} -> fixture missing, run 'ingest' after fixtures exist")
            continue
        r = ingest_batch_file(path, name, validator, "bronze/data")
        total += r["records_landed"]
        errs = f"  {r['errors']} errors" if r["errors"] else ""
        print(f"  {name:<12} -> {r['records_landed']} records  run:{r['run_id'][:8]}...{errs}")
    print(f"\n  Total landed: {total} records in Bronze")


def _run_quality():
    from quality.checks import (make_null_rate_check, make_schema_drift_check,
                                 make_volume_anomaly_check, make_pii_check, run_checks, Policy)
    records = []
    path = "bronze/data"
    for f in os.listdir(path):
        if f.startswith("pos") and f.endswith(".jsonl") and "error" not in f:
            for line in open(os.path.join(path, f)):
                if line.strip(): records.append(json.loads(line))
    if not records:
        print("  No POS Bronze records found. Run 'ingest' first.")
        return
    rules = [
        make_null_rate_check("customer_id", 0.0, Policy.BREAK),
        make_schema_drift_check({"customer_id","first_name","last_name","email","phone","address","order_date","total_amount"}),
        make_volume_anomaly_check([4]*7),
        make_pii_check(),
    ]
    results = run_checks(records, rules)
    for r in results:
        status = "PASS" if r.passed else r.policy.value + " FAIL"
        print(f"  [{status:<12}] {r.rule_id}")
        if r.violations:
            print(f"               -> {r.violations[0]}")


def _run_hook():
    from quality.hook import check_gold_write
    good = {"customer_id":"uuid-001","first_name":"Katherine","last_name":"Moore",
            "email_masked":"km**@gmail.com","loyalty_segment":"Gold","record_confidence":0.97,
            "source_systems":"pos,crm","created_at_utc":"2024-03-15T00:00:00Z","updated_at_utc":"2024-03-15T00:00:00Z"}
    bad = dict(good); bad["email_masked"] = "katherine.moore@gmail.com"

    a1, _ = check_gold_write("customer", [good])
    a2, _ = check_gold_write("customer", [bad])
    print(f"  Clean record  -> {'ALLOWED' if a1 else 'BLOCKED'}")
    print(f"  PII record    -> {'BLOCKED (correct)' if not a2 else 'ALLOWED (WRONG)'}")


class FabrikamConsole(cmd.Cmd):
    prompt = "\nfabrikam> "
    intro = BANNER

    def do_status(self, _):
        "Show pipeline status and record counts"
        _print_status()

    def do_ingest(self, _):
        "Run batch ingestion for all 6 source fixtures"
        print("\n[WS-3] Ingesting sources into Bronze...")
        import scripts.generate_test_data as gd
        gd.write_pos_fixture(); gd.write_ecommerce_fixture(); gd.write_crm_fixture()
        gd.write_loyalty_fixture(); gd.write_merger_a_fixture(); gd.write_merger_c_fixture()
        _run_ingest()

    def do_quality(self, _):
        "Run quality checks on POS Bronze data"
        print("\n[WS-5] Quality checks on Bronze POS data...")
        _run_quality()

    def do_hook(self, _):
        "Test Gold PreToolUse hook"
        print("\n[WS-5] Gold PreToolUse hook test...")
        _run_hook()

    def do_scorecard(self, _):
        "Run WS-7 entity matcher eval harness"
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("  Set ANTHROPIC_API_KEY first.")
            return
        print("\n[WS-7] Running entity matcher scorecard (16 pairs)...")
        import logging; logging.disable(logging.CRITICAL)
        from quality.scorecard.eval_harness import run_evaluation, check_regression
        metrics = run_evaluation()
        print(metrics.report())
        check_regression(metrics)

    def do_swarm(self, _):
        "Run WS-9 parallel swamp health dashboard"
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("  Set ANTHROPIC_API_KEY first.")
            return
        print("\n[WS-9] Launching 7 parallel source profilers...")
        import logging; logging.disable(logging.WARNING)
        from swarm.coordinator import run_swarm, print_dashboard
        dashboard = run_swarm()
        print_dashboard(dashboard)

    def do_catalog(self, name):
        "Show a catalogue entry: catalog <customer|transaction|product|store|loyalty>"
        names = {"customer","transaction","product","store","loyalty","loyalty_account"}
        name = name.strip().lower().replace("loyalty account","loyalty_account")
        if not name:
            print("  Usage: catalog <customer|transaction|product|store|loyalty>")
            return
        fname = "loyalty_account" if name == "loyalty" else name
        path = f"catalog/{fname}.md"
        if not os.path.exists(path):
            print(f"  Not found: {path}")
            return
        print()
        for line in open(path):
            print(" ", line, end="")
        print()

    def do_bronze(self, _):
        "List Bronze landing files"
        path = "bronze/data"
        if not os.path.exists(path) or not os.listdir(path):
            print("  Bronze zone is empty. Run 'ingest' first.")
            return
        print(f"\n  Bronze files in {path}/:")
        for f in sorted(os.listdir(path)):
            size = os.path.getsize(os.path.join(path, f))
            rows = sum(1 for line in open(os.path.join(path, f)) if line.strip())
            tag = " [dead-letter]" if "error" in f or "dead" in f else ""
            print(f"    {f:<55} {rows:>3} rows  {size:>6} bytes{tag}")
        print()

    def do_gold(self, _):
        "Show Gold schema contract for customer table"
        path = "gold/schema_contracts/customer.json"
        contract = json.loads(open(path).read())
        print(f"\n  Table:   {contract['table']}  (v{contract['version']})")
        print(f"  Zone:    {contract['zone']}  |  PII policy: {contract['pii_policy']}")
        print(f"  Columns:")
        for col, spec in contract["columns"].items():
            nullable = "nullable" if spec.get("nullable", True) else "NOT NULL"
            desc = spec.get("description", "")
            print(f"    {col:<22} {spec['type']:<8} {nullable:<10} {desc}")
        print()

    def do_full(self, _):
        "Run full pipeline end-to-end"
        print("\n[FULL PIPELINE]")
        self.do_ingest("")
        self.do_quality("")
        self.do_hook("")
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.do_scorecard("")
            self.do_swarm("")
        else:
            print("\n  Skipping scorecard + swarm (no ANTHROPIC_API_KEY set)")
        _print_status()

    def do_help(self, _):
        print(HELP_TEXT)

    def do_quit(self, _):
        "Exit the console"
        print("Goodbye.")
        return True

    def do_exit(self, _):
        "Exit the console"
        return self.do_quit(_)

    def default(self, line):
        print(f"  Unknown command: '{line}'. Type 'help' for available commands.")


if __name__ == "__main__":
    try:
        FabrikamConsole().cmdloop()
    except KeyboardInterrupt:
        print("\nGoodbye.")
