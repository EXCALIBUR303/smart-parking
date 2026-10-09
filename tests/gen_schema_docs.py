#!/usr/bin/env python3
"""Generate the relational schema document and every ER diagram from the live
database, so none of them can drift from what is actually implemented.

Writes into docs/database/:
    RELATIONAL_SCHEMA.md           relations, foreign keys, creation order
    er/relational_schema.{png,svg} tables with their foreign-key arrows
    er/chen_legend.{png,svg}       what every shape and line means
    er/chen_overview.{png,svg}     all entities and relationships (no attributes)
    er/chen_<module>.{png,svg}     entities with their attributes, per module

Cardinality, participation and key markings are READ from the catalogue (nullable
foreign key = partial participation, UNIQUE foreign key = one-to-one). Only the
relationship verbs and the grouping into modules are written by hand below, and
the script refuses to run if a foreign key has no verb.

Needs Graphviz:  brew install graphviz
Run:  ./.venv/bin/python tests/gen_schema_docs.py     (database must be running)

Print variants for a written report (more compact, larger text, PNG only):
      ./.venv/bin/python tests/gen_schema_docs.py --print --out /some/folder
"""
import collections
import math
import os
import pathlib
import subprocess
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "database"
PRINT = "--print" in sys.argv     # compact layout with larger text, sized for a printed A4 page
OUT = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else DOCS / "er"
OUT.mkdir(parents=True, exist_ok=True)
FS = 1.35 if PRINT else 1.0        # text size factor
SC = 0.8 if PRINT else 1.0       # spacing factor for the hand-placed layouts
RS = 1.1 if PRINT else 1.0        # radius factor for the rings of attributes

# --------------------------------------------------------------------- catalogue
con = psycopg.connect(f"dbname={os.environ.get('SMARTPARK_DB', 'smartpark')}")
cur = con.cursor()

COLS = collections.defaultdict(list)           # table -> [(name, type, notnull, generated)]
for t, name, typ, nn, gen in cur.execute("""
    select c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, a.attgenerated
      from pg_attribute a join pg_class c on c.oid = a.attrelid
     where c.relnamespace = 'public'::regnamespace and c.relkind = 'r'
       and a.attnum > 0 and not a.attisdropped
     order by c.relname, a.attnum"""):
    COLS[t].append((name, typ, nn, gen))
TABLES = sorted(COLS)

PK, UK, FK = {}, collections.defaultdict(list), []
for conname, typ, child, parent, cols, pcols, dele in cur.execute("""
    select c.conname, c.contype, cl.relname, pcl.relname,
      (select array_agg(a.attname order by k.o) from unnest(c.conkey) with ordinality k(n, o)
         join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.n),
      (select array_agg(a.attname order by k.o) from unnest(c.confkey) with ordinality k(n, o)
         join pg_attribute a on a.attrelid = c.confrelid and a.attnum = k.n),
      c.confdeltype
      from pg_constraint c join pg_class cl on cl.oid = c.conrelid
      left join pg_class pcl on pcl.oid = c.confrelid
     where c.connamespace = 'public'::regnamespace and c.contype in ('p', 'f', 'u')
     order by cl.relname, c.contype, c.conname"""):
    if typ == "p":
        PK[child] = cols
    elif typ == "u":
        UK[child].append(cols)
    else:
        FK.append(dict(name=conname, child=child, parent=parent, cols=cols, pcols=pcols,
                       on_delete={"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE",
                                  "n": "SET NULL", "d": "SET DEFAULT"}[dele]))
NOTNULL = {(t, n): nn for t, cs in COLS.items() for n, _, nn, _ in cs}
for f in FK:
    f["total"] = all(NOTNULL[(f["child"], c)] for c in f["cols"])     # child must take part
    f["composite"] = len(f["cols"]) > 1
FK_COLS = collections.defaultdict(set)
for f in FK:
    FK_COLS[f["child"]].update(f["cols"])

# one entry per (child, parent) pair: a relationship in ER terms
PAIRS = collections.OrderedDict()
for f in FK:
    p = PAIRS.setdefault((f["child"], f["parent"]), dict(total=False, one_to_one=False))
    p["total"] = p["total"] or f["total"]
    if not f["composite"] and [f["cols"]] == [c for c in UK[f["child"]] if c == f["cols"]]:
        p["one_to_one"] = True

