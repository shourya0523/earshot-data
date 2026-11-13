"""Builds shared/formulary.json (EMS dictionary). Data agent seed; re-run is idempotent.
Sources for each entry: NASEMSO National Model EMS Clinical Guidelines v3 drug list (public),
common US EMS protocols, and ASR variants observed in stock whisper small.en output (eval/BASELINE.md)."""
import json, pathlib
D = lambda name, generic=None, brands=(), aliases=(), asr=(), cls="", routes=(), units=("mg",), doses=(): dict(
    name=name, generic=generic or name, brands=list(brands), aliases=list(aliases), asr_variants=list(asr),
    drug_class=cls, routes=list(routes), units=list(units), typical_doses=list(doses))
drugs = [
 D("aspirin", brands=["Bayer"], aliases=["ASA","baby aspirin","chewable aspirin"], asr=["asprin","a s a"], cls="antiplatelet", routes=["PO"], doses=["324","325","162","81"]),
 D("nitroglycerin", brands=["Nitrostat","Nitrolingual"], aliases=["nitro","NTG","nitro spray","nitro tab","nitro paste"], asr=["nitro glycerin","night row","nitroglycerine"], cls="vasodilator", routes=["SL","topical"], units=["mg","inch"], doses=["0.4"]),
 D("naloxone", brands=["Narcan"], aliases=["narcan","nasal narcan"], asr=["nar can","narkan","naloxon","now loxone"], cls="opioid antagonist", routes=["IN","IV","IM","IO"], doses=["0.4","2","4"]),
 D("dextrose", aliases=["D10","D50","D25","dextrose 10%","dextrose 50%","D10W","amp of D50"], asr=["d 10","d-10","d ten","d 50","d fifty","dextros"], cls="carbohydrate", routes=["IV","IO"], units=["g","mL"], doses=["25","12.5","5","10","100","250"]),
 D("oral glucose", aliases=["glucose gel","insta-glucose","glucose tube"], asr=["oral glucos"], cls="carbohydrate", routes=["PO","buccal"], units=["g"], doses=["15","24"]),
 D("glucagon", brands=["GlucaGen","Baqsimi"], asr=["glucogon","gluca gone"], cls="hormone", routes=["IM","IN"], doses=["1","3"]),
 D("albuterol", brands=["ProAir","Ventolin","Proventil"], aliases=["neb","breathing treatment","albuterol neb"], asr=["albuteral","al butyrol","albuterall","albuterol's"], cls="beta-2 agonist", routes=["neb","MDI","inhaled"], units=["mg","puffs"], doses=["2.5","5"]),
 D("ipratropium", brands=["Atrovent"], aliases=["atrovent"], asr=["atro vent","ipratropeum"], cls="anticholinergic", routes=["neb"], units=["mcg","mg"], doses=["500","0.5"]),
 D("albuterol/ipratropium", brands=["DuoNeb"], aliases=["duoneb","duo neb","duo-neb"], asr=["do neb","duo nab","dual neb"], cls="bronchodilator combination", routes=["neb"], units=["mg"], doses=["3"]),
 D("epinephrine", brands=["EpiPen","Adrenalin","Auvi-Q"], aliases=["epi","epi pen","epi 1 to 1000","epi 1:1000","epi 1:10,000","push dose epi","adrenaline"], asr=["epipen","epi pin","epinephrin","epi nephrine"], cls="sympathomimetic", routes=["IM","IV","IO","neb","ET"], units=["mg","mcg"], doses=["0.3","0.15","0.5","1","10"]),
 D("racemic epinephrine", aliases=["racemic epi"], cls="sympathomimetic", routes=["neb"], units=["mg","mL"], doses=["11.25","0.5"]),
 D("diphenhydramine", brands=["Benadryl"], aliases=["benadryl"], asr=["bena dril","benadril","diphen hydramine"], cls="antihistamine", routes=["IV","IM","PO"], doses=["25","50"]),
 D("famotidine", brands=["Pepcid"], aliases=["pepcid"], cls="H2 blocker", routes=["IV","PO"], doses=["20"]),
 D("methylprednisolone", brands=["Solu-Medrol"], aliases=["solu-medrol","solumedrol"], asr=["solu medrol","sol you medrol","soul medrol","solu-medrol's"], cls="corticosteroid", routes=["IV","IM"], doses=["125"]),
 D("dexamethasone", brands=["Decadron"], aliases=["decadron","dex"], cls="corticosteroid", routes=["IV","IM","PO"], doses=["10","8"]),
 D("magnesium sulfate", aliases=["mag","mag sulfate","magnesium"], asr=["mag sulphate"], cls="electrolyte", routes=["IV","IO"], units=["g"], doses=["2","1"]),
 D("ondansetron", brands=["Zofran"], aliases=["zofran"], asr=["zofrin","so fran","zophran","zofran's"], cls="antiemetic", routes=["IV","IM","PO","ODT"], doses=["4","8"]),
 D("fentanyl", brands=["Sublimaze"], aliases=["fent"], asr=["fentanil","fentenyl","fenta nil"], cls="opioid analgesic", routes=["IV","IN","IM","IO"], units=["mcg"], doses=["50","100","25","1"]),
 D("morphine", aliases=["MS"], asr=["morphin"], cls="opioid analgesic", routes=["IV","IM"], doses=["2","4","5","10"]),
 D("hydromorphone", brands=["Dilaudid"], aliases=["dilaudid"], cls="opioid analgesic", routes=["IV","IM"], doses=["0.5","1"]),
 D("ketamine", brands=["Ketalar"], aliases=["ket","special K"], asr=["keta mean","ketamin"], cls="dissociative", routes=["IV","IM","IN","IO"], doses=["0.3","1","2","4","50","100"]),
 D("ketorolac", brands=["Toradol"], aliases=["toradol"], asr=["tora doll"], cls="NSAID", routes=["IV","IM"], doses=["15","30"]),
 D("acetaminophen", brands=["Tylenol","Ofirmev"], aliases=["tylenol","APAP"], cls="analgesic", routes=["PO","IV"], doses=["500","650","1000"]),
 D("ibuprofen", brands=["Motrin","Advil"], aliases=["motrin","advil"], cls="NSAID", routes=["PO"], doses=["400","600","800"]),
 D("midazolam", brands=["Versed"], aliases=["versed"], asr=["ver said","versed's","midazolom","mid as olam"], cls="benzodiazepine", routes=["IV","IM","IN","IO"], doses=["2","2.5","5","10"]),
 D("lorazepam", brands=["Ativan"], aliases=["ativan"], asr=["ativen","adivan"], cls="benzodiazepine", routes=["IV","IM"], doses=["1","2","4"]),
 D("diazepam", brands=["Valium","Diastat"], aliases=["valium"], cls="benzodiazepine", routes=["IV","PR"], doses=["5","10"]),
 D("amiodarone", brands=["Cordarone","Nexterone"], aliases=["amio"], asr=["amy oderone","amiodaron","amioderone"], cls="antiarrhythmic", routes=["IV","IO"], doses=["300","150"]),
 D("adenosine", brands=["Adenocard"], aliases=["adenocard"], asr=["adenoseen","a denosine"], cls="antiarrhythmic", routes=["IV"], doses=["6","12"]),
 D("atropine", asr=["a tropine","atropeen"], cls="anticholinergic", routes=["IV","IO"], doses=["1","0.5","2"]),
 D("lidocaine", brands=["Xylocaine"], aliases=["lido"], cls="antiarrhythmic / local anesthetic", routes=["IV","IO"], doses=["100","40","1.5"]),
 D("diltiazem", brands=["Cardizem"], aliases=["cardizem"], asr=["cardi zem","dil tiazem"], cls="calcium channel blocker", routes=["IV"], doses=["10","15","20"]),
 D("metoprolol", brands=["Lopressor","Toprol"], aliases=["lopressor"], cls="beta blocker", routes=["IV","PO"], doses=["5","25"]),
 D("calcium chloride", aliases=["calcium","CaCl"], cls="electrolyte", routes=["IV","IO"], units=["g","mg"], doses=["1","1000"]),
 D("calcium gluconate", cls="electrolyte", routes=["IV"], units=["g"], doses=["1","3"]),
 D("sodium bicarbonate", aliases=["bicarb","sodium bicarb","amp of bicarb"], cls="alkalinizer", routes=["IV","IO"], units=["mEq"], doses=["50","1"]),
 D("normal saline", aliases=["NS","saline","fluid bolus","bolus","0.9% sodium chloride"], cls="crystalloid", routes=["IV","IO"], units=["mL","L"], doses=["500","1000","250","20"]),
 D("lactated Ringer's", aliases=["LR","lactated ringers","ringers"], cls="crystalloid", routes=["IV","IO"], units=["mL","L"], doses=["500","1000"]),
 D("oxygen", aliases=["O2","non-rebreather","NRB","nasal cannula","NC","blow-by"], asr=["o two","o 2"], cls="gas", routes=["NC","NRB","BVM","CPAP","inhaled"], units=["L/min","LPM","%"], doses=["2","4","15","10"]),
 D("tranexamic acid", aliases=["TXA"], asr=["t x a"], cls="antifibrinolytic", routes=["IV","IO"], units=["g","mg"], doses=["1","1000","2"]),
 D("haloperidol", brands=["Haldol"], aliases=["haldol"], cls="antipsychotic", routes=["IM","IV"], doses=["5","10"]),
 D("droperidol", brands=["Inapsine"], cls="antipsychotic", routes=["IM","IV"], doses=["2.5","5"]),
 D("olanzapine", brands=["Zyprexa"], aliases=["zyprexa"], cls="antipsychotic", routes=["IM","ODT"], doses=["10"]),
 D("promethazine", brands=["Phenergan"], aliases=["phenergan"], cls="antiemetic", routes=["IV","IM"], doses=["12.5","25"]),
 D("prochlorperazine", brands=["Compazine"], aliases=["compazine"], cls="antiemetic", routes=["IV","IM"], doses=["10"]),
 D("furosemide", brands=["Lasix"], aliases=["lasix"], cls="loop diuretic", routes=["IV","PO"], doses=["40","20"]),
 D("norepinephrine", brands=["Levophed"], aliases=["levophed","norepi"], cls="vasopressor", routes=["IV"], units=["mcg/min","mcg"], doses=["2","4"]),
 D("dopamine", cls="vasopressor", routes=["IV"], units=["mcg/kg/min"], doses=["5","10"]),
 D("etomidate", brands=["Amidate"], cls="sedative / induction", routes=["IV"], doses=["20","0.3"]),
 D("rocuronium", brands=["Zemuron"], aliases=["roc","rocc"], cls="paralytic", routes=["IV"], doses=["100","1"]),
 D("succinylcholine", aliases=["sux","succs","anectine"], cls="paralytic", routes=["IV"], doses=["100","1.5"]),
 D("oxytocin", brands=["Pitocin"], aliases=["pitocin"], cls="hormone", routes=["IM","IV"], units=["units"], doses=["10"]),
 D("terbutaline", aliases=["terb"], cls="beta-2 agonist", routes=["SQ"], doses=["0.25"]),
 D("hydroxocobalamin", brands=["Cyanokit"], aliases=["cyanokit"], cls="antidote", routes=["IV"], units=["g"], doses=["5"]),
 D("activated charcoal", aliases=["charcoal","actidose"], cls="adsorbent", routes=["PO"], units=["g"], doses=["50","25"]),
 D("nitrous oxide", aliases=["nitrous","nitronox"], cls="analgesic gas", routes=["inhaled"], units=["%"], doses=["50"]),
 D("thiamine", aliases=["vitamin B1"], cls="vitamin", routes=["IV","IM"], doses=["100"]),
 D("heparin", cls="anticoagulant", routes=["IV"], units=["units"], doses=["4000","5000"]),
 D("ticagrelor", brands=["Brilinta"], aliases=["brilinta"], cls="antiplatelet", routes=["PO"], doses=["180"]),
]
# Patient home medications (heard in history, not given by EMS)
home_meds = ["metformin","insulin","Lantus","Humalog","lisinopril","amlodipine","atorvastatin","Lipitor","simvastatin","levothyroxine","Synthroid",
  "apixaban","Eliquis","rivaroxaban","Xarelto","warfarin","Coumadin","clopidogrel","Plavix","metoprolol","carvedilol","losartan",
  "hydrochlorothiazide","HCTZ","furosemide","Lasix","gabapentin","sertraline","Zoloft","fluoxetine","Prozac","oxycodone","Percocet",
  "hydrocodone","Norco","tramadol","alprazolam","Xanax","clonazepam","Klonopin","levetiracetam","Keppra","phenytoin","Dilantin",
  "lamotrigine","Lamictal","Depakote","valproic acid","prednisone","montelukast","Singulair","Advair","Symbicort","fluticasone",
  "omeprazole","pantoprazole","digoxin","Entresto","sildenafil","Viagra","tamsulosin","donepezil","Aricept","Suboxone","buprenorphine","methadone"]
