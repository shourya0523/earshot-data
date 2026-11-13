"""EMS-aware text normalisation for WER scoring (applied identically to reference and hypothesis).
lowercase; strip punctuation; number words -> digits; '158/94' -> '158 over 94'; unit words -> canonical;
'I.V.' -> 'iv'; '12-lead' -> '12 lead'; '%' -> 'percent'; 'A&O×4' -> 'a and o times 4'."""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ONES = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
UNIT_CANON = {"milligrams": "mg", "milligram": "mg", "mgs": "mg", "micrograms": "mcg", "microgram": "mcg", "mics": "mcg", "mikes": "mcg", "ug": "mcg",
              "grams": "g", "gram": "g", "gm": "g", "milliliters": "ml", "milliliter": "ml", "mls": "ml", "cc": "ml", "ccs": "ml", "mil": "ml", "mils": "ml",
              "liters": "l", "liter": "l", "litres": "l", "litre": "l", "units": "units", "percent": "percent", "joules": "j"}
SPELLED = {"i v": "iv", "i m": "im", "i o": "io", "i n": "in", "s l": "sl", "p o": "po", "b p": "bp", "g c s": "gcs", "b g l": "bgl", "n p a": "npa",
           "t x a": "txa", "a c": "ac", "e t": "et", "o 2": "o2", "o two": "o2", "spo 2": "spo2", "sp o2": "spo2", "s p o 2": "spo2", "a v f": "avf",
           "c t": "ct", "m v c": "mvc", "n r b": "nrb", "d 10": "d10", "d 50": "d50", "d ten": "d10", "d fifty": "d50", "duo neb": "duoneb",
           "solu medrol": "solumedrol", "ekg": "ecg", "e k g": "ecg", "be fast": "befast", "a and o": "a and o", "co 2": "co2", "end tidal": "etco2"}


def words_to_digits(tokens):
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in ONES or t in TENS or (t == "hundred" and out and out[-1].isdigit()):
            val, used, cur = 0, 0, 0
            j = i
            while j < len(tokens):
                w = tokens[j]
                if w in ONES and (cur % 10 == 0 or cur == 0) and not (cur and ONES[w] >= 10):
                    if cur and cur < 10: break
                    cur += ONES[w]
                elif w in TENS and cur % 100 == 0 and cur < 1000:
                    if cur and cur % 100: break
                    cur += TENS[w]
                elif w == "hundred" and 0 < cur < 10:
                    cur *= 100
                elif w == "and" and cur >= 100 and j + 1 < len(tokens) and (tokens[j + 1] in ONES or tokens[j + 1] in TENS):
                    pass
                else:
                    break
                j += 1
            if j == i:
                out.append(t); i += 1; continue
            out.append(str(cur)); i = j
        else:
            out.append(t); i += 1
    return out


def normalize(s):
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", " ", s)   # whisper non-speech tags: [beep] (siren) *clap*
    s = s.lower().replace("×", " times ").replace("&", " and ")
    s = re.sub(r"(\d)\s*/\s*(\d)", r"\1 over \2", s)
    s = re.sub(r"(\d)%", r"\1 percent", s).replace("%", " percent")
    s = re.sub(r"\b([a-z])\.(?=[a-z]\.)", r"\1", s)          # I.V. -> iv.
    s = re.sub(r"(?<=\b[a-z])\.(?=\s|$)", "", s)
    s = re.sub(r"(\d),(\d{3})", r"\1\2", s)
    s = re.sub(r"(\d)\.(\d)", r"\1point\2", s)             # keep decimals as one token
    s = re.sub(r"[-–—/]", " ", s)
    s = re.sub(r"[^a-z0-9' ]", " ", s)
    s = s.replace("'s", " s").replace("'", "")
    s = re.sub(r"(\d)([a-z]+)\b", lambda m: m.group(1) + " " + m.group(2) if m.group(2) not in ("point",) else m.group(0), s)
    s = re.sub(r"\b(d)\s+(10|50|25)\b", r"\1\2", s)
    toks = s.split()
    toks = words_to_digits(toks)
    s = " ".join(toks).replace("point", ".")
    for k, v in sorted(SPELLED.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(rf"\b{k}\b", v, s)
    toks = [UNIT_CANON.get(t, t) for t in s.split()]
    toks = ["ok" if t in ("okay", "k") else t for t in toks]
    toks = [t for t in toks if t not in ("uh", "um", "uhm", "er", "ah", "hmm", "mm")]
    return " ".join(toks)


_DICT = None


def dictionary():
    global _DICT
    if _DICT is None:
        _DICT = json.loads((ROOT / "data" / "dictionary" / "ems_seed.json").read_text())
    return _DICT


def drug_terms():
    """normalised single tokens that are drug names (generic, brand, alias)"""
    d = dictionary(); terms = set()
    for x in d["drugs"]:
        for n in [x["name"], x["generic"], *x["brands"], *x["aliases"]]:
            for t in normalize(n).split():
                if (len(t) > 2 and t not in {"of", "amp", "the", "push", "dose", "tab", "neb", "and", "spray", "paste", "chewable", "baby",
                                                                "nasal", "fluid", "bolus", "acid", "sulfate", "chloride", "sodium", "gel", "tube", "oral",
                                                                "blow", "by", "breathing", "treatment", "activated", "rebreather", "non", "cannula", "special", "vitamin", "insta", "ringer", "ringers", "lactated", "normal", "saline", "racemic", "auvi", "pen", "nrb", "inch"}
                        and not re.match(r"^[0-9.]+$", t)):
                    terms.add(t)
    terms |= {"d10", "d50", "d25", "duoneb", "solumedrol", "txa"}
    return terms


def jargon_terms():
    d = dictionary(); terms = set()
    for j in d["jargon"] + d["status_terms"]:
        n = normalize(j)
        if n and len(n) > 1: terms.add(n)
    for k, al in d["procedures"].items():
        for a in al:
            n = normalize(a)
            if n and len(n) > 1: terms.add(n)
    return terms


if __name__ == "__main__":
    for t in ["BP 158/94, sat 95%, D10 100 mLs I.V.", "Twelve lead shows elevation", "sixty-two year old, one hundred twenty four", "A&O×4, Solu-Medrol 125 IV", "0.4 mg SL, 2.5 milligrams"]:
        print(t, "->", normalize(t))