# ------------------------------------------------------------- hand-written parts
# (child, parent) -> verb phrase read from the PARENT to the CHILD
VERB = {
    ("floor", "facility"): "is divided into",       ("zone", "floor"): "contains",
    ("slot", "zone"): "contains",                   ("slot", "vehicle_type"): "is built for",
    ("vehicle", "vehicle_type"): "classifies",      ("tariff", "vehicle_type"): "is priced for",
    ("pass_type", "vehicle_type"): "is sold for",   ("tariff", "facility"): "prices",
    ("parking_pass", "facility"): "honours",        ("app_user", "facility"): "posts",
    ("customer", "app_user"): "logs in as",         ("vehicle", "customer"): "owns",
    ("reservation", "customer"): "books",           ("parking_pass", "customer"): "buys",
    ("reservation", "vehicle"): "is booked for",    ("parking_session", "vehicle"): "parks in",
    ("parking_pass", "vehicle"): "is covered by",   ("violation", "vehicle"): "commits",
    ("reservation", "slot"): "is held by",          ("parking_session", "slot"): "hosts",
    ("violation", "slot"): "is site of",            ("parking_session", "reservation"): "is fulfilled by",
    ("parking_session", "parking_pass"): "covers",  ("parking_pass", "pass_type"): "is sold as",
    ("bill", "parking_session"): "produces",        ("violation", "parking_session"): "incurs",
    ("bill", "tariff"): "prices",                   ("payment", "bill"): "is settled by",
    ("payment", "app_user"): "receives",            ("parking_session", "app_user"): "operates gate for",
    ("audit_log", "app_user"): "performs",
}
missing = [k for k in PAIRS if k not in VERB]
extra = [k for k in VERB if k not in PAIRS]
if missing or extra:
    sys.exit(f"relationship verbs out of step with the schema: missing {missing}, unused {extra}")

MODULES = [   # key, title, entities that show attributes, [context entities shown bare], pinned positions
    ("facility", "Facility structure", ["facility", "floor", "zone", "slot", "vehicle_type"], [],
     dict(facility=(0, 4), floor=(8, 4), zone=(16, 4), slot=(16, -1), vehicle_type=(8, -1))),
    ("people", "Users, customers, vehicles and audit",
     ["app_user", "customer", "vehicle", "audit_log"], ["facility", "vehicle_type"],
     dict(facility=(0, 8), app_user=(0, 1), customer=(8, 1), vehicle=(16, 1),
          vehicle_type=(16, 8), audit_log=(0, -6))),
    ("pricing", "Tariffs and passes", ["tariff", "pass_type", "parking_pass"],
     ["facility", "vehicle_type", "customer", "vehicle"],
     dict(vehicle_type=(6, -1), tariff=(0, 6.5), facility=(8, 11), parking_pass=(17, 7),
          pass_type=(12.5, -1), customer=(25, 11), vehicle=(26, 3))),
    ("sessions", "Reservations and parking sessions", ["reservation", "parking_session"],
     ["customer", "vehicle", "slot", "parking_pass", "app_user"],
     dict(reservation=(0, 0), parking_session=(13, 0), vehicle=(6.5, 7), slot=(6.5, -7),
          customer=(-10, 3), parking_pass=(19, 7), app_user=(20, -6))),
    ("billing", "Billing and violations", ["bill", "payment", "violation"],
     ["parking_session", "tariff", "app_user", "vehicle", "slot"],
     dict(parking_session=(0, 6), bill=(0, -2), tariff=(-8, -2), payment=(8, -2), app_user=(8, 6),
          violation=(-9, 6), vehicle=(-15, 10), slot=(-9, 12))),
]
GROUP_COLOR = {"facility": "#D6E6F5", "people": "#D9EBD3", "pricing": "#FBE8B8",
               "sessions": "#F9D9C6", "billing": "#F9D9C6", "audit": "#E3E3E3"}
TABLE_GROUP = {}
for key, _, ents, _, _ in MODULES:
    for e in ents:
        TABLE_GROUP[e] = key
TABLE_GROUP["audit_log"] = "audit"


