#!/usr/bin/env python3
"""Generate BOM and JLCPCB assembly files from the KiCad project with kicad-cli.

Outputs (in BOM/):
  5uH_LISN_BOM.csv   full BOM from the schematic (all parts)
  jlcpcb/jlc_bom.csv JLCPCB assembly BOM  (Comment, Designator, Footprint, LCSC Part #)
  jlcpcb/jlc_cpl.csv JLCPCB placement file (Designator, Mid X, Mid Y, Layer, Rotation)
  hand_bom.csv       parts to buy and solder by hand

JLCPCB places every part that is on the bottom side of the PCB position file.
Part numbers live in the schematic fields manf#, Manufacturer, Mouser code, LCSC;
change them there, then rerun:  python3 BOM/make_bom.py
"""
import csv, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCH, PCB = ROOT / "5uH_LISN.kicad_sch", ROOT / "5uH_LISN.kicad_pcb"
OUT = ROOT / "BOM"

# Rotation corrections for the JLCPCB preview (degrees, added to the KiCad rotation).
# D1-D4: pin 3 (common node) must sit on the single pad; value from the JLCPCB preview.
ROT_OFFSET = {"D1": 270, "D2": 270, "D3": 270, "D4": 270}
NOT_A_PART = {"H1", "H2", "H3", "H4"}  # mounting holes

FIELDS = "Reference,Value,Footprint,${QUANTITY},Manufacturer,manf#,Mouser code,LCSC,Description,${DNP}"
LABELS = "Designator,Value,Footprint,Qty,Manufacturer,MPN,Mouser No,LCSC No,Description,DNP"


def run(*args):
    subprocess.run(["kicad-cli", *args], check=True, stdout=subprocess.DEVNULL)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # one row per part (ungrouped) for filtering; grouped for the full BOM
        run("sch", "export", "bom", "--fields", FIELDS, "--labels", LABELS,
            "--group-by", "", "-o", str(tmp / "parts.csv"), str(SCH))
        run("sch", "export", "bom", "--fields", FIELDS, "--labels", LABELS,
            "--group-by", "Value,Footprint,manf#", "--ref-range-delimiter", "",
            "-o", str(OUT / "5uH_LISN_BOM.csv"), str(SCH))
        run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
            "-o", str(tmp / "pos.csv"), str(PCB))
        parts = {r["Designator"]: r for r in csv.DictReader(open(tmp / "parts.csv"))}
        pos = list(csv.DictReader(open(tmp / "pos.csv")))

    jlc = [p for p in pos if p["Side"] == "bottom"]
    jlc_refs = {p["Ref"] for p in jlc}
    errors = [f"{r}: no LCSC number in schematic" for r in sorted(jlc_refs)
              if not parts.get(r, {}).get("LCSC No")]
    errors += [f"{r}: in PCB but not in schematic" for r in sorted(jlc_refs - parts.keys())]
    if errors:
        sys.exit("\n".join(errors))

    (OUT / "jlcpcb").mkdir(exist_ok=True)

    def grouped(refs, cols):
        groups = {}
        for r in sorted(refs, key=lambda s: (s.rstrip("0123456789"), int("0" + s[len(s.rstrip("0123456789")):]))):
            p = parts[r]
            key = tuple(p[c] for c in cols)
            groups.setdefault(key, []).append(r)
        return groups

    with open(OUT / "jlcpcb" / "jlc_bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fp, mpn, lcsc), refs in grouped(jlc_refs, ["Value", "Footprint", "MPN", "LCSC No"]).items():
            w.writerow([f"{val} {mpn}", ",".join(refs), fp.split(":")[-1], lcsc])

    with open(OUT / "jlcpcb" / "jlc_cpl.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in jlc:
            rot = (float(p["Rot"]) + ROT_OFFSET.get(p["Ref"], 0)) % 360
            w.writerow([p["Ref"], f"{float(p['PosX']):.4f}mm", f"{float(p['PosY']):.4f}mm",
                        "Bottom", f"{rot:g}"])

    hand_refs = set(parts) - jlc_refs - NOT_A_PART
    with open(OUT / "hand_bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Qty", "Value", "Manufacturer", "MPN", "Mouser No", "LCSC No", "Description"])
        for (val, mfr, mpn, mouser, lcsc, desc), refs in grouped(
                hand_refs, ["Value", "Manufacturer", "MPN", "Mouser No", "LCSC No", "Description"]).items():
            w.writerow([",".join(refs), len(refs), val, mfr, mpn, mouser, lcsc, desc])

    print(f"JLCPCB: {len(jlc_refs)} parts placed; hand: {len(hand_refs)} parts")


if __name__ == "__main__":
    main()
