"""
Compares a real model with the hard-coded mock on the invoice wording.
Needs your own key. Do not paste the key into any file.

    OPENROUTER_API_KEY=your_key OPENROUTER_MODEL=model_id python try_llm.py

Windows PowerShell:
    $env:OPENROUTER_API_KEY="your_key"; $env:OPENROUTER_MODEL="model_id"; python try_llm.py

Keep it small. Free models have rate limits, so there is a pause between calls.
"""
import os
import time

import audit

# What a person would say the right answer is. "REVIEW" means the wording is too vague to
# map, so the right behaviour is a confidence below the floor (a person looks at it).
TRUTH = {
    "Software Engineer":   "ENG-L2",
    "SW Engineer":         "ENG-L2",
    "Project Manager":     "PM",
    "Sr. Cloud Architect": "ENG-L4",
    "Cloud Architect":     "ENG-L4",
    "Tech Support Fee":    None,        # not a contract item
    "Consultant (misc)":   "REVIEW",
}


def judge(item, conf, truth):
    if truth == "REVIEW":
        return "ok" if conf < audit.CONFIDENCE_FLOOR else "CONFIDENT WRONG"
    if item == truth and conf >= audit.CONFIDENCE_FLOOR:
        return "ok"
    if conf < audit.CONFIDENCE_FLOOR:
        return "sent to a person"       # safe, but costs reviewer time
    return "CONFIDENT WRONG"            # the dangerous kind: it hides or invents an overcharge


def main():
    if not (os.environ.get("OPENROUTER_API_KEY") and os.environ.get("OPENROUTER_MODEL")):
        raise SystemExit("Set OPENROUTER_API_KEY and OPENROUTER_MODEL first (see the top of this file).")
    model = os.environ["OPENROUTER_MODEL"]
    print(f"model: {model}\n")
    tally = {}
    for text, truth in TRUTH.items():
        item, conf = audit.map_line_llm(text)
        verdict = judge(item, conf, truth)
        tally[verdict] = tally.get(verdict, 0) + 1
        print(f"{text:<22} truth={str(truth):<8} model={str(item):<8} conf={conf}  {verdict}")
        time.sleep(3)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in tally.items()))
    print("Note: confidence 0 with no item can also mean the call failed. Check your key and model id.")


if __name__ == "__main__":
    main()