def run_dot(engine, src, name, dpi=130):
    for fmt in (("png",) if PRINT else ("png", "svg")):
        args = [engine, f"-T{fmt}", "-o", str(OUT / f"{name}.{fmt}")]
        if fmt == "png":
            args.insert(1, f"-Gdpi={220 if PRINT else dpi}")
        subprocess.run(args, input=src, text=True, check=True)
    print(f"  {name}.png")


def is_fk(t, c):
    return c in FK_COLS[t]


def unique_single(t, c):
    return [c] in UK[t]


# ============================================================ relational diagram
def relational_diagram():
    """Tables as boxes, one arrow per foreign key from child to parent (parents on top).
    Which column is the foreign key is written inside the child box, so the arrows stay
    plain and readable. Dashed red arrows are composite foreign keys."""
    L = ['digraph R { rankdir=TB; nodesep=' + ('0.3' if PRINT else '0.5') + '; ranksep=' + ('0.8' if PRINT else '1.1') + '; splines=true; bgcolor=white; pad=0.4;',
         f'node [shape=plain, fontname="Helvetica", fontsize={14 * FS:g}]; edge [arrowsize=0.9];',
         'labelloc=t; fontsize=22; fontname="Helvetica-Bold"; '
         'label="SmartPark: relational schema (17 relations, arrows run from a foreign key to the table it references)";']
    fk_target = {}
    for f in FK:
        for c in f["cols"]:
            fk_target.setdefault((f["child"], c), []).append(f["parent"])
    for t in TABLES:
        rows = [f'<TR><TD COLSPAN="{2 if PRINT else 3}" BGCOLOR="{GROUP_COLOR[TABLE_GROUP[t]]}"><B>{t.upper()}</B></TD></TR>']
        for n, typ, nn, gen in COLS[t]:
            typ = typ.replace("timestamp with time zone", "timestamptz").replace("character varying", "varchar") \
                     .replace("time without time zone", "time")
            if n in PK[t]:
                nm, key = f"<U><B>{n}</B></U>", "PK"
            elif is_fk(t, n):
                targets = sorted(set(fk_target[(t, n)]))
                nm, key = f"<I>{n}</I>", "FK &#8594; " + ", ".join(targets)
            else:
                nm, key = n, ""
            if unique_single(t, n) and n not in PK[t]:
                key = (key + " " if key else "") + "UK"
            type_cell = '' if PRINT else (f'<TD ALIGN="LEFT"><FONT COLOR="#777777" POINT-SIZE="9">{typ}</FONT></TD>')
            rows.append(f'<TR><TD ALIGN="LEFT">{nm}</TD>' + type_cell +
                        f'<TD ALIGN="LEFT"><FONT COLOR="#1F4E79" POINT-SIZE="{9 * FS:g}">{key or "&#160;"}</FONT></TD></TR>')
        L.append(f'{t} [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" '
                 f'BGCOLOR="white" COLOR="#444444">{"".join(rows)}</TABLE>>];')
    drawn = set()
    for f in FK:
        if f["composite"]:
            L.append(f'{f["child"]} -> {f["parent"]} [style=dashed, color="#B03A2E", penwidth=1.4];')
        elif (f["child"], f["parent"]) not in drawn:
            drawn.add((f["child"], f["parent"]))
            L.append(f'{f["child"]} -> {f["parent"]} [color="#333333", penwidth=1.2];')
    L.append('}')
    run_dot("dot", "\n".join(L), "relational_schema", dpi=110)


# ===================================================================== Chen parts
FONT = 'fontname="Helvetica"'
ENT = f'shape=box, style=filled, fillcolor="#C9DDF2", penwidth=2, fontsize={15 * FS:g}, {FONT}, margin="0.25,0.15"'
CTX = f'shape=box, style="dashed,filled", fillcolor="#F4F4F4", penwidth=1.3, fontsize={13 * FS:g}, {FONT}, margin="0.2,0.12"'
REL = f'shape=diamond, style=filled, fillcolor="#FFE7A3", penwidth=1.5, fontsize={11 * FS:g}, {FONT}'
ATT = f'shape=ellipse, style=filled, fillcolor=white, fontsize={11 * FS:g}, {FONT}'


