#!/usr/bin/env python3
"""Generate synthetic EMS call scripts (.call DSL) for TRAIN/DEV from the shared dictionary.
  python3 data/synth/gen_calls.py --n 80 --split train --seed 1
  python3 data/synth/gen_calls.py --n 10 --split dev --seed 2
Phrasings, scenarios and numbers are randomised; none of the hand-written test lines are used, and
data/synth/leakage_check.py verifies there is no n-gram overlap with the test scripts."""
import argparse, json, pathlib, random

ROOT = pathlib.Path(__file__).resolve().parents[2]
F = json.loads((ROOT / "shared/formulary.json").read_text())
DRUG = {d["name"]: d for d in F["drugs"]}
UNIT_WORD = {"mg": ["milligrams", "mg", "migs", ""], "mcg": ["micrograms", "mics", "mcg"], "g": ["grams", "gram"], "mL": ["mLs", "cc's", "mils"],
             "L": ["liter", "liters"], "L/min": ["liters", "L"], "units": ["units"], "mEq": ["milliequivalents", "mEq"], "puffs": ["puffs"]}
ROUTE_WORD = {"IV": ["IV", "IV push", "through the line", "intravenous"], "IO": ["IO", "through the IO"], "IM": ["IM", "in the thigh", "intramuscular", "in the deltoid"],
              "IN": ["intranasal", "IN", "in the nose", "atomized"], "PO": ["PO", "by mouth", "chewed", "orally"], "SL": ["SL", "sublingual", "under the tongue"],
              "neb": ["by neb", "nebulized", "in the neb", "via nebulizer"], "SQ": ["sub Q", "subcutaneous"], "NRB": ["non-rebreather", "NRB"], "NC": ["nasal cannula"],
              "ET": ["down the tube"], "PR": ["rectal"], "inhaled": ["inhaled"]}
UNIT_DEFAULT = {"oxygen": "L/min"}

