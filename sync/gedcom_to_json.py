#!/usr/bin/env python3
"""
Convert a Gramps GEDCOM export into the JSON files the family tree site reads.

Usage:
    python gedcom_to_json.py data/raw/family.ged \\
        --places data/places.json \\
        --out site/data \\
        [--root I0000]

Produces (in --out):
    tree.json       {"root": "<id>", "people": {...}}
    marriages.json  {"<id1>_<id2>": "YYYY-MM-DD", ...}
    places.json     merged copy of the places lookup (curated + any
                     coordinates found embedded in the GEDCOM itself)

Also prints a list of place names that still have no coordinates, so you
know what to add next time (either directly in Gramps, or to
data/places.json).
"""
import argparse
import json
import re
import sys
from pathlib import Path

MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def cid(s):
    """Strip the @...@ wrapper GEDCOM puts around pointers."""
    return s.strip("@") if s else s


def norm_date(s):
    if not s:
        return None
    parts = s.strip().split()
    if len(parts) == 3 and parts[1].upper() in MONTHS:
        try:
            return f"{parts[2]}-{MONTHS[parts[1].upper()]}-{int(parts[0]):02d}"
        except ValueError:
            return s.strip()
    if len(parts) == 1 and parts[0].isdigit():
        return parts[0]
    return s.strip()


def tokenize(path):
    lines = []
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            raw = raw.rstrip("\r\n")
            m = re.match(r"^(\d+)\s+(@\S+@|\S+)\s?(.*)$", raw)
            if not m:
                continue
            lines.append((int(m.group(1)), m.group(2), m.group(3)))
    return lines


def parse_gedcom(path):
    lines = tokenize(path)
    indi, fam = {}, {}
    i, n = 0, len(lines)

    while i < n:
        level, tag, val = lines[i]

        if level == 0 and val == "INDI":
            iid = cid(tag)
            rec = {"names": [], "sex": None, "birt": {}, "deat": {},
                   "occu": [], "famc": [], "fams": []}
            i += 1
            cur_name = cur_event = cur_famc = None
            while i < n and lines[i][0] > 0:
                lv, tg, vl = lines[i]
                if lv == 1 and tg == "NAME":
                    cur_name = {"raw": vl, "type": None, "givn": None, "surn": None}
                    rec["names"].append(cur_name)
                    cur_event = None
                elif lv == 2 and tg == "TYPE" and cur_name is not None and cur_event is None:
                    cur_name["type"] = vl
                elif lv == 2 and tg == "GIVN" and cur_name is not None:
                    cur_name["givn"] = vl
                elif lv == 2 and tg == "SURN" and cur_name is not None:
                    cur_name["surn"] = vl
                elif lv == 1 and tg == "SEX":
                    rec["sex"] = vl
                    cur_name = cur_event = None
                elif lv == 1 and tg == "BIRT":
                    cur_event = "birt"
                    cur_name = None
                elif lv == 1 and tg == "DEAT":
                    cur_event = "deat"
                    cur_name = None
                elif lv == 2 and tg == "DATE" and cur_event in ("birt", "deat"):
                    rec[cur_event]["date"] = vl
                elif lv == 2 and tg == "PLAC" and cur_event in ("birt", "deat"):
                    rec[cur_event]["place"] = vl
                elif lv == 2 and tg == "NOTE" and cur_event in ("birt", "deat"):
                    rec[cur_event]["desc"] = vl
                elif lv == 3 and tg == "LATI" and cur_event in ("birt", "deat"):
                    rec[cur_event]["lat"] = float(vl.lstrip("N").lstrip("S").rstrip() or 0) if vl else None
                    rec[cur_event]["lat_raw"] = vl
                elif lv == 3 and tg == "LONG" and cur_event in ("birt", "deat"):
                    rec[cur_event]["lng_raw"] = vl
                elif lv == 1 and tg == "OCCU":
                    rec["occu"].append(vl)
                    cur_event = cur_name = None
                elif lv == 1 and tg == "FAMC":
                    cur_famc = {"fam_id": cid(vl), "pedi": "birth"}
                    rec["famc"].append(cur_famc)
                    cur_event = cur_name = None
                elif lv == 2 and tg == "PEDI" and cur_famc is not None:
                    cur_famc["pedi"] = vl
                elif lv == 1 and tg == "FAMS":
                    rec["fams"].append(cid(vl))
                    cur_event = cur_name = cur_famc = None
                elif lv == 1:
                    cur_event = cur_name = cur_famc = None
                i += 1
            indi[iid] = rec
            continue

        if level == 0 and val == "FAM":
            fid = cid(tag)
            rec = {"husb": None, "wife": None, "chil": [], "marr": {}}
            i += 1
            cur_event = None
            while i < n and lines[i][0] > 0:
                lv, tg, vl = lines[i]
                if lv == 1 and tg == "HUSB":
                    rec["husb"] = cid(vl); cur_event = None
                elif lv == 1 and tg == "WIFE":
                    rec["wife"] = cid(vl); cur_event = None
                elif lv == 1 and tg == "CHIL":
                    rec["chil"].append(cid(vl)); cur_event = None
                elif lv == 1 and tg == "MARR":
                    cur_event = "marr"
                elif lv == 2 and tg == "DATE" and cur_event == "marr":
                    rec["marr"]["date"] = vl
                elif lv == 2 and tg == "PLAC" and cur_event == "marr":
                    rec["marr"]["place"] = vl
                elif lv == 2 and tg == "NOTE" and cur_event == "marr":
                    rec["marr"]["desc"] = vl
                elif lv == 1:
                    cur_event = None
                i += 1
            fam[fid] = rec
            continue

        i += 1

    return indi, fam