def attrs_of(t):
    """Attributes in Chen terms: every column that is not a foreign key (those are the
    relationships). Returns [(name, kind)] with kind in pk / unique / derived / plain."""
    out = []
    for n, _, _, gen in COLS[t]:
        if is_fk(t, n):
            continue
        if n in PK[t]:
            kind = "pk"
        elif gen:
            kind = "derived"
        elif unique_single(t, n):
            kind = "unique"
        else:
            kind = "plain"
        out.append((n, kind))
    return out


def attr_node(nid, name, kind):
    label = name
    if kind == "pk":
        return f'{nid} [{ATT}, label=<<U><B>{name}</B></U>>];'
    if kind == "unique":
        return f'{nid} [{ATT}, fillcolor="#FFF9C4", label="{label}"];'
    if kind == "derived":
        return f'{nid} [{ATT}, style="dashed,filled", label="{label}"];'
    return f'{nid} [{ATT}, label="{label}"];'


def edge_to_rel(ent, rel, card, total):
    color = '"black:white:black"' if total else "black"
    return (f'{ent} -> {rel} [dir=none, color={color}, penwidth=1.2, headlabel="", '
            f'taillabel="{card}", labeldistance=2.2, labelfontsize={13 * FS:g}, fontname="Helvetica-Bold", '
            f'labelfontname="Helvetica-Bold", len=2.3];')


def place_attrs(center, k, occupied, margin=24.0, radii=(2.35 * RS, 3.35 * RS)):
    """Positions for k attribute ellipses around `center`, spread over the angular gaps
    between the entity's relationship lines (so no attribute sits on a line).
    Alternating radii stagger neighbours so wide labels do not collide."""
    occ = sorted(a % 360 for a in occupied)
    arcs = []
    if not occ:
        arcs = [(0.0, 360.0)]
    else:
        for i, a in enumerate(occ):
            b = occ[(i + 1) % len(occ)] + (360 if i == len(occ) - 1 else 0)
            lo, hi = a + margin, b - margin
            if hi > lo:
                arcs.append((lo, hi))
    total = sum(hi - lo for lo, hi in arcs) or 1.0
    out = []
    for j in range(k):
        t = (j + 0.5) * total / k
        for lo, hi in arcs:
            if t <= hi - lo:
                ang = lo + t
                break
            t -= hi - lo
        else:
            ang = arcs[-1][1]
        r = radii[j % 2] if k > 5 else radii[0]
        out.append((center[0] + r * math.cos(math.radians(ang)), center[1] + r * math.sin(math.radians(ang))))
    return out


def chen(title, ents_with_attrs, ctx, pairs, name, pos=None, engine="neato", with_attrs=True):
    L = ['graph G { ', f'layout={engine}; overlap=true; splines=line; pad=0.4; bgcolor=white; '
         'outputorder=edgesfirst;',
         f'labelloc=t; fontsize=20; fontname="Helvetica-Bold"; label="{title}";']
    if pos:
        pos = {k: (v[0] * SC, v[1] * SC) for k, v in pos.items()}
    shown = set(ents_with_attrs) | set(ctx)
    pin = lambda t: f', pos="{pos[t][0]},{pos[t][1]}!"' if pos and t in pos else ""
    for t in ents_with_attrs:
        L.append(f'{t} [{ENT}, label="{t.upper()}"{pin(t)}];')
    for t in ctx:
        L.append(f'{t} [{CTX}, label="{t.upper()}"{pin(t)}];')
    if with_attrs:
        for t in ents_with_attrs:
            occupied = []
            for child, parent in pairs:
                other = parent if child == t else child if parent == t else None
                if other and pos and other in pos:
                    occupied.append(math.degrees(math.atan2(pos[other][1] - pos[t][1],
                                                            pos[other][0] - pos[t][0])))
            # also steer clear of every other box on the page, related or not
            for other, xy in (pos or {}).items():
                if other != t:
                    occupied.append(math.degrees(math.atan2(xy[1] - pos[t][1], xy[0] - pos[t][0])))
            attrs = attrs_of(t)
            spots = place_attrs(pos[t], len(attrs), occupied)
            for (n, kind), (x, y) in zip(attrs, spots):
                nid = f"a_{t}_{n}"
                L.append(attr_node(nid, n, kind).replace("];", f', pos="{x:.2f},{y:.2f}!"];'))
                L.append(f'{t} -- {nid} [color="#555555"];')
    for child, parent in pairs:
        info = PAIRS[(child, parent)]
        rid = f"r_{child}_{parent}"
        verb = VERB[(child, parent)].replace(" ", "\\n", 1) if len(VERB[(child, parent)]) > 9 else VERB[(child, parent)]
        mid = ""
        if pos and child in pos and parent in pos:       # both ends placed by hand: sit halfway
            mid = f', pos="{(pos[child][0] + pos[parent][0]) / 2},{(pos[child][1] + pos[parent][1]) / 2}!"'
        L.append(f'{rid} [{REL}, label="{verb}"{mid}];')
        pcard, ccard = ("1", "1") if info["one_to_one"] else ("1", "N")
        L.append(f'{parent} -- {rid} [color="black", penwidth=1.2, taillabel="{pcard}", labeldistance=2.4, '
                 f'labelfontsize={13 * FS:g}, labelfontname="Helvetica-Bold", len=2.1];')
        cc = '"black:white:black"' if info["total"] else "black"
        L.append(f'{rid} -- {child} [color={cc}, penwidth=1.2, headlabel="{ccard}", labeldistance=2.4, '
                 f'labelfontsize={13 * FS:g}, labelfontname="Helvetica-Bold", len=2.1];')
    L.append('}')
    run_dot(engine, "\n".join(L), name)