SCEN = {
    "chest_pain": dict(disp=["chest pain", "cardiac problem", "chest discomfort"], meds=[("aspirin", "324", "mg", "PO"), ("nitroglycerin", "0.4", "mg", "SL"), ("fentanyl", "50", "mcg", "IV"), ("ondansetron", "4", "mg", "IV")],
                       procs=["12-lead ECG", "IV access", "cardiac monitor"], complaint=["pressure in my chest", "my chest is squeezing", "it's burning in my chest and my jaw"], traps=["MI", "heart attack"]),
    "svt": dict(disp=["rapid heart rate", "palpitations"], meds=[("adenosine", "6", "mg", "IV"), ("adenosine", "12", "mg", "IV"), ("normal saline", "10", "mL", "IV")],
                procs=["12-lead ECG", "IV access", "vagal maneuver"], complaint=["my heart won't slow down", "it feels like it's fluttering"], traps=["SVT"]),
    "brady": dict(disp=["weakness", "dizziness"], meds=[("atropine", "1", "mg", "IV"), ("normal saline", "500", "mL", "IV")], procs=["transcutaneous pacing", "IV access", "12-lead ECG"],
                  complaint=["I feel like I'm going to pass out", "I'm so weak"], traps=["heart block"]),
    "arrest": dict(disp=["cardiac arrest", "unconscious not breathing"], meds=[("epinephrine", "1", "mg", "IO"), ("amiodarone", "300", "mg", "IO"), ("amiodarone", "150", "mg", "IV"), ("sodium bicarbonate", "50", "mEq", "IV")],
                   procs=["CPR", "defibrillation", "IO access", "supraglottic airway", "BVM ventilation"], complaint=[], traps=["cardiac arrest"]),
    "copd": dict(disp=["difficulty breathing", "shortness of breath"], meds=[("albuterol/ipratropium", "3", "mL", "neb"), ("methylprednisolone", "125", "mg", "IV"), ("magnesium sulfate", "2", "g", "IV"), ("oxygen", "4", "L/min", "NC")],
                 procs=["CPAP", "nebulizer"], complaint=["I can't get my air", "my breathing's bad today"], traps=["COPD exacerbation"]),
    "chf": dict(disp=["difficulty breathing"], meds=[("nitroglycerin", "0.4", "mg", "SL"), ("nitroglycerin", "0.8", "mg", "SL"), ("furosemide", "40", "mg", "IV")], procs=["CPAP", "12-lead ECG"],
                complaint=["I woke up and couldn't breathe", "I've been sleeping in the recliner"], traps=["CHF", "pulmonary edema"]),
    "hypoglycemia": dict(disp=["diabetic problem", "unresponsive"], meds=[("dextrose", "25", "g", "IV"), ("glucagon", "1", "mg", "IM"), ("oral glucose", "15", "g", "PO"), ("dextrose", "250", "mL", "IV")],
                         procs=["glucose check", "IV access"], complaint=["I feel shaky", "I took my insulin and skipped breakfast"], traps=["hypoglycemia"]),
    "opioid": dict(disp=["overdose", "person down", "unknown problem"], meds=[("naloxone", "2", "mg", "IN"), ("naloxone", "0.4", "mg", "IV"), ("naloxone", "4", "mg", "IN"), ("oxygen", "15", "L/min", "BVM")],
                   procs=["BVM ventilation", "OPA", "suction"], complaint=["I'm good, man", "I only had one"], traps=["overdose"]),
    "seizure": dict(disp=["seizure", "convulsions"], meds=[("midazolam", "5", "mg", "IM"), ("midazolam", "2.5", "mg", "IN"), ("lorazepam", "2", "mg", "IV"), ("diazepam", "10", "mg", "PR")],
                    procs=["NPA", "suction", "glucose check"], complaint=["I'm tired, my tongue hurts"], traps=["epilepsy"]),
    "trauma": dict(disp=["fall", "assault", "MVC rollover", "pedestrian struck"], meds=[("fentanyl", "100", "mcg", "IV"), ("ketamine", "0.3", "mg/kg", "IV"), ("tranexamic acid", "1", "g", "IV"), ("morphine", "4", "mg", "IV"), ("normal saline", "250", "mL", "IV")],
                   procs=["spinal motion restriction", "splinting", "tourniquet", "pelvic binder", "wound packing", "bandaging"], complaint=["my hip hurts so bad", "I can't feel my fingers", "my arm, don't touch my arm"], traps=["fracture", "head injury"]),
    "allergy": dict(disp=["allergic reaction", "bee sting"], meds=[("epinephrine", "0.3", "mg", "IM"), ("diphenhydramine", "25", "mg", "IV"), ("methylprednisolone", "125", "mg", "IV"), ("albuterol", "2.5", "mg", "neb"), ("epinephrine", "10", "mcg", "IV")],
                    procs=["IV access", "nebulizer"], complaint=["my lips are swelling", "I'm itchy all over"], traps=["anaphylaxis"]),
    "nausea": dict(disp=["sick person", "abdominal pain"], meds=[("ondansetron", "4", "mg", "IV"), ("ondansetron", "4", "mg", "ODT"), ("normal saline", "1000", "mL", "IV"), ("ketorolac", "15", "mg", "IV")],
                   procs=["IV access"], complaint=["I've been throwing up all night", "my stomach is killing me"], traps=["appendicitis", "kidney stone"]),
    "agitation": dict(disp=["psychiatric emergency", "combative person"], meds=[("ketamine", "4", "mg/kg", "IM"), ("midazolam", "5", "mg", "IM"), ("haloperidol", "5", "mg", "IM"), ("droperidol", "5", "mg", "IM"), ("olanzapine", "10", "mg", "IM")],
                      procs=["restraint", "glucose check"], complaint=["get away from me", "I didn't do anything"], traps=["excited delirium", "psychosis"]),
    "sepsis": dict(disp=["sick person", "fever"], meds=[("normal saline", "1000", "mL", "IV"), ("lactated Ringer's", "500", "mL", "IV"), ("acetaminophen", "1000", "mg", "PO")],
                   procs=["IV access", "12-lead ECG"], complaint=["I'm freezing", "I've had a fever for three days"], traps=["sepsis", "pneumonia"]),
    "syncope": dict(disp=["fainting", "unconscious person"], meds=[("normal saline", "500", "mL", "IV"), ("oxygen", "2", "L/min", "NC")], procs=["12-lead ECG", "glucose check", "cardiac monitor"],
                    complaint=["I just blacked out", "everything went grey"], traps=["vasovagal"]),
    "stroke": dict(disp=["stroke", "weakness one side"], meds=[("oxygen", "2", "L/min", "NC")], procs=["stroke scale", "glucose check", "IV access"],
                   complaint=["my hand won't work", "words aren't coming out right"], traps=["CVA", "TIA"]),
    "ob": dict(disp=["childbirth", "pregnancy problem"], meds=[("oxytocin", "10", "units", "IM"), ("tranexamic acid", "1", "g", "IV")], procs=["childbirth", "IV access"],
               complaint=["the contractions are two minutes apart", "my water broke"], traps=["postpartum hemorrhage"]),
    "burn": dict(disp=["burns", "structure fire"], meds=[("fentanyl", "1", "mcg/kg", "IN"), ("lactated Ringer's", "1000", "mL", "IV"), ("hydroxocobalamin", "5", "g", "IV")],
                 procs=["bandaging", "cooling"], complaint=["my arms are on fire", "I breathed in smoke"], traps=["smoke inhalation"]),
}
VNAMES = {"bp": ["BP", "blood pressure", "pressure", ""], "hr": ["heart rate", "pulse", "rate", "HR"], "rr": ["resps", "respirations", "resp rate", "breathing"],
          "spo2": ["sat", "sats", "SpO2", "pulse ox"], "bgl": ["sugar", "BGL", "blood sugar", "glucose"], "gcs": ["GCS"], "etco2": ["end tidal", "ETCO2", "capno"], "pain": ["pain"]}