routes = {"PO":["by mouth","orally","oral","chewed","p o"],"SL":["sublingual","under the tongue","s l"],"IV":["intravenous","i v","IV push","slow push"],
  "IO":["intraosseous","i o"],"IM":["intramuscular","i m","in the thigh","lateral thigh","deltoid"],"IN":["intranasal","nasal","in the nose","atomized","MAD"],
  "SQ":["subcutaneous","sub q","subcu","SC"],"neb":["nebulized","nebulizer","via neb","breathing treatment","hand-held neb"],"inhaled":["MDI","inhaler","puffs"],
  "ET":["endotracheal","down the tube"],"PR":["rectal","rectally"],"topical":["on the skin","paste"],"buccal":["in the cheek"],"ODT":["dissolving tab"]}
units = {"mg":["milligrams","milligram","milligrams of","mgs","migs"],"mcg":["micrograms","microgram","mics","mikes","mcg","ug"],"g":["grams","gram","gm"],
  "mL":["milliliters","mls","cc","ccs","ml"],"L":["liters","liter"],"L/min":["liters per minute","LPM","liters a minute","liters"],"units":["units","U"],
  "mEq":["milliequivalents","meq","m e q"],"puffs":["puffs","puff"],"J":["joules","jewels"],"%":["percent"],"mcg/kg/min":["mics per kilo per minute"],"mg/kg":["milligrams per kilo","mgs per kilo"]}
