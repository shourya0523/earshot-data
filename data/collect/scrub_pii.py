"""Privacy step: replace patient names, street addresses and dates of birth in transcripts with tokens.
scrub(text) -> (clean_text, list_of_token_types_found). Conservative regexes + a first-name list; anything replaced
is reported in the manifest 'pii' column. Audio that contains PII is excluded from training (see RISKS.md)."""
import re

FIRST = set("""james john robert michael william david richard joseph thomas charles mary patricia jennifer linda elizabeth barbara susan jessica sarah karen
nancy lisa betty margaret sandra ashley kimberly emily donna michelle dorothy carol amanda melissa deborah stephanie rebecca sharon laura cynthia
kathleen amy shirley angela helen anna brenda pamela nicole emma samantha katherine christine debra rachel catherine carolyn janet ruth maria heather
diane virginia julie joyce victoria olivia kelly christina lauren joan evelyn judith megan cheryl andrea hannah martha jacqueline frances gloria ann
teresa kathryn sara janice jean alice madison doris abigail julia judy grace denise amber marilyn beverly danielle theresa sophia marie diana brittany
natalie isabella charlotte rose alexis kayla daniel matthew anthony mark donald steven paul andrew joshua kenneth kevin brian george timothy ronald
edward jason jeffrey ryan jacob gary nicholas eric jonathan stephen larry justin scott brandon benjamin samuel gregory alexander frank patrick raymond
jack dennis jerry tyler aaron jose adam nathan henry douglas zachary peter kyle ethan walter noah jeremy christian keith roger terry gerald harold
sean austin carl arthur lawrence dylan jesse jordan bryan billy joe bruce gabriel logan albert willie alan juan wayne elijah randy roy vincent ralph
eugene russell bobby mason philip louis""".split())
STREET = r"(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|court|ct|way|place|pl|circle|terrace|highway|hwy)"
MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def scrub(text):
    found = []
    t = text
    t2 = re.sub(rf"\b\d{{1,6}}\s+(?:[A-Z][a-z]+\s+){{1,3}}{STREET}\b\.?", "[ADDRESS]", t, flags=re.I)
    if t2 != t: found.append("address"); t = t2
    t2 = re.sub(rf"\b(?:dob|date of birth|born(?: on)?)\b[:\s]*(?:\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})", "[DOB]", t, flags=re.I)
    if t2 != t: found.append("dob"); t = t2
    def name_sub(m):
        return "[NAME]"
    t2 = re.sub(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+\b", "[NAME]", t)
    t2 = re.sub(r"\b(?:my name is|name's|this is|patient is)\s+([A-Z][a-z]+)(\s+[A-Z][a-z]+)?", lambda m: m.group(0).split()[0] + " " + " ".join(m.group(0).split()[1:-1 if m.group(2) else None][:-1]) + " [NAME]" if False else re.sub(r"[A-Z][a-z]+(\s+[A-Z][a-z]+)?$", "[NAME]", m.group(0)), t2)
    words = t2.split()
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^A-Za-z]", "", w)
        if core.lower() in FIRST and core[:1].isupper() and i > 0:
            out.append(w.replace(core, "[NAME]"))
        else:
            out.append(w)
    t2 = " ".join(out)
    if t2 != t: found.append("name"); t = t2
    return t, ",".join(found)