FILLER_M = ["How long has this been going on?", "Any medical history I should know about?", "Do you take any medications?", "Okay, we're going to take care of you.",
            "Can you tell me what day it is?", "Stay with me, keep your eyes open.", "Any allergies?", "On a scale of zero to ten, how bad is it?", "Grab the stair chair.",
            "Let's move on three. One, two, three.", "Watch the step.", "Get the cot.", "I'm going to put some stickers on your chest.", "Small poke.",
            "Did you pass out at all?", "When did you last eat?", "Who's your doctor?", "Can you squeeze my fingers?", "Are you having any trouble breathing?", "Hang tight, partner."]
FILLER_P = ["I don't know, it just started.", "Yeah, I take a bunch of pills, my daughter knows.", "No allergies.", "Am I going to be okay?", "It's about an eight.",
            "I had something like this last year.", "Please don't cut my shirt.", "Can somebody call my wife?", "I feel sick.", "It's getting worse."]
HOSP = ["Mercy", "General", "Saint Joseph's", "Riverside", "University", "Memorial", "County", "Valley", "Northside", "the trauma center", "Good Sam", "Saint Vincent's"]
UNITS = ["Medic", "Rescue", "Ambulance", "Squad"]


def vit(name, rng, sick):
    if name == "bp":
        s = rng.randint(80, 120) if sick and rng.random() < .5 else rng.randint(110, 200); return f"{s}/{max(40, s - rng.randint(30, 80))}"
    return str({"hr": rng.randint(40, 160), "rr": rng.randint(8, 36), "spo2": rng.randint(82, 100), "bgl": rng.randint(28, 450), "gcs": rng.randint(8, 15),
                "etco2": rng.randint(18, 55), "pain": rng.randint(2, 10)}[name])


def say_vital(name, val, rng):
    w = rng.choice(VNAMES[name])
    if name == "bp":
        a, b = val.split("/"); body = f"{a} over {b}"
    elif name == "spo2":
        body = rng.choice([f"{val}", f"{val} percent", f"{val} on room air"])
    elif name == "pain":
        return f"pain is {val} out of 10", f"{val} out of 10"
    else:
        body = val
    conn = rng.choice([" ", " is ", "'s ", " at "]) if w else ""
    if name == "bp" and not w:
        return body, body
    phrase = f"{w}{conn}{body}"
    return phrase, phrase


