"""
Invoice vs contract checker. Synthetic data only: no real vendor, contract or client.

Real in this file: the date-aware rate lookup, the Decimal maths, the volume discount,
the duplicate / currency / confidence gates, the grounding check, and the citations that
come with every finding.

Not real: the "AI" step. map_line() reads a hard-coded table. There is an optional
OpenRouter version further down that I have not run (no API key), so treat it as untested.

    python audit.py          report for the sample invoice
    python test_audit.py     all the examples, including the ones that fail
"""
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal as D, ROUND_HALF_UP

CONFIDENCE_FLOOR = D("0.80")   # below this a line goes to a person
CONTRACT_CCY = "USD"


def load_env(path=".env"):
    """Reads KEY=value lines from a .env file so no extra package is needed.
    Variables already set in the shell win over the file."""
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


load_env()


def cents(x):
    return D(x).quantize(D("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Cite:
    doc: str
    page: int
    section: str

    def __str__(self):
        return f"{self.doc} p.{self.page} {self.section}"


# ---- contract terms (made up). In real use these come from the approved terms table. ----

RATES = {
    "ENG-L2": [   # Software Engineer
        dict(rate=D("100"), start=date(2026, 1, 1), end=date(2026, 6, 30),
             cite=Cite("MSA_2026.pdf", 4, "Exhibit B.1")),
        dict(rate=D("110"), start=date(2026, 7, 1), end=date(2026, 12, 31),
             cite=Cite("MSA_Amendment_1.pdf", 2, "Section 2.1")),
    ],
    "ENG-L4": [   # Level 4 Engineer
        dict(rate=D("185"), start=date(2026, 1, 1), end=date(2026, 12, 31),
             cite=Cite("MSA_2026.pdf", 4, "Exhibit B.2")),
    ],
    "PM": [       # Project Manager
        dict(rate=D("150"), start=date(2026, 1, 1), end=date(2026, 12, 31),
             cite=Cite("MSA_2026.pdf", 4, "Exhibit B.3")),
    ],
}

# hours above the limit on one line get a discount. (The real clause would say per month.)
TIER = dict(after_hours=D("160"), discount=D("0.10"), cite=Cite("MSA_2026.pdf", 5, "Exhibit B.5"))

# Stand-in for the OCR text inside each cited box.
SOURCE_TEXT = {
    Cite("MSA_2026.pdf", 4, "Exhibit B.1"): "B.1 Software Engineer (Level 2): USD 100 per hour.",
    Cite("MSA_Amendment_1.pdf", 2, "Section 2.1"): "2.1 From 1 July 2026 the Software Engineer rate is USD 110 per hour.",
    Cite("MSA_2026.pdf", 4, "Exhibit B.2"): "B.2 Level 4 Engineer: USD 185 per hour.",
    Cite("MSA_2026.pdf", 4, "Exhibit B.3"): "B.3 Project Manager: USD 150 per hour.",
    Cite("MSA_2026.pdf", 5, "Exhibit B.5"): "B.5 Hours above 160 are billed at a 10% discount.",
}


def check_grounding(rates=RATES, tier=TIER):
    """A term only counts if its number appears in the text it cites. Returns a list of problems."""
    problems = []
    for item, versions in rates.items():
        for v in versions:
            found = re.findall(r"USD\s*(\d+(?:\.\d+)?)", SOURCE_TEXT.get(v["cite"], ""))
            if str(v["rate"]) not in found:
                problems.append(f"{item}: rate {v['rate']} is not in {v['cite']}")
    text = SOURCE_TEXT.get(tier["cite"], "")
    if str(tier["after_hours"]) not in re.findall(r"above\s*(\d+)", text):
        problems.append(f"tier threshold not in {tier['cite']}")
    if str(int(tier["discount"] * 100)) not in re.findall(r"(\d+)%", text):
        problems.append(f"tier discount not in {tier['cite']}")
    return problems


# ---- invoice ----

@dataclass(frozen=True)
class Line:
    id: str
    text: str
    hours: D
    rate: D
    amount: D
    day: date
    ccy: str
    page: int


def L(id, text, hours, rate, amount, day, ccy="USD", page=1):
    return Line(id, text, D(hours), D(rate), D(amount), day, ccy, page)


SAMPLE_LINES = [
    L("L01", "Software Engineer",   80, 100,  8000, date(2026, 5, 10), page=1),
    L("L02", "Software Engineer",   80, 120,  9600, date(2026, 5, 11), page=1),   # rate too high
    L("L03", "Sr. Cloud Architect", 40, 185,  7400, date(2026, 5, 12), page=1),   # different wording, correct
    L("L04", "Tech Support Fee",     1, 500,   500, date(2026, 5, 13), page=2),   # not in the contract
    L("L05", "Project Manager",    100, 150, 15500, date(2026, 5, 14), page=2),   # should be 15000
    L("L06", "Software Engineer",  200, 100, 20000, date(2026, 5, 15), page=2),   # discount missed
    L("L07", "Consultant (misc)",   30, 150,  4500, date(2026, 5, 16), page=3),   # too vague
    L("L08", "Project Manager",     10, 140,  1400, date(2026, 5, 17), page=3),   # below contract rate
    L("L09", "Software Engineer",   80, 100,  8000, date(2026, 5, 10), page=3),   # same as L01
    L("L10", "Software Engineer",   10, 110,  1100, date(2026, 5, 20), page=3),   # amended rate, too early
    L("L11", "Software Engineer",   10, 110,  1100, date(2026, 8, 10), page=4),   # amended rate, fine
    L("L12", "Project Manager",     20, 150,  3000, date(2026, 5, 21), "EUR", 4), # wrong currency
    L("L13", "Software Engineer",  200, 100, 19600, date(2026, 5, 22), page=4),   # discount applied, fine
]
SAMPLE_STATED_USD_TOTAL = D("96700")


# ---- the AI step (mocked) ----

# wording on the invoice -> (contract item, confidence)
MOCK_MAP = {
    "software engineer":   ("ENG-L2", "0.99"),
    "sw engineer":         ("ENG-L2", "0.97"),
    "project manager":     ("PM",     "0.99"),
    "sr. cloud architect": ("ENG-L4", "0.91"),
    "tech support fee":    (None,     "0.95"),   # sure it is NOT a contract item
    "consultant (misc)":   ("ENG-L2", "0.55"),   # a guess
    "cloud architect":     ("ENG-L2", "0.90"),   # wrong on purpose, see failure F1 in test_audit.py
}
CATALOG = {"ENG-L2": "Software Engineer", "ENG-L4": "Level 4 Engineer", "PM": "Project Manager"}


_llm_cache = {}   # same wording is only sent to the model once


def map_line(text):
    """Returns (item or None, confidence). Anything unknown gets confidence 0.
    USE_LLM=1 (shell or .env) switches from the hard-coded table to the model."""
    if os.environ.get("USE_LLM") == "1":
        key = text.strip().lower()
        if key not in _llm_cache:
            _llm_cache[key] = map_line_llm(text)
        return _llm_cache[key]
    item, conf = MOCK_MAP.get(text.strip().lower(), (None, "0"))
    return item, D(conf)


def map_line_llm(text):
    """
    Needs OPENROUTER_API_KEY and OPENROUTER_MODEL (set them in .env, see .env.example).
    The model only picks an item id from CATALOG and gives a confidence. It never sees
    an amount. A failure or a reply outside the catalog counts as confidence 0, which
    sends the line to a person.
    """
    key, model = os.environ.get("OPENROUTER_API_KEY"), os.environ.get("OPENROUTER_MODEL")
    if not key or not model:
        return None, D("0")
    prompt = ("Match this invoice line to one item id in the catalog, or null if none fits. "
              f"Catalog: {json.dumps(CATALOG)}. Line: {text!r}. "
              'Answer with JSON only: {"item": "<id or null>", "confidence": <0 to 1>}')
    body = json.dumps({"model": model, "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            reply = json.loads(resp.read())["choices"][0]["message"]["content"]
        data = json.loads(reply[reply.index("{"): reply.rindex("}") + 1])
        item = data.get("item")
        if item is not None and item not in CATALOG:
            return None, D("0")
        return item, min(max(D(str(data.get("confidence", 0))), D("0")), D("1"))
    except Exception:
        return None, D("0")


# ---- the checks (no AI in here) ----

@dataclass
class Finding:
    line_id: str
    text: str
    flag: str          # OK, RATE_TOO_HIGH, MATH_ERROR, DISCOUNT_MISSED, DUPLICATE,
                       # NOT_IN_CONTRACT, BELOW_CONTRACT, NEEDS_REVIEW
    loss: D
    why: str
    invoice_ref: str
    contract_ref: str = ""


def rate_on(item, day):
    for v in RATES[item]:
        if v["start"] <= day <= v["end"]:
            return v
    return None


def amount_with_tier(hours, rate):
    normal = min(hours, TIER["after_hours"])
    extra = max(hours - TIER["after_hours"], D("0"))
    return cents(normal * rate + extra * rate * (1 - TIER["discount"]))


def check_line(line, seen):
    ref = f"INV-SYN-0001.pdf p.{line.page} line {line.id}"

    def finding(flag, loss="0", why="", contract=""):
        return Finding(line.id, line.text, flag, cents(loss), why, ref, str(contract))

    if line.ccy != CONTRACT_CCY:
        return finding("NEEDS_REVIEW", why=f"billed in {line.ccy}, contract is in {CONTRACT_CCY}")

    item, conf = map_line(line.text)
    if conf < CONFIDENCE_FLOOR:
        return finding("NEEDS_REVIEW", why=f"mapping confidence {conf} is below {CONFIDENCE_FLOOR}")

    key = (item, line.hours, line.rate, line.day)
    if key in seen:
        return finding("DUPLICATE", line.amount, "same item, hours, rate and date already billed")
    seen.add(key)

    if item is None:
        return finding("NOT_IN_CONTRACT", line.amount, "no matching charge in the rate card")

    term = rate_on(item, line.day)
    if term is None:
        return finding("NEEDS_REVIEW", why=f"no contract rate in force on {line.day}")
    cite = term["cite"]

    should_be = amount_with_tier(line.hours, term["rate"])           # at the contract rate
    at_billed_rate = amount_with_tier(line.hours, line.rate)         # at the rate they used

    if line.rate > term["rate"]:
        return finding("RATE_TOO_HIGH", line.amount - should_be,
                       f"billed {line.rate}/h, contract says {term['rate']}/h", cite)
    if cents(line.amount) == at_billed_rate:
        if line.rate < term["rate"]:
            return finding("BELOW_CONTRACT", why=f"billed {line.rate}/h, contract says {term['rate']}/h", contract=cite)
        return finding("OK", contract=cite)
    if cents(line.amount) == cents(line.hours * line.rate):
        return finding("DISCOUNT_MISSED", line.amount - at_billed_rate,
                       f"should be {at_billed_rate} after the volume discount ({TIER['cite']})", cite)
    return finding("MATH_ERROR", line.amount - at_billed_rate,
                   f"{line.hours} h at {line.rate} should be {at_billed_rate}, invoice says {line.amount}", cite)


def check_invoice(lines):
    seen = set()
    return [check_line(line, seen) for line in lines]


def total_matches(lines, stated_usd_total):
    """Adds up the USD lines only, since the stated total is in USD."""
    return cents(sum(l.amount for l in lines if l.ccy == CONTRACT_CCY)) == cents(stated_usd_total)


def print_report(lines, findings, stated_usd_total):
    print("INVOICE INV-SYN-0001 (synthetic)\n")
    for f in findings:
        if f.flag == "OK":
            continue
        print(f"{f.line_id}  {f.flag:<16} loss ${f.loss:>8}  {f.text}")
        print(f"      why:      {f.why}")
        print(f"      invoice:  {f.invoice_ref}")
        if f.contract_ref:
            print(f"      contract: {f.contract_ref}")
    confirmed = sum(f.loss for f in findings)
    waiting = [f.line_id for f in findings if f.flag == "NEEDS_REVIEW"]
    print(f"\nTotal matches the lines: {total_matches(lines, stated_usd_total)}")
    print(f"Confirmed loss: ${confirmed}")
    print(f"Waiting for a person: {', '.join(waiting) or 'nothing'}")


if __name__ == "__main__":
    problems = check_grounding()
    if problems:
        raise SystemExit("contract terms failed the grounding check: " + "; ".join(problems))
    results = check_invoice(SAMPLE_LINES)
    print_report(SAMPLE_LINES, results, SAMPLE_STATED_USD_TOTAL)
