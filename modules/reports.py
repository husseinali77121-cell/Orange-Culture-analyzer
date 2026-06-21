# modules/reports.py
# © Dr. Hussein Ali — Orange Lab
# Summary Image (Pillow) + TXT Report Generator

from __future__ import annotations
import io, re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = ImageDraw = ImageFont = None

from data.antibiotics import AWARE_COLORS, get_commercial_name

def generate_decision_tree_image(
    patient_name:    str,
    age:             int,
    sex:             str,
    weight:          float,
    cl_cr:           float,
    is_renal:        bool,
    is_preg:         bool,
    organism:        str,
    specimen:        str,
    first_line:      List[str],
    preferred:       List[str],
    use_caution:     List[str],
    contraindicated: List[str],
    reserve:         List[str],
    notes:           List[str],
    colony_count:    str = "",
    date_in:         str = "",
    pus_cells:       str = "",
    rbcs:            str = "",
    lab_name:        str = "Orange Lab",
    lab_city:        str = "",
    mdr_result:      Optional[Dict] = None,
    esbl_result:     Optional[Dict] = None,
    phenotypes:      Optional[List] = None,
) -> bytes:
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow غير متاح — أضف Pillow لـ requirements.txt")

    S  = 2
    W  = 2181
    H  = 1496
    P  = 14 * S
    G  = 8  * S

    BG         = (248, 250, 252)
    WHITE      = (255, 255, 255)
    DARK       = (28,  32,  40)
    GRAY       = (95, 100, 112)
    LIGHT_GRAY = (190, 195, 205)
    NAVY       = (4,   26,  63)
    PURPLE_BD  = (120, 75, 178);  PURPLE_BG  = (247, 243, 254)
    GREEN_BD   = (45, 138,  68);  GREEN_BG   = (236, 252, 240);  GREEN_TXT  = (20,  95,  40)
    AMBER_BD   = (195,140,  30);  AMBER_BG   = (255, 250, 228);  AMBER_TXT  = (120,  80,   0)
    RED_BD     = (183, 52,  52);  RED_BG     = (255, 237, 234);  RED_TXT    = (148,  30,  30)
    BLUE_BD    = (35,  90, 172);  BLUE_BG    = (234, 244, 255);  BLUE_TXT   = (15,   55, 145)
    ALERT_BD   = (205,115,  50);  ALERT_BG   = (255, 248, 232);  ALERT_TXT  = (130,  60,   5)
    SPEC_BD    = (35,  90, 172);  SPEC_BG    = (234, 244, 255)
    MICRO_BD   = (30, 130,  65);  MICRO_BG   = (234, 252, 238)
    FL_BD      = (190,138,  28);  FL_BG      = (255, 250, 225)
    FOOT_BD    = (185,192,200);   FOOT_BG    = (247, 249, 251)

    def gf(size: int, bold: bool = False):
        paths = [
            f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if bold else 'Regular'}.ttf",
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, size * S)
            except Exception:
                pass
        return ImageFont.load_default()

    F_HEADER  = gf(20, True)
    F_TITLE   = gf(15, True)
    F_SUBTITL = gf(12, True)
    F_TEXT    = gf(12)
    F_SMALL   = gf(10)
    F_ORG     = gf(26, True)
    F_SUMNUM  = gf(20, True)
    F_BADGE   = gf(9,  True)

    def fh(f) -> int:
        return f.size if hasattr(f, "size") else 14 * S

    def tw(draw, text, font) -> float:
        try:
            return draw.textlength(text, font=font)
        except Exception:
            return len(text) * fh(font) * 0.6

    def rbox(draw, box, bg, bd, radius=14, width=3):
        draw.rounded_rectangle(
            [box[0], box[1], box[2], box[3]],
            radius=radius * S, fill=bg, outline=bd, width=width * S
        )

    def text_wrap(draw, x, y, text, font, fill, max_w, gap=4):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if tw(draw, trial, font) <= max_w:
                cur = trial
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        lh = fh(font) + gap * S
        for line in lines:
            draw.text((x, y), line, fill=fill, font=font)
            y += lh
        return y

    BADGE_COLORS = {"[A]": (20, 138, 68), "[W]": (195, 140, 30)}

    # ألوان AWaRe للنص
    AWARE_TXT_COLORS = {
        "[A]": (20, 138, 68),   # أخضر — Access
        "[W]": (160, 100, 0),   # برتقالي — Watch
    }

    def section_box(draw, box, title, title_color, subtitle, items, bg, bd, ft, fs, fi):
        x1, y1, x2, y2 = box
        rbox(draw, box, bg, bd, radius=16, width=3)
        draw.text((x1 + 14*S, y1 + 12*S), title, fill=title_color, font=ft)
        cy = y1 + 12*S + fh(ft) + 6*S
        if subtitle:
            draw.text((x1 + 14*S, cy), subtitle, fill=(110,115,125), font=fs)
            cy += fh(fs) + 4*S
        draw.line([(x1 + 10*S, cy), (x2 - 10*S, cy)], fill=bd, width=1*S)
        cy += 8*S
        for item in items:
            if cy + fh(fi) + 6*S > y2 - 8*S:
                draw.text((x1 + 14*S, cy), "...", fill=LIGHT_GRAY, font=fi)
                break
            # استخراج الـ badge وتلوين الاسم
            badge = ""
            display_name = item
            for b in ["[A]", "[W]"]:
                if item.endswith(b):
                    badge = b
                    display_name = item[:-len(b)].rstrip()
                    break
            # لون النص حسب AWaRe
            txt_color = AWARE_TXT_COLORS.get(badge, DARK)
            cy = text_wrap(draw, x1 + 14*S, cy, f"• {display_name}",
                           fi, txt_color, x2 - x1 - 26*S, gap=6)

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Header — اسم المعمل متغير بالكامل بدون أي نص ثابت
    rbox(draw, (P, 6*S, W-P, 62*S), NAVY, NAVY, radius=12, width=1)
    htxt = f"{lab_name.upper()}  —  MICROBIOLOGY CDSS"
    if lab_city:
        htxt += f"  |  {lab_city}"
    hw = tw(draw, htxt, F_HEADER)
    draw.text(((W - hw)//2, 16*S), htxt, fill=WHITE, font=F_HEADER)

    # Culture box
    CB = (368*S, 72*S, 870*S, 198*S)
    rbox(draw, CB, WHITE, NAVY, radius=14, width=2)
    ctype = "URINE CULTURE RESULT" if "urine" in specimen.lower() else f"{specimen.upper()} CULTURE RESULT"
    ctw_  = tw(draw, ctype, F_SUBTITL)
    draw.text(((CB[0]+CB[2]-ctw_)//2, CB[1]+12*S), ctype, fill=DARK, font=F_SUBTITL)
    ow = tw(draw, organism, F_ORG)
    draw.text(((CB[0]+CB[2]-ow)//2, CB[1]+38*S), organism, fill=NAVY, font=F_ORG)
    cc_parts = []
    if colony_count:
        cc_parts.append(f"Colony Count: {colony_count}")
    if date_in:
        cc_parts.append(f"Date In: {date_in}")
    if cc_parts:
        cc_txt = "   |   ".join(cc_parts)
        cctw   = tw(draw, cc_txt, F_TEXT)
        draw.text(((CB[0]+CB[2]-cctw)//2, CB[1]+38*S+fh(F_ORG)+6*S),
                  cc_txt, fill=(90, 90, 140), font=F_TEXT)

    # Alert box — ديناميكي حسب MDR/ESBL/Phenotype
    _ph_names  = [p.get("phenotype","") for p in (phenotypes or [])]
    _has_cre   = any(p in _ph_names for p in ["CRE","CRAB","CRPA"])
    _mdr_lvl   = (mdr_result or {}).get("level")
    _esbl_prob = (esbl_result or {}).get("probability")
    _has_xdr   = _mdr_lvl in ("XDR","PDR")
    _has_esbl  = _esbl_prob in ("high","carbapenemase")

    if _has_cre or _has_xdr:
        AB_BG=(255,237,234); AB_BD=(183,52,52);  AB_TXT=(148,30,30)
        _alert_title = "🚨 CRE / XDR ALERT"
    elif _has_esbl or _mdr_lvl == "MDR":
        AB_BG=(255,248,232); AB_BD=(205,115,50); AB_TXT=(130,60,5)
        _alert_title = "⚠  ESBL / MDR ALERT"
    else:
        AB_BG=ALERT_BG; AB_BD=ALERT_BD; AB_TXT=ALERT_TXT
        _alert_title = "⚠  IMPORTANT ALERT"

    AB = (885*S, 72*S, W-P, 198*S)
    rbox(draw, AB, AB_BG, AB_BD, radius=14, width=3)
    draw.text((AB[0]+12*S, 72*S+12*S), _alert_title, fill=AB_TXT, font=F_SUBTITL)
    alerts: List[str] = []

    if _mdr_lvl:
        rc   = (mdr_result or {}).get("resistant_count",0)
        rt   = (mdr_result or {}).get("total_tested",0)
        cats = (mdr_result or {}).get("resistant_categories",[])
        alerts.append(f"{_mdr_lvl}: R {rc}/{rt} categories")
        if cats:
            alerts.append(f"R: {', '.join(cats[:3])}")

    if _esbl_prob == "carbapenemase":
        alerts += ["Carbapenemase (KPC/MBL/OXA)!","Send to reference lab NOW."]
    elif _esbl_prob == "high":
        alerts += ["High probability ESBL Producer","Use Carbapenems for severe cases"]
    elif _esbl_prob == "moderate":
        alerts += ["ESBL confirmation needed","Double Disk Synergy Test"]

    for ph in (phenotypes or [])[:2]:
        if ph.get("phenotype") not in ("Possible MRSA",):
            alerts.append(f"Phenotype: {ph.get('phenotype','')}")

    org_l = organism.lower()
    if not alerts:
        if "klebsiella" in org_l:
            alerts += ["Consider ESBL screening","Natural R: Ampicillin"]
        elif "e. coli" in org_l or "coli" in org_l:
            alerts += ["Most common UTI pathogen","Verify culture sensitivity"]
        elif "pseudomonas" in org_l:
            alerts += ["High intrinsic resistance","Anti-pseudomonal required"]
        elif "mrsa" in org_l or "staphylococcus" in org_l:
            alerts += ["Check MRSA status","Vancomycin/Linezolid if MRSA"]
        elif "acinetobacter" in org_l:
            alerts += ["MDR risk — check Carbapenem S/I/R"]
        else:
            alerts = ["Verify sensitivity results."]

    if is_renal:
        alerts.append(f"Renal adj. (CrCl {cl_cr:.0f} ml/min)")
    if is_preg and age >= 18:
        alerts.append("Pregnancy: verify fetal safety")

    ay = 72*S + 12*S + fh(F_SUBTITL) + 8*S
    for al in alerts[:6]:
        if ay + fh(F_SMALL) + 4*S > AB[3] - 6*S:
            break
        ay = text_wrap(draw, AB[0]+12*S, ay, f"• {al}",
                       F_SMALL, AB_TXT, AB[2]-AB[0]-22*S, gap=4)
        ay += 2*S

    # Patient box
    PB = (P, 72*S, 358*S, 198*S)
    rbox(draw, PB, PURPLE_BG, PURPLE_BD, radius=14, width=3)
    draw.text((P+14*S, 84*S), "PATIENT DETAILS", fill=PURPLE_BD, font=F_TITLE)
    p_lines = []
    if patient_name:
        p_lines.append(f"Name: {patient_name}")
    p_lines.append(f"{'Male' if sex == 'Male' else 'Female'}, {age} years")
    if is_renal:
        p_lines.append(f"Weight: {weight} kg")
        p_lines.append(f"Renal: IMPAIRED")
        p_lines.append(f"CrCl: {cl_cr:.1f} ml/min ({get_renal_severity(cl_cr)})")
    else:
        p_lines.append("Renal: Normal")
    if sex == "Female" and age >= 18:
        p_lines.append(f"Pregnancy: {'Yes' if is_preg else 'No'}")
    if age < 18:
        p_lines.append("Verify age-specific suitability.")
    py = 106*S
    for ln in p_lines[:7]:
        draw.text((P+14*S, py), f"• {ln}", fill=DARK, font=F_TEXT)
        py += fh(F_TEXT) + 5*S

    # Row 2: Specimen | Microscopic | First-line
    R2_Y1 = 210*S
    R2_Y2 = 310*S
    r2w   = (W - 2*P - 2*G) // 3
    spec_items  = [f"Type: {specimen}", "Method: Culture & Sensitivity"]
    micro_items = [
        f"Pus Cells: {pus_cells if pus_cells else '-'} /HPF",
        f"RBCs:      {rbcs if rbcs else '-'} /HPF",
    ]
    fl_items = first_line[:4] or ["-"]
    r2_data = [
        ("SPECIMEN",           spec_items,  SPEC_BD,  SPEC_BG,  "Specimen"),
        ("MICROSCOPIC EXAM",   micro_items, MICRO_BD, MICRO_BG, "Microscopy"),
        ("FIRST-LINE OPTIONS", fl_items,    FL_BD,    FL_BG,    "First-Line"),
    ]
    for i, (title, items, bd, bg, _) in enumerate(r2_data):
        bx1 = P + i*(r2w+G)
        bx2 = bx1 + r2w
        rbox(draw, (bx1, R2_Y1, bx2, R2_Y2), bg, bd, radius=12, width=2)
        draw.text((bx1+12*S, R2_Y1+9*S), title, fill=bd, font=F_SUBTITL)
        iy = R2_Y1 + 32*S
        for it in items[:4]:
            iy = text_wrap(draw, bx1+14*S, iy, f"• {it}", F_SMALL, DARK, bx2-bx1-24*S, gap=4)

    # 4 main columns
    COL_Y1 = 323*S
    COL_Y2 = H - 115*S
    cw     = (W - 2*P - 3*G) // 4
    avoid_title = "AVOID IN PREGNANCY" if is_preg else "AVOID / CONTRAINDICT."
    avoid_sub   = "Contraindicated / Pregnancy" if is_preg else "Due to other factors"
    columns = [
        ("PREFERRED (SAFE)",  "Preferred oral options",  preferred,       GREEN_BD, GREEN_BG, GREEN_TXT),
        ("USE WITH CAUTION",  "Use with caution",         use_caution,     AMBER_BD, AMBER_BG, AMBER_TXT),
        (avoid_title,         avoid_sub,                  contraindicated, RED_BD,   RED_BG,   RED_TXT),
        ("RESERVE (SEVERE)",  "ESBL / Severe cases only", reserve,         BLUE_BD,  BLUE_BG,  BLUE_TXT),
    ]
    for i, (title, subtitle, items, bd, bg, tc) in enumerate(columns):
        bx1 = P + i*(cw+G)
        bx2 = bx1 + cw
        section_box(draw, (bx1, COL_Y1, bx2, COL_Y2),
                    title, tc, subtitle, items or ["-"],
                    bg, bd, F_TITLE, F_SMALL, F_TEXT)

    # Footer — 4 boxes
    FY1 = H - 116*S
    FY2 = H - 8*S
    fw4 = (W - 2*P - 3*G) // 4

    # WHO AWaRe
    fx1 = P; fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "WHO AWaRe", fill=DARK, font=F_SUBTITL)
    bx = fx1 + 10*S
    by = FY1 + 30*S
    for label, color in [("ACCESS", GREEN_TXT), ("WATCH", AMBER_TXT), ("RESERVE", RED_TXT)]:
        lw      = tw(draw, label, F_BADGE)
        badge_w = int(lw) + 10*S
        rbox(draw, (bx-2*S, by-2*S, bx+badge_w, by+fh(F_BADGE)+4*S), color, color, radius=5, width=1)
        draw.text((bx+3*S, by), label, fill=WHITE, font=F_BADGE)
        bx += badge_w + 5*S
    draw.text((fx1+10*S, by+fh(F_BADGE)+7*S), "1st/2nd | Caution | Last resort", fill=GRAY, font=F_SMALL)

    # Summary
    fx1 = P + fw4 + G; fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "SUMMARY", fill=DARK, font=F_SUBTITL)
    sum_items = [
        (f"~{len(preferred)}",       "Recommended", GREEN_TXT),
        (f"~{len(use_caution)}",     "Caution",     AMBER_TXT),
        (f"~{len(contraindicated)}", "Avoided",     RED_TXT),
        (f"~{len(reserve)}",         "Reserve",     BLUE_TXT),
    ]
    sw = (fx2 - fx1 - 16*S) // 4
    for j, (num, lbl, clr) in enumerate(sum_items):
        sx = fx1 + 10*S + j * sw
        draw.text((sx, FY1+28*S), num, fill=clr,  font=F_SUMNUM)
        draw.text((sx, FY1+62*S), lbl, fill=GRAY, font=F_SMALL)

    # Notes
    fx1 = P + 2*(fw4+G); fx2 = fx1 + fw4
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "NOTES", fill=DARK, font=F_SUBTITL)
    ny = FY1 + 30*S
    for note in (notes or [])[:5]:
        if ny + fh(F_SMALL) + 3*S > FY2 - 6*S:
            break
        ny = text_wrap(draw, fx1+10*S, ny, f"• {note}", F_SMALL, DARK, fx2-fx1-18*S, gap=3)

    # References
    fx1 = P + 3*(fw4+G); fx2 = W - P
    rbox(draw, (fx1, FY1, fx2, FY2), FOOT_BG, FOOT_BD, radius=12, width=2)
    draw.text((fx1+10*S, FY1+10*S), "REFERENCES", fill=DARK, font=F_SUBTITL)
    refs = ["EUCAST 2026","CLSI M100 2026","IDSA AMR 2025",
            "WHO AWaRe 2025","Egypt Nat. Guidelines","BNF 2025 | FDA Labels"]
    ry = FY1 + 30*S
    for ref in refs:
        if ry + fh(F_SMALL) + 3*S > FY2 - 6*S:
            break
        ry = text_wrap(draw, fx1+10*S, ry, f"• {ref}", F_SMALL, DARK, fx2-fx1-18*S, gap=3)

    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(200, 200), optimize=False)
    return buf.getvalue()


def generate_report(
    patient_name:    str,
    age:             int,
    sex:             str,
    weight:          float,
    cl_cr:           float,
    is_renal:        bool,
    is_preg:         bool,
    is_hepatic:      bool,
    allowed:         List[Dict],
    warned:          List[Dict],
    banned:          List[Dict],
    preg_warn_items: List[Dict],
    organism:        str,
    specimen:        str,
    interactions:    List[str],
    sir_map:         Dict[str, str],
    colony_count:    str = "",
    date_in:         str = "",
    pus_cells:       str = "",
    rbcs:            str = "",
    lab_name:              str = "Orange Lab",
    lab_city:              str = "",
    patho_assessment:      dict = None,
    show_commercial_names: bool = False,
) -> str:
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    sep  = "=" * 60
    sep2 = "-" * 60
    L:   List[str] = []

    lab_hdr = lab_name.upper() if lab_name else "ORANGE LAB"
    L += [sep, f"{lab_hdr} — CLINICAL DECISION REPORT", sep, f"Date     : {now}"]
    if patient_name:
        L.append(f"Patient  : {patient_name}")
    L.append(sep)

    L += ["\nPATIENT DETAILS", sep2,
          f"Age      : {age} years",
          f"Gender   : {sex}",
          f"Weight   : {weight} kg",
          f"Renal    : {'IMPAIRED' if is_renal else 'Normal'}"]
    if is_renal:
        L.append(f"CrCl     : {cl_cr:.1f} ml/min ({get_renal_severity(cl_cr)})")
    L.append(f"Hepatic  : {'IMPAIRED' if is_hepatic else 'Normal'}")
    if sex == "Female" and age >= 18:
        L.append(f"Pregnant : {'Yes' if is_preg else 'No'}")

    L += ["\nCULTURE & MICROSCOPY", sep2,
          f"Specimen : {specimen}"]
    if date_in:
        L.append(f"Date In  : {date_in}")
    L.append(f"Organism : {organism}")
    if colony_count:
        L.append(f"Colony   : {colony_count}")
    if pus_cells:
        L.append(f"Pus Cells: {pus_cells} /HPF")
    if rbcs:
        L.append(f"RBCs     : {rbcs} /HPF")

    if organism in ORGANISM_PROFILE:
        op = ORGANISM_PROFILE[organism]
        if op.get("note"):
            L.append(f"Note       : {op['note']}")
        spec_ctx = (op.get("specimen_context") or {}).get(specimen, "")
        if spec_ctx:
            L.append(f"Context    : {spec_ctx}")
        if op.get("first_line"):
            L.append(f"First-line : {', '.join(op['first_line'])}")
        if op.get("avoid"):
            L.append(f"Avoid      : {', '.join(op['avoid'])}")

    if sir_map:
        L += ["\nSENSITIVITY RESULTS", sep2]
        for drug, result in sorted(sir_map.items()):
            label = {"S": "Sensitive", "R": "Resistant", "I": "Intermediate"}.get(result, result)
            L.append(f"{drug:<40} {label}")

    if interactions:
        L += ["\nINTERACTIONS / WARNINGS", sep2]
        for item in sorted(set(interactions)):
            L.append(f"- {item}")

    if sir_map:
        mdr_r = classify_mdr(organism, sir_map)
        if mdr_r["level"]:
            info = MDR_INFO[mdr_r["level"]]
            L += [f"\n{info['icon']} RESISTANCE CLASSIFICATION: {info['label']}", sep2,
                  info["detail"],
                  f"Resistant ({mdr_r['resistant_count']}/{mdr_r['total_tested']}): "
                  + ", ".join(mdr_r['resistant_categories']),
                  f"Action: {info['action']}", ""]
        esbl_r = predict_esbl(organism, sir_map)
        prob   = esbl_r.get("probability")
        if prob == "carbapenemase":
            L += ["\nPOSSIBLE CARBAPENEMASE PRODUCER", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob == "high":
            L += ["\nHIGH PROBABILITY ESBL PRODUCER", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]
        elif prob == "moderate":
            L += ["\nESBL CONFIRMATION RECOMMENDED", sep2,
                  esbl_r["detail"], f"Action: {esbl_r['action']}", ""]

    L += ["\nRECOMMENDED ANTIBIOTICS", sep]
    if allowed:
        for item in allowed:
            sir_tag  = f" [Culture: {sir_map[item['name']]}]" if sir_map and item['name'] in sir_map else ""
            preg_tag = " [Pregnancy: caution]" if (is_preg and item.get("preg_status") == "Warn") else ""
            L += [f"\n{item['name']}{sir_tag}{preg_tag}", sep2,
                  f"WHO AWaRe : {item.get('aware','-')}",
                  f"Class     : {item.get('class','-')}",
                  f"Route     : {'Oral/PO-friendly' if item.get('high_po') else 'IV/IM only'}"]
            spec_note = (item.get("specimen_notes") or {}).get(specimen, "")
            if spec_note:
                L += [f"Note      : {item.get('note','')}", f"{specimen}   : {spec_note}"]
            else:
                L.append(f"Note      : {item.get('note','')}")
            if is_renal:
                L.append(f"Renal     : {item.get('renal_note','-')}")
            if is_preg and item.get("preg_status") == "Warn":
                pn = (item.get("preg_note") or "").splitlines()
                if pn:
                    L.append(f"Pregnancy : {pn[0]}")
            if show_commercial_names:
                _brands = get_commercial_name(item["name"])
                if _brands:
                    L.append(f"Brands    : {_brands}")
    else:
        L.append("No recommended options after applying all restrictions.")

    if warned:
        L += ["\nDOSE ADJUSTMENT / USE WITH CAUTION", sep]
        if is_renal:
            L.append(f"Patient CrCl = {cl_cr:.1f} ml/min\n")
        for item in warned:
            sir_tag = f" [Culture: {sir_map[item['name']]}]" if sir_map and item['name'] in sir_map else ""
            L += [f"{item['name']}{sir_tag}", sep2, f"WHO AWaRe : {item.get('aware','-')}"]
            if item.get("warning_reason") == "intermediate_culture":
                L.append("Reason    : Intermediate (I) on culture result")
            else:
                L += [f"Renal note: {item.get('renal_note','-')}",
                      f"Limit CrCl: <= {item.get('renal_limit','-')} ml/min"]
            if show_commercial_names:
                _brands = get_commercial_name(item["name"])
                if _brands:
                    L.append(f"Brands    : {_brands}")
            L.append("")

    if is_preg and preg_warn_items:
        L += ["\nPREGNANCY — USE WITH CAUTION", sep]
        for item in preg_warn_items:
            L += [item['name'], sep2]
            L.extend((item.get("preg_note") or "").splitlines())
            L.append("")

    if banned:
        L += ["\nCONTRAINDICATED / INEFFECTIVE", sep]
        grouped: Dict[str, list] = {
            "resistant": [], "renal": [], "pregnancy": [],
            "child": [], "organism": [], "other": [],
        }
        for item in banned:
            grouped.setdefault(item["category"], []).append(item)
        labels = [
            ("resistant", "[A] RESISTANT IN CULTURE"),
            ("renal",     "[B] CONTRAINDICATED — RENAL IMPAIRMENT"),
            ("pregnancy", "[C] CONTRAINDICATED — PREGNANCY"),
            ("child",     "[D] NOT SUITABLE FOR AGE"),
            ("organism",  f"[E] INEFFECTIVE FOR {organism}"),
            ("other",     "[F] OTHER CONTRAINDICATIONS"),
        ]
        for cat, heading in labels:
            if grouped.get(cat):
                L += [f"\n{heading}", sep2]
                for b in grouped[cat]:
                    L.append(f"- {b['name']} — {b['reason_short']}")
                    if cat == "renal":
                        dk       = b["name"].lower().replace(" ", "")
                        rendered = False
                        for k, v in RENAL_BAN_REASONS.items():
                            if k in dk:
                                L.extend([f"  {ln}" for ln in v.splitlines()])
                                rendered = True
                                break
                        if not rendered:
                            L.extend([f"  {ln}" for ln in (b.get("reason_detail") or "").splitlines()])
                    else:
                        L.extend([f"  {ln}" for ln in (b.get("reason_detail") or "").splitlines()])
                    L.append("")

    # ── Pathogenicity Assessment ──────────────────────────────────────
    if patho_assessment:
        sc     = patho_assessment.get("score", 0)
        verd   = patho_assessment.get("verdict", "")
        interp = patho_assessment.get("interpretation", "")
        recs   = patho_assessment.get("recommendations", [])
        flags  = patho_assessment.get("special_flags", [])
        L += ["", "PATHOGENICITY ASSESSMENT", sep2,
              f"Score    : {sc}% — {verd}"]
        if "ABU_DETECTED" in flags:
            L.append("FLAG     : Asymptomatic Bacteriuria (ABU) Detected")
        if "MW_REJECT" in flags:
            L.append("FLAG     : Murray-Washington — Specimen REJECTED")
        elif "MW_ADEQUATE" in flags:
            L.append("FLAG     : Murray-Washington — Adequate Sputum")
        if "SIRS_HIGH" in flags:
            L.append("FLAG     : SIRS >=3 criteria — Sepsis Probable")
        if interp:
            L.append(f"Interp   : {interp}")
        if recs:
            L.append("Recs     :")
            for r in recs:
                L.append(f"  • {r}")

    L += ["\nDISCLAIMER", sep,
          "هذا التقرير أداة مساعدة للقرار الطبي وليس بديلاً عن التقييم السريري.",
          "القرار النهائي للوصف العلاجي يعود للطبيب المعالج.", sep,
          "Guidelines: EUCAST 2026 | CLSI M100 2026 | IDSA AMR 2025 | Egypt National",
          "Route info: BNF 2025 | FDA Labels | WHO AWaRe 2025",
          "WHO AWaRe : Access | Watch | Reserve", sep,
          f"Developed by Dr / Hussein Ali | {lab_name}{(' | ' + lab_city) if lab_city else ''}", sep]
    return "\n".join(L)


# =========================================================
