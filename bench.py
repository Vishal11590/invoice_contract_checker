"""Rough speed check for the rules part. Mock mapper, in memory, one core. Run: python bench.py"""
import os
import time
from datetime import date, timedelta
from decimal import Decimal as D

os.environ["USE_LLM"] = "0"   # never send 200,000 lines to a paid or rate-limited model
import audit
from audit import L

N = 200_000
names = ["Software Engineer", "Project Manager", "Sr. Cloud Architect"]
rate_of = {"Software Engineer": D("100"), "Project Manager": D("150"), "Sr. Cloud Architect": D("185")}

# every line is correct and unique, so none of them takes an early exit
lines = []
for i in range(N):
    name = names[i % 3]
    hours = D(1 + i)
    lines.append(L(f"X{i}", name, hours, rate_of[name], audit.amount_with_tier(hours, rate_of[name]),
                   date(2026, 5, 1) + timedelta(days=i % 60)))

start = time.perf_counter()
results = audit.check_invoice(lines)
secs = time.perf_counter() - start

flags = {}
for r in results:
    flags[r.flag] = flags.get(r.flag, 0) + 1
print(flags)
print(f"{N} lines in {secs:.2f}s, about {N / secs:,.0f} lines/s, {secs / N * 1e6:.1f} microseconds a line")