def overview():
    L = [f'digraph G {{ rankdir=TB; nodesep={0.3 if PRINT else 0.45}; ranksep={0.4 if PRINT else 0.55}; splines=true; pad=0.4; bgcolor=white;',
         'labelloc=t; fontsize=20; fontname="Helvetica-Bold"; '
         'label="ER diagram: all 17 entities and 31 relationships (their attributes are on the module diagrams)";']
    for t in TABLES:
        L.append(f'{t} [{ENT}, label="{t.upper()}"];')
    for (child, parent), info in PAIRS.items():
        rid = f"r_{child}_{parent}"
        v = VERB[(child, parent)]
        v = v.replace(" ", "\\n", 1) if len(v) > 9 else v
        L.append(f'{rid} [{REL}, label="{v}"];')
        pcard, ccard = ("1", "1") if info["one_to_one"] else ("1", "N")
        L.append(f'{parent} -> {rid} [dir=none, color=black, penwidth=1.2, taillabel="{pcard}", '
                 f'labeldistance=1.6, labelfontsize={12 * FS:g}, labelfontname="Helvetica-Bold"];')
        cc = '"black:white:black"' if info["total"] else "black"
        L.append(f'{rid} -> {child} [dir=none, color={cc}, penwidth=1.2, headlabel="{ccard}", '
                 f'labeldistance=1.6, labelfontsize={12 * FS:g}, labelfontname="Helvetica-Bold"];')
    L.append('}')
    run_dot("dot", "\n".join(L), "chen_overview")


def chen_pairs(ents):
    return [k for k in PAIRS if k[0] in ents and k[1] in ents]


def chen_diagrams():
    for key, title, ents, ctx, pos in MODULES:
        pairs = [k for k in PAIRS if (k[0] in ents or k[1] in ents) and k[0] in set(ents) | set(ctx)
                 and k[1] in set(ents) | set(ctx)]
        chen(f"ER diagram: {title}", ents, ctx, pairs, f"chen_{key}", pos=pos)
    overview()