def say_med(drug, dose, unit, route, rng):
    d = DRUG[drug]
    names = [drug] + d["brands"][:2] + d["aliases"][:2]
    names = [n for n in names if len(n) > 2 and "1:" not in n]
    nm = rng.choice(names)
    uw = rng.choice(UNIT_WORD.get(unit, [unit])) if unit not in ("mg/kg", "mcg/kg") else unit.replace("mg/kg", "milligrams per kilo").replace("mcg/kg", "mics per kilo")
    rw = rng.choice(ROUTE_WORD.get(route, [route])) if route else ""
    keep_unit = bool(uw) and rng.random() < .75
    keep_route = bool(rw) and rng.random() < .8
    pat = rng.randrange(6)
    u = f" {uw}" if keep_unit else ""; r = f" {rw}" if keep_route else ""
    if pat == 0: s = f"{nm} {dose}{u}{r}"
    elif pat == 1: s = f"Giving {dose}{u} of {nm}{r}"
    elif pat == 2: s = f"{dose}{u} {nm}{r}, it's in"
    elif pat == 3: s = f"Pushing {nm}, {dose}{u}{r}"
    elif pat == 4: s = f"I gave {nm} {dose}{u}{r}"
    else: s = f"Drawing up {dose}{u} of {nm}{r}"
    unit_out = (unit if keep_unit else "")
    if drug == "oxygen" and keep_unit: unit_out = "L/min"
    return s.replace("  ", " "), dict(drug=drug, dose=dose, unit=unit_out, route=(route if keep_route else ""))