vitals = {
 "bp":{"aliases":["BP","blood pressure","pressure","b p"],"pattern":"\\b(\\d{2,3})\\s*(?:/|over)\\s*(\\d{2,3})\\b","unit":"mmHg"},
 "hr":{"aliases":["HR","heart rate","pulse","rate","heart's at","p"],"pattern":"\\b(\\d{2,3})\\b","unit":"bpm"},
 "rr":{"aliases":["RR","resp","resps","respirations","respiratory rate","breathing at"],"pattern":"\\b(\\d{1,2})\\b","unit":"/min"},
 "spo2":{"aliases":["SpO2","sat","sats","pulse ox","O2 sat","oxygen saturation","satting","sat'ing","spo two"],"pattern":"\\b(\\d{2,3})\\s*(?:%|percent)?","unit":"%"},
 "bgl":{"aliases":["BGL","blood glucose","blood sugar","sugar","glucose","CBG","dextro","accucheck","accu-chek","BG"],"pattern":"\\b(\\d{2,3}|HI|LO|high|low)\\b","unit":"mg/dL"},
 "etco2":{"aliases":["ETCO2","end tidal","end-tidal","capno","wave form capno","CO2"],"pattern":"\\b(\\d{1,3})\\b","unit":"mmHg"},
 "temp":{"aliases":["temp","temperature"],"pattern":"\\b(\\d{2,3}(?:\\.\\d)?)\\b","unit":"F"},
 "gcs":{"aliases":["GCS","Glasgow","glasgow coma scale","GCS of"],"pattern":"\\b(3|4|5|6|7|8|9|1[0-5])\\b","unit":""},
 "pain":{"aliases":["pain","pain scale","out of ten","out of 10","on a scale"],"pattern":"\\b(10|[0-9])\\s*(?:/|out of)\\s*10\\b","unit":"/10"},
}
procedures = {
 "12-lead ECG":["12 lead","twelve lead","12-lead","EKG","ECG","transmit the 12"],"cardiac monitor":["on the monitor","monitor","pads on","4 lead"],
 "IV access":["IV","line","got a line","18 in the AC","20 in the left hand","saline lock","established IV","18 gauge","20 gauge"],
 "IO access":["IO","EZ-IO","drilled","tibial IO","humeral IO"],"CPR":["compressions","CPR","starting compressions"],"defibrillation":["shock","shocking","clear","defib","200 joules","shock advised"],
 "synchronized cardioversion":["cardioversion","sync","synchronized"],"transcutaneous pacing":["pacing","pace","pacer pads"],"BVM ventilation":["bagging","BVM","bag valve mask","bag him","bag her"],
 "endotracheal intubation":["intubate","tube","ETT","intubated","tubed"],"supraglottic airway":["i-gel","King airway","King","LMA","supraglottic"],"OPA":["OPA","oral airway"],"NPA":["NPA","nasal trumpet","nasal airway"],
 "suction":["suction","suctioning"],"CPAP":["CPAP","c pap","see pap"],"needle decompression":["needle decompression","needle d","decompress"],"tourniquet":["tourniquet","TQ","CAT"],
 "wound packing":["packing","packed the wound","hemostatic gauze"],"bandaging":["bandage","dressing","4x4"],"splinting":["splint","SAM splint","traction splint"],
 "spinal motion restriction":["c-collar","c collar","collar","SMR","backboard","spinal precautions","full spinal"],"pelvic binder":["pelvic binder","binder","sheet the pelvis"],
 "glucose check":["finger stick","check a sugar","check her sugar","check his sugar","BGL check"],"stroke scale":["BE-FAST","BEFAST","Cincinnati","stroke scale","LAMS","FAST exam","RACE score"],
 "nebulizer":["neb","nebulizer treatment","breathing treatment"],"oxygen":["non-rebreather","nasal cannula","on O2","put her on oxygen","put him on oxygen"],"vagal maneuver":["modified valsalva","vagal","bear down"],
 "restraint":["restraints","soft restraints"],"childbirth":["delivered","crowning"],"cooling":["cold packs","cooling"],"refusal":["AMA","refusal","signed off","sign the refusal","release"],
}
status_terms = ["A&O×4","A&Ox4","A and O times four","alert and oriented times four","A&O×3","A and O times three","A&O×2","A&O×1","CAOx4","GCS 15","altered","AMS","altered mental status",
 "unresponsive","responsive to verbal","responsive to pain","AVPU","alert","lethargic","postictal","combative","confused","compensating","decompensating","stable","unstable","improving","worsening",
 "no change","ROSC","pulses back","pulseless","apneic","agonal","cyanotic","diaphoretic","pale, cool, diaphoretic","PCD","warm and dry","skin signs good","flushed","mottled",
 "lung sounds clear","clear bilaterally","wheezes","wheezing","rales","crackles","diminished","stridor","JVD","pedal edema","tripoding","accessory muscle use","speaking in one-word sentences",
 "pupils PERRL","PERRL","pinpoint","pinpoint pupils","facial droop","arm drift","slurred speech","aphasia","last known well","LKW","sinus tach","sinus rhythm","NSR","afib","a-fib","SVT","VF","v-fib","v-tach","asystole","PEA","STEMI","ST elevation","STEMI alert","stroke alert","trauma alert","priority 1","code 3","hot","cold","non-emergent"]
