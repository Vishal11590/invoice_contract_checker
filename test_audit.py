"""
Examples for audit.py. Run:  python test_audit.py

Part 1: 13 invoice lines where I know the right answer in advance (I wrote them next to the code,
so this is not an independent test set).
Part 2: three cases where the checker gets it WRONG. The tests pin down the wrong behaviour on
purpose, so the failure stays visible, and so someone fixing one will see a test change.
"""
import os
import unittest
from datetime import date
from decimal import Decimal as D

os.environ["USE_LLM"] = "0"   # the tests expect the mock, whatever is in .env
import audit
from audit import L

# line id -> (flag, loss)
EXPECTED = {
    "L01": ("OK", "0"),
    "L02": ("RATE_TOO_HIGH", "1600"),
    "L03": ("OK", "0"),
    "L04": ("NOT_IN_CONTRACT", "500"),
    "L05": ("MATH_ERROR", "500"),
    "L06": ("DISCOUNT_MISSED", "400"),
    "L07": ("NEEDS_REVIEW", "0"),
    "L08": ("BELOW_CONTRACT", "0"),
    "L09": ("DUPLICATE", "8000"),
    "L10": ("RATE_TOO_HIGH", "100"),
    "L11": ("OK", "0"),
    "L12": ("NEEDS_REVIEW", "0"),
    "L13": ("OK", "0"),
}


class SampleInvoice(unittest.TestCase):
    def setUp(self):
        self.findings = {f.line_id: f for f in audit.check_invoice(audit.SAMPLE_LINES)}

    def test_every_line(self):
        for line_id, (flag, loss) in EXPECTED.items():
            with self.subTest(line=line_id):
                got = self.findings[line_id]
                self.assertEqual((got.flag, got.loss), (flag, D(loss)))

    def test_confirmed_loss(self):
        self.assertEqual(sum(f.loss for f in self.findings.values()), D("11100"))

    def test_total_ignores_the_euro_line(self):
        self.assertTrue(audit.total_matches(audit.SAMPLE_LINES, audit.SAMPLE_STATED_USD_TOTAL))

    def test_money_flags_carry_both_citations(self):
        for f in self.findings.values():
            if f.flag in ("RATE_TOO_HIGH", "MATH_ERROR", "DISCOUNT_MISSED"):
                self.assertTrue(f.contract_ref and f.invoice_ref, f.line_id)


class Grounding(unittest.TestCase):
    def test_real_terms_pass(self):
        self.assertEqual(audit.check_grounding(), [])

    def test_invented_rate_is_rejected(self):
        bad = {"ENG-L2": [{**audit.RATES["ENG-L2"][0], "rate": D("105")}]}
        self.assertTrue(audit.check_grounding(rates=bad))

    def test_wrong_discount_is_rejected(self):
        self.assertTrue(audit.check_grounding(tier={**audit.TIER, "discount": D("0.15")}))


class KnownFailures(unittest.TestCase):
    """Each of these is a real mistake the checker makes today."""

    def test_f1_confident_wrong_mapping_gives_a_false_alarm(self):
        # "Cloud Architect" is really a Level 4 Engineer at 185, and the vendor billed 185 correctly.
        # The mock mapper is confidently wrong (ENG-L2), so the line is flagged as an overcharge.
        # Truth: OK, loss 0.
        line = L("F1", "Cloud Architect", 10, 185, 1850, date(2026, 5, 12))
        got = audit.check_invoice([line])[0]
        self.assertEqual((got.flag, got.loss), ("RATE_TOO_HIGH", D("850")))

    def test_f2_discount_that_should_span_several_lines_is_missed(self):
        # 100 h + 100 h of Project Manager in the same month. If the clause is "over 160 h a month",
        # 40 h should have been discounted, so $600 was overbilled. The checker looks at one line at a time.
        # Truth: DISCOUNT_MISSED, loss 600.
        lines = [L("F2a", "Project Manager", 100, 150, 15000, date(2026, 5, 3)),
                 L("F2b", "Project Manager", 100, 150, 15000, date(2026, 5, 17))]
        got = audit.check_invoice(lines)
        self.assertEqual([f.flag for f in got], ["OK", "OK"])

    def test_f3_duplicate_with_the_date_off_by_one_is_missed(self):
        # The duplicate rule needs an exact match on item, hours, rate and date.
        # Truth: second line is a duplicate, loss 8000.
        lines = [L("F3a", "Software Engineer", 80, 100, 8000, date(2026, 5, 10)),
                 L("F3b", "Software Engineer", 80, 100, 8000, date(2026, 5, 11))]
        got = audit.check_invoice(lines)
        self.assertEqual([f.flag for f in got], ["OK", "OK"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