def gen_call(i, split, rng):
    key = rng.choice(list(SCEN)); sc = SCEN[key]
    unit = f"{rng.choice(UNITS)} {rng.randint(1, 60)}"
    age = rng.randint(18, 92); sex = rng.choice(["male", "female"])
    hh, mm, ss = rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)
    L = [f"@call {split[0]}{i:03d} {key} start={hh:02d}:{mm:02d}:{ss:02d}",
         f'@patient age={age} sex={sex} weight_kg={rng.randint(45, 140)} complaint="{rng.choice(sc["disp"])}" allergies=unknown home_meds=unknown history=unknown',
         f"@traps {'; '.join(sc['traps'])}"]
    d = rng.choice(sc["disp"])
    L.append(f'RD: {unit}, {rng.choice(["respond to", "you have a", "priority two,", "priority one,"])} {d}, {age} year old {sex}.  >> dispatch:{d} "{d}"')
    L.append(f"GAP {rng.choice([2, 3, 4])}")
    on = rng.choice(["on scene", "arriving on scene", "we're on scene"])
    L.append(f'M{rng.choice([1, 2])}: {unit} {on}.  >> time:eTimes.06 "{on}"')
    sick = rng.random() < .6
    lines = []
    nt = 0
    # body: interleave fillers, vitals sets, meds, procs, taps
    meds = rng.sample(sc["meds"], k=min(len(sc["meds"]), rng.randint(2, 4)))
    procs = rng.sample(sc["procs"], k=min(len(sc["procs"]), rng.randint(1, 2)))
    blocks = [("vit",)] * rng.randint(2, 3) + [("med", m) for m in meds] + [("proc", p) for p in procs] + [("fill",)] * rng.randint(3, 6)
    rng.shuffle(blocks)
    blocks.insert(0, ("fill",))
    if sc["complaint"]:
        blocks.insert(1, ("pt", rng.choice(sc["complaint"])))
    transported = False
    for bi, b in enumerate(blocks):
        tap = None
        if b[0] in ("vit", "med") and rng.random() < .55:
            tap = rng.choice(["knock", "snap", "button"])
            lines.append(f"TAP {tap} +label"); nt += 1
        if b[0] == "fill":
            lines.append(f"M{rng.choice([1, 1, 2])}: {rng.choice(FILLER_M)}")
            if rng.random() < .6: lines.append(f"{rng.choice(['PT', 'PT', 'BY'])}: {rng.choice(FILLER_P)}")
        elif b[0] == "pt":
            lines.append(f"PT: {b[1][0].upper() + b[1][1:]}.")
        elif b[0] == "vit":
            names = rng.sample(["bp", "hr", "rr", "spo2", "bgl", "gcs", "etco2", "pain"], k=rng.randint(1, 3))
            parts, evs = [], []
            for n in names:
                v = vit(n, rng, sick); ph, q = say_vital(n, v, rng)
                parts.append(ph); evs.append(f'vital:{n}={v} "{q}"')
            lead = rng.choice(["", "Vitals, ", "Repeat, ", "Okay, ", "Second set, "])
            lines.append(f"M{rng.choice([1, 2])}: {lead}{', '.join(parts)}.  >> " + "; ".join(evs))
        elif b[0] == "med":
            drug, dose, unit_, route = b[1]
            if drug not in DRUG: continue
            s, f = say_med(drug, dose, unit_, route, rng)
            q = s.split(", it's in")[0]
            lines.append(f'M{rng.choice([1, 1, 2])}: {s}.  >> med:{f["drug"]},{f["dose"]},{f["unit"]},{f["route"]} "{q}"')
        elif b[0] == "proc":
            al = [a for a in F["procedures"].get(b[1], [b[1]]) if len(a) > 3] or [b[1]]
            a = rng.choice(al)
            lines.append(f'M{rng.choice([1, 2])}: {rng.choice(["Get", "Let's do", "We need", "Doing", "Got"])} {a}.  >> proc:{b[1]} "{a}"')
        lines.append(f"GAP {rng.choice([1, 2, 3, 4, 6, 8])}")
        if not transported and bi > len(blocks) * .6:
            h = rng.choice(HOSP); tr = rng.choice(["Transporting", "We're transporting", "Leaving scene"])
            lines.append(f'M1: {tr} to {h}.  >> time:eTimes.09 "{tr}"'); lines.append("GAP 3"); transported = True
    # unlabelled taps (1-2) with quiet margins
    for _ in range(rng.randint(1, 2)):
        pos = rng.randrange(len(lines) + 1)
        while pos < len(lines) and lines[pos - 1 if pos else 0].startswith("TAP"):
            pos += 1
        lines[pos:pos] = ["GAP 11", f"TAP {rng.choice(['knock', 'snap', 'button'])} -", "GAP 11"]; nt += 1
    L += lines
    h = rng.choice(HOSP)
    arr = rng.choice(["Arrived at", "We're at", "Arriving at"])
    L.append(f'M1: {arr} {h}.  >> time:eTimes.11 "{arr}"')
    if rng.random() < .6:
        L.append(f"GAP {rng.randint(4, 15)}")
        if rng.random() < .5: L.append("TAP button +label")
        toc = rng.choice(["Transfer of care", "Handing off", "Giving report"])
        L.append(f'M1: {toc} {rng.choice(["to the nurse", "to bed four", "now", "complete"])}.  >> time:eTimes.12 "{toc}"')
    if rng.random() < .3: L.append("KNOCK3")
    # fix: a labelled tap must be followed by an event line; drop dangling ones
    out = []
    for j, l in enumerate(L):
        if l.startswith("TAP") and l.endswith("+label"):
            nxt = next((x for x in L[j + 1:] if not x.startswith("GAP")), "")
            if ">>" not in nxt: continue
        out.append(l)
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=80); ap.add_argument("--split", default="train"); ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    od = ROOT / "data/scripts" / f"{a.split}_synth"; od.mkdir(parents=True, exist_ok=True)
    import sys; sys.path.insert(0, str(ROOT / "data/synth")); import calldsl
    sys.path.insert(0, str(ROOT / "eval")); import textnorm as tn
    test_lines = [tn.normalize(it["text"]) for p in sorted((ROOT / "data/scripts/test").glob("*.call"))
                  for it in calldsl.parse(p.read_text())["items"] if it["kind"] == "speech"]
    test_tok = [set(l.split()) for l in test_lines]; test_set = set(test_lines)

    def leaks(c):
        for it in c["items"]:
            if it["kind"] != "speech": continue
            n = tn.normalize(it["text"]); s_ = set(n.split())
            if n in test_set: return True
            if len(s_) >= 5 and max(len(s_ & t) / len(s_ | t) for t in test_tok) >= 0.6: return True
        return False
    k = 0; rejected = 0
    while k < a.n:
        txt = gen_call(k + 1, a.split, rng)
        try:
            c = calldsl.parse(txt)
        except Exception as e:
            continue
        if leaks(c):
            rejected += 1; continue
        (od / f"{a.split[0]}{k+1:03d}.call").write_text(txt); k += 1
    print("wrote", k, "to", od, "rejected for test overlap:", rejected)