def parse_lati_long(lat_raw, lng_raw):
    """GEDCOM LATI/LONG look like 'N48.804878' / 'E2.120375'."""
    def conv(raw):
        if not raw:
            return None
        sign = -1 if raw[0] in "SW" else 1
        try:
            return sign * float(raw[1:])
        except ValueError:
            return None
    return conv(lat_raw), conv(lng_raw)


def build_people(indi, fam):
    people = {}
    embedded_places = {}

    for iid, rec in indi.items():
        names = rec["names"]
        chosen = next((nm for nm in names if nm["type"] == "birth"), None) or (names[0] if names else None)
        surname, given = None, []
        if chosen:
            surname = chosen["surn"] or None
            if chosen["givn"]:
                given = [g.strip() for g in re.split(r",\s*", chosen["givn"]) if g.strip()]
            if not surname or not given:
                m = re.match(r"^(.*?)\s*/(.*)/\s*$", chosen["raw"])
                if m:
                    if not given and m.group(1).strip():
                        given = [g.strip() for g in re.split(r",\s*", m.group(1).strip()) if g.strip()]
                    if not surname:
                        surname = m.group(2).strip() or None

        def event(ev):
            if not rec[ev]:
                return None
            place = rec[ev].get("place")
            if place and rec[ev].get("lat_raw"):
                lat, lng = parse_lati_long(rec[ev].get("lat_raw"), rec[ev].get("lng_raw"))
                if lat is not None and lng is not None:
                    embedded_places[place] = [lat, lng]
            return {"date": norm_date(rec[ev].get("date")), "place": place, "desc": rec[ev].get("desc")}

        birth, death = event("birt"), event("deat")
        occupation = " · ".join(rec["occu"]) if rec["occu"] else None

        parents_default = []
        parentSets = None
        if len(rec["famc"]) >= 2:
            sets = {}
            for fc in rec["famc"]:
                f = fam.get(fc["fam_id"], {})
                par_ids = [x for x in [f.get("husb"), f.get("wife")] if x]
                key = {"birth": "biological", "adopted": "adoptive"}.get(fc["pedi"], fc["pedi"])
                sets[key] = par_ids
            parentSets = sets
        elif len(rec["famc"]) == 1:
            f = fam.get(rec["famc"][0]["fam_id"], {})
            parents_default = [x for x in [f.get("husb"), f.get("wife")] if x]

        spouses, children = [], []
        for fsid in rec["fams"]:
            f = fam.get(fsid, {})
            other = f.get("wife") if f.get("husb") == iid else (f.get("husb") if f.get("wife") == iid else None)
            if other and other not in spouses:
                spouses.append(other)
            for c in f.get("chil", []):
                if c not in children:
                    children.append(c)

        entry = {
            "surname": surname, "given": given if given else ["?"],
            "gender": rec["sex"], "birth": birth, "death": death,
            "occupation": occupation, "parents": parents_default,
            "spouses": spouses, "children": children,
        }
        if parentSets:
            entry["parentSets"] = parentSets
        people[iid] = entry

    marriages = {}
    for f in fam.values():
        if f["marr"].get("date") and f.get("husb") and f.get("wife"):
            key = "_".join(sorted([f["husb"], f["wife"]]))
            marriages[key] = {
                "date": norm_date(f["marr"]["date"]),
                "place": f["marr"].get("place"),
                "desc": f["marr"].get("desc"),
            }

    return people, marriages, embedded_places