dispatch_terms = {"dispatch":["dispatched for","dispatched to","toned out for","call came in as","called for","reported as","respond to","per dispatch","CAD says","caller states"],
  "found":["found","on arrival","upon arrival","we found","patient found","pt found","found sitting","found lying","found supine","found on the floor","on scene we have","presents with","actually"]}
time_events = {  # NEMSIS v3.5 eTimes mapping and spoken cues
 "eTimes.01":{"name":"PSAP call","cues":["call received"]},"eTimes.03":{"name":"unit notified by dispatch","cues":["toned out","dispatched"]},
 "eTimes.05":{"name":"unit en route","cues":["en route","responding","we're en route"]},"eTimes.06":{"name":"unit arrived on scene","cues":["on scene","arriving on scene","we're on scene"]},
 "eTimes.07":{"name":"arrived at patient","cues":["at patient side","with the patient","at patient"]},"eTimes.09":{"name":"unit left scene","cues":["transporting","leaving scene","we're transporting","en route to"]},
 "eTimes.11":{"name":"patient arrived at destination","cues":["arrived at","at the hospital","we're at","arriving at destination","pulling in"]},
 "eTimes.12":{"name":"destination patient transfer of care","cues":["transfer of care","handing off","giving report","bed assigned","handoff complete"]},
 "eTimes.13":{"name":"unit back in service","cues":["back in service","in service","available"]}}
