#!/usr/bin/env python3
"""
apply_brand.py — Reusable brand re-skinning engine for eaef-multiprocedure-eater
dashboard exports.

WHY THIS EXISTS
----------------
The eaef-multiprocedure-eater pipeline generates fully server-rendered,
self-contained dashboard HTML files (one per client, per domain). The data,
markup structure, and JavaScript are already correct for the client — only
the *visual design tokens* (colors, fonts) need to change to match a new
client's brand. Rather than hand-editing four (or forty) generated HTML
files, this script mechanically re-skins any dashboard export by swapping
its color palette and font stack for values defined in a brand config file.

This is the reusable piece of the "template vs. data vs. brand" separation:
  - STRUCTURE + DATA  -> baked into the dashboard HTML by eaef-multiprocedure-eater
  - BRAND (this file)  -> a small JSON config swapped in per client
  - OUTPUT            -> client-branded dashboard, byte-identical in structure

USAGE
-----
    python3 apply_brand.py --brand brands/chanel.json --in SRC.html --out DEST.html
    python3 apply_brand.py --brand brands/chanel.json --in-dir SRC_DIR --out-dir DEST_DIR

For a NEW CLIENT: copy brands/chanel.json to brands/<client>.json, replace
the hex values with the new brand's palette (see the "how to extract a
palette" note in brands/chanel.json), and re-run against that client's
dashboard exports. No HTML/CSS/JS editing required.
"""
import argparse
import json
import os
import re
import sys

# The exact literal strings the eaef-multiprocedure-eater dashboard template
# uses for its default (IBM Carbon dark) palette. Every brand config below
# must supply a replacement for each key. Order matters: longer/more-specific
# patterns are replaced first so we never partially clobber a shorter one.
DEFAULT_PALETTE = {
    # surfaces
    "bg":      "#161616",
    "l01":     "#262626",
    "l02":     "#393939",
    "l03":     "#525252",
    "lh":      "#333333",
    "bs":      "#393939",   # same literal as l02, handled via combined pass
    "bst":     "#525252",   # same literal as l03
    # text
    "tp":      "#f4f4f4",
    "ts":      "#c6c6c6",
    "tpl":     "#6f6f6f",
    # accents (hex form, as they appear in :root)
    "blue":    "#4589ff",
    "teal":    "#08bdba",
    "purple":  "#a56eff",
    "green":   "#42be65",
    "warn":    "#f1c21b",
    "err":     "#fa4d56",
    "cyan":    "#33b1ff",
    "mag":     "#ee5396",
}

# RGB triplets used in literal rgba(...) calls throughout the stylesheet
# (chip backgrounds, badge borders, highlight tints). Must match the hex
# accents above 1:1.
DEFAULT_RGB = {
    "blue":   "69,137,255",
    "teal":   "8,189,186",
    "purple": "165,110,255",
    "green":  "66,190,101",
    "warn":   "241,194,27",
    "err":    "250,77,86",
    "cyan":   "51,177,255",
    "mag":    "238,83,150",
}

FONT_LINK_RE = re.compile(
    r'<link rel="preconnect" href="https://fonts\.googleapis\.com">\s*'
    r'<link href="https://fonts\.googleapis\.com/css2\?family=[^"]*" rel="stylesheet">',
    re.MULTILINE,
)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def load_brand(path):
    with open(path) as f:
        brand = json.load(f)
    if "font_sans" not in brand or "font_mono" not in brand:
        raise ValueError(f"{path}: brand config must include font_sans and font_mono")
    required_palette_keys = list(DEFAULT_PALETTE) + ["hero_gradient", "ink_on_accent"]
    absent = [k for k in required_palette_keys if k not in brand.get("palette", {})]
    if absent:
        raise ValueError(f"{path}: palette missing keys: {absent}")
    return brand