# =================================================================== legend
def legend():
    """Every shape and line used in the ER diagrams, with its meaning next to it."""
    L = ['graph L { layout=neato; overlap=true; pad=0.5; bgcolor=white; splines=line;',
         'labelloc=t; fontsize=22; fontname="Helvetica-Bold"; '
         'label="How to read the ER diagrams (Chen notation)";',
         f'node [{FONT}]; edge [fontname="Helvetica"];']
    n = [0]

    def text(x, y, msg):
        """Text starts 1.1in to the right of its symbol; width estimated from the longest line."""
        n[0] += 1
        w = max(len(line) for line in msg.split("\\n")) * 0.082
        L.append(f't{n[0]} [shape=plaintext, fontsize=13, label="{msg}", pos="{x + 1.1 + w / 2:.2f},{y}!"];')

    def node(nid, style, label, x, y):
        L.append(f'{nid} [{style}, label={label}, pos="{x},{y}!"];')

    def pair(nid, x, y, double=False):
        L.append(f'{nid}a [{ENT}, label="A", pos="{x - 0.6},{y}!"]; {nid}b [{ENT}, label="B", pos="{x + 0.9},{y}!"];')
        c = '"black:white:black"' if double else "black"
        L.append(f'{nid}a -- {nid}b [color={c}, penwidth=1.2];')

    LX, RX = (0, 0) if PRINT else (0, 11.4)
    RY = -7.8 if PRINT else 0          # the right-hand items sit below the left-hand ones when printing
    node("e1", ENT, '"ENTITY"', LX, 7.4)
    text(LX, 7.4, "Rectangle: an entity, a thing we keep records of.\\nIt becomes a table.")
    node("e2", CTX, '"ENTITY"', LX, 6.1)
    text(LX, 6.1, "Dashed rectangle: an entity drawn only for context.\\nIts attributes are on another diagram.")
    node("a1", ATT, '"attribute"', LX, 4.8)
    text(LX, 4.8, "Ellipse: an attribute (a column) of the entity it is joined to.")
    node("a2", ATT, "<<U><B>primary_key</B></U>>", LX, 3.5)
    text(LX, 3.5, "Underlined ellipse: the primary key. It identifies each row.")
    node("a3", ATT + ', fillcolor="#FFF9C4"', '"unique_key"', LX, 2.2)
    text(LX, 2.2, "Yellow ellipse: a UNIQUE attribute (candidate key).\\nNo two rows may hold the same value.")
    node("a4", ATT + ', style="dashed,filled"', '"derived"', LX, 0.9)
    text(LX, 0.9, "Dashed ellipse: a derived attribute, computed from others\\n(total_amount = base_amount + tax_amount).")

    node("r1", REL, '"relationship"', RX, 7.4 + RY)
    text(RX + 0.4, 7.4 + RY, "Diamond: a relationship between two entities (a foreign key).\\nRead it as a sentence: PARENT verb CHILD.")
    L.append(f'p1 [{ENT}, label="PARENT", pos="{RX - 0.3},{6.1 + RY}!"]; c1 [{ENT}, label="CHILD", pos="{RX + 1.9},{6.1 + RY}!"];')
    L.append('p1 -- c1 [color=black, penwidth=1.2, taillabel="1", headlabel="N", labeldistance=2.2, '
             'labelfontsize=14, labelfontname="Helvetica-Bold"];')
    text(RX + 2.9, 6.1 + RY, "1 and N: cardinality. One PARENT has many CHILDREN.\\n1 on both ends means one-to-one.")
    pair("s1", RX, 4.8 + RY)
    text(RX + 1.3, 4.8 + RY, "Single line: partial participation. A row may exist without\\ntaking part (the foreign key may be NULL).")
    pair("s2", RX, 3.5 + RY, double=True)
    text(RX + 1.3, 3.5 + RY, "Double line: total participation. Every row must take part\\n(the foreign key is NOT NULL).")
    L.append(f'note [shape=plaintext, fontsize=12, label="Foreign-key columns are not drawn as attributes: the relationship diamond is the foreign key.\\n'
             f'Not used here: weak entities (double rectangle) and multivalued attributes (double ellipse). Every entity has its own\\n'
             f'primary key, and repeating groups such as payments were moved into their own entity during normalization.", '
             f'pos="{RX + 1.5},{1.5 + RY}!"];')
    L.append('}')
    src = "\n".join(L)
    for fmt in (("png",) if PRINT else ("png", "svg")):
        args = ["neato", f"-T{fmt}", "-o", str(OUT / f"chen_legend.{fmt}")]
        if fmt == "png":
            args.insert(1, f"-Gdpi={220 if PRINT else 130}")
        subprocess.run(args, input=src, text=True, check=True)
    print("  er/chen_legend.png")


# ================================================================ markdown
def creation_order():
    deps = {t: {f["parent"] for f in FK if f["child"] == t and f["parent"] != t} for t in TABLES}
    level, done = {}, set()
    while len(done) < len(TABLES):
        ready = [t for t in TABLES if t not in done and deps[t] <= done]
        if not ready:
            sys.exit("foreign-key cycle")
        for t in ready:
            level[t] = 1 + max([level[d] for d in deps[t]] or [0])
        done.update(ready)
    return level