def collect_place_names(people):
    names = set()
    for p in people.values():
        for ev in ("birth", "death"):
            if p[ev] and p[ev].get("place"):
                names.add(p[ev]["place"])
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gedcom", type=Path, help="Path to the .ged file exported from Gramps")
    ap.add_argument("--places", type=Path, default=Path("data/places.json"), help="Curated place -> [lat,lng] lookup")
    ap.add_argument("--out", type=Path, default=Path("site/data"), help="Output directory")
    ap.add_argument("--root", type=str, default=None, help="Person id to use as the default focus (defaults to whatever was used last time, from --out/tree.json)")
    args = ap.parse_args()

    if not args.gedcom.exists():
        sys.exit(f"GEDCOM file not found: {args.gedcom}")

    indi, fam = parse_gedcom(args.gedcom)
    people, marriages, embedded_places = build_people(indi, fam)

    # figure out the root person
    root = args.root
    if not root:
        existing_tree = args.out / "tree.json"
        if existing_tree.exists():
            try:
                prev = json.loads(existing_tree.read_text(encoding="utf-8"))
                if prev.get("root") in people:
                    root = prev["root"]
            except (json.JSONDecodeError, KeyError):
                pass
    if not root:
        root = next(iter(people))
        print(f"Warning: no --root given and none found from a previous run; "
              f"defaulting to {root}. Pass --root to set it explicitly.", file=sys.stderr)
    if root not in people:
        sys.exit(f"--root {root} is not a person id in this GEDCOM file.")

    # merge place coordinates: curated file, overlaid with anything embedded in the GEDCOM itself
    curated = {}
    if args.places.exists():
        curated = json.loads(args.places.read_text(encoding="utf-8"))
    merged_places = {**curated, **embedded_places}

    needed = collect_place_names(people)
    missing = sorted(pl for pl in needed if pl not in merged_places)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tree.json").write_text(
        json.dumps({"root": root, "people": people}, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "marriages.json").write_text(
        json.dumps(marriages, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "places.json").write_text(
        json.dumps(merged_places, ensure_ascii=False, indent=1), encoding="utf-8")

    # also write the merged places back to the curated source file, so
    # coordinates found embedded in the GEDCOM (or added by hand) accumulate
    # over time instead of being re-derived every run
    args.places.parent.mkdir(parents=True, exist_ok=True)
    args.places.write_text(json.dumps(merged_places, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Parsed {len(people)} people, {len(marriages)} marriages, root={root}")
    if embedded_places:
        print(f"Found {len(embedded_places)} coordinate(s) embedded directly in the GEDCOM.")
    if missing:
        print(f"\n{len(missing)} place(s) still have no coordinates and won't show on the map:")
        for pl in missing:
            print(f"  - {pl}")
        print(f"\nAdd them either in Gramps (place coordinates) or directly to {args.places}.")
    else:
        print("All places have coordinates.")


if __name__ == "__main__":
    main()