def apply_brand(html, brand):
    palette = brand["palette"]

    # NOTE ON ORDERING: the source template reuses the literal #161616 for
    # THREE distinct roles - (a) the --bg variable, (b) the hardcoded hero
    # gradient's outer stops, and (c) "dark ink text for contrast on a
    # light/bright fill" (funnel-segment labels, bar-fill labels, and a JS
    # ternary in the heatmap renderer). In a light brand theme (b) still
    # wants to stay light and (c) still wants to stay dark ink - they must
    # NOT both collapse to the new --bg value. So every role-(b)/(c) literal
    # is replaced FIRST (most-specific pattern first), and only the bare
    # remaining #161616 (the actual --bg declaration) is swapped last.

    # 1. Hero gradient (hardcoded, references #161616 twice + #0d1b2e once)
    html = html.replace(
        "linear-gradient(135deg,#161616 0%,#0d1b2e 55%,#161616 100%)",
        palette["hero_gradient"],
    )

    # 2. "Ink on accent" literal text-color uses of #161616 (CSS + inline JS
    #    string form used when building SVG markup)
    html = html.replace("color:#161616", f"color:{palette['ink_on_accent']}")
    html = html.replace("'#161616'", f"'{palette['ink_on_accent']}'")

    # 3. Hex color substitutions (:root block; by this point the only
    #    remaining bare #161616 is the actual --bg declaration)
    hex_pairs = [
        (DEFAULT_PALETTE["bg"], palette["bg"]),
        (DEFAULT_PALETTE["l01"], palette["l01"]),
        (DEFAULT_PALETTE["l02"], palette["l02"]),
        (DEFAULT_PALETTE["l03"], palette["l03"]),
        (DEFAULT_PALETTE["lh"], palette["lh"]),
        (DEFAULT_PALETTE["tp"], palette["tp"]),
        (DEFAULT_PALETTE["ts"], palette["ts"]),
        (DEFAULT_PALETTE["tpl"], palette["tpl"]),
        (DEFAULT_PALETTE["blue"], palette["blue"]),
        (DEFAULT_PALETTE["teal"], palette["teal"]),
        (DEFAULT_PALETTE["purple"], palette["purple"]),
        (DEFAULT_PALETTE["green"], palette["green"]),
        (DEFAULT_PALETTE["warn"], palette["warn"]),
        (DEFAULT_PALETTE["err"], palette["err"]),
        (DEFAULT_PALETTE["cyan"], palette["cyan"]),
        (DEFAULT_PALETTE["mag"], palette["mag"]),
    ]
    for old, new in hex_pairs:
        html = html.replace(old, new)

    # 4. rgba(...) triplets (chip/badge tints & borders)
    for key, old_rgb in DEFAULT_RGB.items():
        new_rgb = hex_to_rgb(palette[key])
        html = html.replace(f"rgba({old_rgb}", f"rgba({new_rgb}")

    # 5. Fonts: drop the Google Fonts <link> pair and swap font-family refs
    #    (both the CSS quoted form and the unquoted form used inside
    #    JS-generated SVG text attributes)
    html = FONT_LINK_RE.sub(brand.get("font_link_html", ""), html)
    html = html.replace("'IBM Plex Mono',monospace", brand["font_mono"])
    html = html.replace("'IBM Plex Sans',sans-serif", brand["font_sans"])
    svg_font = brand["font_mono"].replace("'", "")
    html = html.replace("IBM Plex Mono,monospace", svg_font)

    # 6. Branding text swaps (logo lockup, etc.) — optional, only if present
    for old, new in brand.get("text_replacements", {}).items():
        html = html.replace(old, new)

    return html


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True, help="Path to brand config JSON")
    ap.add_argument("--in", dest="infile", help="Single input HTML file")
    ap.add_argument("--out", dest="outfile", help="Single output HTML file")
    ap.add_argument("--in-dir", dest="indir", help="Directory of input HTML files")
    ap.add_argument("--out-dir", dest="outdir", help="Directory to write branded HTML files")
    args = ap.parse_args()

    brand = load_brand(args.brand)

    if args.infile:
        with open(args.infile, encoding="utf-8") as f:
            html = f.read()
        branded = apply_brand(html, brand)
        os.makedirs(os.path.dirname(args.outfile) or ".", exist_ok=True)
        with open(args.outfile, "w", encoding="utf-8") as f:
            f.write(branded)
        print(f"wrote {args.outfile}")
    elif args.indir:
        os.makedirs(args.outdir, exist_ok=True)
        for name in sorted(os.listdir(args.indir)):
            if not name.endswith(".html"):
                continue
            with open(os.path.join(args.indir, name), encoding="utf-8") as f:
                html = f.read()
            branded = apply_brand(html, brand)
            outpath = os.path.join(args.outdir, name)
            with open(outpath, "w", encoding="utf-8") as f:
                f.write(branded)
            print(f"wrote {outpath}")
    else:
        print("must supply --in/--out or --in-dir/--out-dir", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