def relation_line(t):
    parts = []
    for n, _, _, _ in COLS[t]:
        s = n
        if n in PK[t]:
            s = f"<ins>**{n}**</ins>"
        elif is_fk(t, n):
            s = f"*{n}*"
        if unique_single(t, n) and n not in PK[t]:
            s += "&nbsp;<sup>UK</sup>"
        parts.append(s)
    return f"**{t.upper()}** ( {', '.join(parts)} )"


def write_markdown():
    level = creation_order()
    md = []
    w = md.append
    w("# Relational Schema\n")
    w("Smart Parking Lot Allocation & Billing System: DBMS PBL Project 20.\n")
    w("Generated from the live PostgreSQL catalogue by `tests/gen_schema_docs.py`, so it "
      "describes the implemented database exactly. The same schema in executable form is "
      "[`db/schema_snapshot.sql`](../../db/schema_snapshot.sql); the migrations in "
      "[`db/migrations/`](../../db/migrations/) are the source of truth.\n")
    w("## 1. How to read it\n")
    w("| Marking | Meaning |\n|---|---|\n"
      "| <ins>**underlined bold**</ins> | primary key |\n"
      "| *italic* | foreign key (the table it points to is listed in section 3) |\n"
      "| <sup>UK</sup> | UNIQUE column (a candidate key) |\n")
    w("## 2. The 17 relations\n")
    for t in TABLES:
        w(f"{relation_line(t)}\n")
    w("![Relational schema](er/relational_schema.png)\n")
    w("*Each box is a relation; each arrow runs from a foreign key to the primary key it "
      "references. Dashed red arrows are composite foreign keys, which make the database refuse a "
      "car in a bike bay and a booking on someone else's vehicle. "
      "[SVG version](er/relational_schema.svg) for zooming.*\n")
    w("## 3. Foreign keys\n")
    w("| # | Child table | Foreign key | Parent table | Parent key | Required? | ON DELETE |\n"
      "|--:|---|---|---|---|---|---|")
    for i, f in enumerate(FK, 1):
        w(f"| {i} | `{f['child']}` | `{', '.join(f['cols'])}` | `{f['parent']}` | "
          f"`{', '.join(f['pcols'])}` | {'yes' if f['total'] else 'no (nullable)'} | {f['on_delete']} |")
    w("")
    w("`RESTRICT` and `NO ACTION` refuse to delete a parent that still has children; `CASCADE` "
      "deletes the children with it; `SET NULL` keeps them and clears the link. Each choice is "
      "explained in the comments of `db/migrations/002` to `004`.\n")
    w("## 4. Candidate keys (UNIQUE constraints)\n")
    w("| Table | Primary key | Other unique keys |\n|---|---|---|")
    for t in TABLES:
        others = ", ".join(f"`({', '.join(u)})`" if len(u) > 1 else f"`{u[0]}`" for u in UK[t]
                           if u != PK[t]) or "none"
        w(f"| `{t}` | `{', '.join(PK[t])}` | {others} |")
    w("\nThe composite unique keys such as `(slot_id, vehicle_type_id)` exist so that other tables "
      "can point at them with composite foreign keys.\n")
    w("## 5. Order the tables must be created in\n")
    w("A table can only be created after every table its foreign keys point to. That gives these "
      "levels (the migrations follow this order):\n")
    w("| Level | Tables |\n|--:|---|")
    for lv in sorted(set(level.values())):
        w(f"| {lv} | {', '.join('`' + t + '`' for t in TABLES if level[t] == lv)} |")
    w("")
    w("## 6. See also\n")
    w("- [ER_DIAGRAM.md](ER_DIAGRAM.md): the entity-relationship diagrams, in Chen notation with a legend\n"
      "- [NORMALIZATION.md](NORMALIZATION.md): functional dependencies and the 1NF to 3NF derivation\n"
      "- [DATA_DICTIONARY.md](DATA_DICTIONARY.md): every column, type and constraint\n")
    (DOCS / "RELATIONAL_SCHEMA.md").write_text("\n".join(md))
    print("  RELATIONAL_SCHEMA.md")


if __name__ == "__main__":
    print("Writing schema documents and diagrams:")
    relational_diagram()
    legend()
    chen_diagrams()
    if not PRINT:
        write_markdown()