jargon = ["BGL","SpO2","ETCO2","GCS","A&O×4","PCD","PERRL","LKW","STEMI","ROSC","12-lead","IO","IV","NRB","NC","BVM","CPAP","SMR","AMA","PMH","HPI","SAMPLE","OPQRST","DCAP-BTLS","CMS","PMS",
 "c-collar","non-rebreather","diaphoretic","tachy","brady","hypotensive","hypertensive","hypoxic","postictal","syncope","near-syncope","LOC","no LOC","CC","chief complaint","NKDA","NKA","ETOH","GSW","MVC","MVA","T-bone",
 "rollover","airbags deployed","starred windshield","entrapment","extrication","ALS","BLS","medic","rig","bus","box","ED","ER","triage","wall time","bed","charge nurse","RN","doc","STEMI alert","stroke alert",
 "trauma alert","cath lab","ABCs","sick","not sick","compensating","load and go","IMIST-AMBO","SBAR","DNR","POLST","hospice","lift assist","refusal","sign off","rule of nines","pinpoint","agonal","PEA","asystole","V-fib","shockable"]
prompt = ("EMS call. Patient A&O×4, GCS 15. BP 142/88, HR 110, RR 20, SpO2 94%, BGL 42, ETCO2 35. "
          "Aspirin 324 mg PO, nitro 0.4 mg SL, Narcan 4 mg IN, D10, glucagon, albuterol, DuoNeb, epi 0.3 mg IM, Benadryl, Solu-Medrol, "
          "Zofran 4 mg IV, fentanyl 50 mcg, Versed, Ativan, amiodarone, adenosine, TXA. 12-lead, STEMI, IV, IO, CPAP, BVM, c-collar.")
out = dict(version="0.1-data-agent-seed", note="Seed EMS dictionary from the data agent. Keys: drugs[] (EMS-administered), home_meds[], routes{canonical:[aliases]}, "
  "units{canonical:[aliases]}, vitals{key:{aliases,pattern,unit}}, procedures{canonical:[aliases]}, status_terms[], dispatch_terms{dispatch,found}, time_events{NEMSIS eTimes}, "
  "jargon[], initial_prompt (≤ ~200 tokens, for whisper.cpp --prompt).",
  drugs=drugs, home_meds=home_meds, routes=routes, units=units, vitals=vitals, procedures=procedures, status_terms=status_terms,
  dispatch_terms=dispatch_terms, time_events=time_events, jargon=jargon, initial_prompt=prompt)
p = pathlib.Path(__file__).resolve().parents[2] / "shared" / "formulary.json"
p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
print(p, len(drugs), "drugs")
