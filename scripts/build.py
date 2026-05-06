"""
Preprocesador de datos del Libro de Balances y Cuentas (DGSFP).

Lee los CSV originales en data/raw/ y produce data/dgsfp.json,
con todas las partidas desplegadas y agregaciones útiles para la web.

Estructura de salida:
    {
      meta: { fuente, years, n },
      lit: { act, pas, nv, vi, nt, sol },     # listas de literales por categoría
      ent: [ {clave, nombre, provincia, ambito, years} ],
      d: { CLAVE: { k, a, p, nv, vi, nt, s } } # k=KPIs cabecera, a=activo, p=pasivo, ...
    }

Uso:
    python scripts/build.py
"""
import csv, json, re, os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW  = ROOT / 'data' / 'raw'
OUT  = ROOT / 'data' / 'dgsfp.json'


def read_csv(name, encoding='cp1252'):
    with open(RAW / name, 'r', encoding=encoding, newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))

def try_read(name):
    for enc in ('cp1252', 'utf-8-sig', 'utf-8'):
        try:
            return read_csv(name, enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"No pude leer {name}")

def to_num(v):
    if v is None: return None
    s = str(v).strip().replace('.', '').replace(',', '.')
    if s in ('', 'NULL', 'null'): return None
    try:
        x = float(s)
        return int(x) if x.is_integer() else round(x, 2)
    except ValueError:
        return None

def clean(s): return re.sub(r'\s+', ' ', (s or '').strip())
def yr(t):
    m = re.search(r'(\d{4})', t or '')
    return int(m.group(1)) if m else None


# ---- AUXILIARES ----------------------------------------------------------
provincias = {r['CLAVE'].strip(): clean(r['NOMBRE']) for r in try_read('Provincias.csv')}
ambitos    = {r['Codigo'].strip(): clean(r['Descripcion']) for r in try_read('AuxAmbitos.csv')}


# ---- LITERALES -----------------------------------------------------------
def load_lit(fname):
    out = {}
    for r in try_read(fname):
        c = (r.get('COL1') or '').strip()
        d = clean(r.get('DESCRIPCION', ''))
        if c.startswith('PT') and d:
            out[c] = d
    return out

L_ACT = load_lit('L0301t.csv')
L_PAS = load_lit('L0302t.csv')
L_NV  = load_lit('L0401t.csv')
L_VI  = load_lit('L0402t.csv')
L_NT  = load_lit('L0403t.csv')

PTS_ACT = sorted(L_ACT.keys(), key=lambda s: int(s[2:]))
PTS_PAS = sorted(L_PAS.keys(), key=lambda s: int(s[2:]))
PTS_NV  = sorted(L_NV.keys(),  key=lambda s: int(s[2:]))
PTS_VI  = sorted(L_VI.keys(),  key=lambda s: int(s[2:]))
PTS_NT  = sorted(L_NT.keys(),  key=lambda s: int(s[2:]))

def order_lits(d):
    return [{'pt': k, 'label': d[k]} for k in sorted(d.keys(), key=lambda s: int(s[2:]))]


# ---- SOLVENCIA: literales y celdas (8 indicadores × hasta 5 niveles) ------
def load_sol_lit():
    out = []
    for r in try_read('LS230101_01t.csv'):
        out.append({
            'desc': clean(r['DESCRIPCION']),
            'cells': {
                'total': (r.get('total') or '').strip(),
                'n1_nr': (r.get('Nivel 1 No restringido') or '').strip(),
                'n1_r':  (r.get('Nivel 1 Restringido')   or '').strip(),
                'n2':    (r.get('Nivel 2') or '').strip(),
                'n3':    (r.get('Nivel 3') or '').strip(),
            }
        })
    return out

SOL_LITS = load_sol_lit()
SOL_CELLS = []
NIVEL_LABELS = [
    ('total', None), ('n1_nr', 'Nivel 1 No restringido'),
    ('n1_r',  'Nivel 1 Restringido'),
    ('n2', 'Nivel 2'), ('n3', 'Nivel 3'),
]
for i, lit in enumerate(SOL_LITS):
    is_ratio = 'Ratio' in lit['desc']
    for nivel_key, nivel_label in NIVEL_LABELS:
        code = lit['cells'].get(nivel_key)
        if code:
            desc = lit['desc'] if nivel_label is None else f"{lit['desc']} — {nivel_label}"
            SOL_CELLS.append({
                'id': f"s{i}_{nivel_key}",
                'desc': desc, 'code': code,
                'is_ratio': is_ratio,
                'level': nivel_label,
                'indicator': lit['desc'],
            })


# ---- IDENTIFICACIÓN ------------------------------------------------------
ent = {}
for r in try_read('D0101t.csv'):
    clave = r['CLAVE'].strip()
    y = yr(r['TRIMESTRE'])
    if not clave or not y: continue
    e = ent.setdefault(clave, {'clave': clave, 'years': []})
    e['nombre']    = clean(r['NOMBRE'])
    e['provincia'] = provincias.get(r['PROVINCIA'].strip(), '')
    e['ambito']    = ambitos.get(r['AMBITO'].strip(), '')
    if y not in e['years']: e['years'].append(y)
for e in ent.values(): e['years'].sort()


# ---- EMPLEADOS -----------------------------------------------------------
emp = defaultdict(dict)
for r in try_read('D0104T.csv'):
    clave = r['CLAVE'].strip(); y = yr(r['TRIMESTRE'])
    if not clave or not y: continue
    emp[clave][str(y)] = {
        't': to_num(r.get('N_EMP_CIERRE')),
        'm': to_num(r.get('N_MUJERES')),
        'h': to_num(r.get('N_HOMBRES')),
    }


# ---- BALANCE (vectores completos) ----------------------------------------
def load_balance(fname, pts):
    by = defaultdict(dict)
    for r in try_read(fname):
        clave = r['CLAVE'].strip(); y = yr(r['TRIMESTRE'])
        if not clave or not y: continue
        vec = [to_num(r.get(pt)) for pt in pts]
        if any(v is not None for v in vec):
            by[clave][str(y)] = vec
    return by

act = load_balance('D0301T.csv', PTS_ACT)
pas = load_balance('D0302t.csv', PTS_PAS)


# ---- PYG (vectores completos, agregados por entidad-año, op=1) -----------
def load_pyg_full(fname, pts, op_filter='1'):
    by = defaultdict(dict)
    has = defaultdict(lambda: defaultdict(set))
    for r in try_read(fname):
        clave = r['CLAVE'].strip(); y = yr(r['TRIMESTRE'])
        if not clave or not y: continue
        op = (r.get('operacion') or '').strip()
        if op_filter and op != op_filter: continue
        ystr = str(y)
        vec = by[clave].setdefault(ystr, [None] * len(pts))
        for i, pt in enumerate(pts):
            v = to_num(r.get(pt))
            if v is not None:
                vec[i] = (vec[i] or 0) + v
                has[clave][ystr].add(i)
    for c in by:
        for y in by[c]:
            v = by[c][y]
            for i in range(len(v)):
                if i not in has[c][y]:
                    v[i] = None
                elif v[i] is not None:
                    v[i] = int(v[i]) if v[i] == int(v[i]) else round(v[i], 2)
    return by

pyg_nv = load_pyg_full('D0401T.csv', PTS_NV, '1')
pyg_vi = load_pyg_full('D0402t.csv', PTS_VI, '1')
pyg_nt = load_pyg_full('D0403T.csv', PTS_NT, '1')


# ---- SOLVENCIA ------------------------------------------------------------
sol = defaultdict(dict)
for r in try_read('DS230101_01t.csv'):
    clave = (r.get('Clave') or '').strip(); y = yr(r.get('Periodo') or '')
    if not clave or not y: continue
    rec = {}
    for cell in SOL_CELLS:
        v = to_num(r.get(cell['code']))
        if v is not None: rec[cell['id']] = v
    if rec: sol[clave][str(y)] = rec


# ---- KPIs CABECERA --------------------------------------------------------
def idx(pts, pt):
    return pts.index(pt) if pt in pts else None

I = {
    'act_tot':  idx(PTS_ACT, 'PT62'),
    'pas_tot':  idx(PTS_PAS, 'PT45'),
    'pn_tot':   idx(PTS_PAS, 'PT70'),
    'res_ej':   idx(PTS_PAS, 'PT60'),
    'nv_prim':  idx(PTS_NV, 'PT8'),
    'nv_sin':   idx(PTS_NV, 'PT26'),
    'nv_gas':   idx(PTS_NV, 'PT34'),
    'nv_res':   idx(PTS_NV, 'PT49'),
    'vi_prim':  idx(PTS_VI, 'PT8'),
    'vi_sin':   idx(PTS_VI, 'PT27'),
    'vi_gas':   idx(PTS_VI, 'PT40'),
    'vi_res':   idx(PTS_VI, 'PT54'),
    'nt_rnv':   idx(PTS_NT, 'PT1'),
    'nt_rvi':   idx(PTS_NT, 'PT2'),
    'nt_rnt':   idx(PTS_NT, 'PT31'),
    'nt_ai':    idx(PTS_NT, 'PT32'),
    'nt_rej':   idx(PTS_NT, 'PT25'),
}

SOL_HEAD_CELL = {
    'cso':    'R0580C0010',
    'cmo':    'R0600C0010',
    'fp_cso': 'R0540C0010',
    'fp_cmo': 'R0550C0010',
    'r_cso':  'R0620C0010',
    'r_cmo':  'R0640C0010',
}
SOL_HEAD = {short: next(c['id'] for c in SOL_CELLS if c['code'] == code)
            for short, code in SOL_HEAD_CELL.items()}


def build_kpi(clave):
    out = {}
    yrs = set()
    for src in (act, pas, pyg_nv, pyg_vi, pyg_nt, emp, sol):
        if clave in src: yrs.update(src[clave].keys())
    for y in yrs:
        rec = {}
        if clave in emp and y in emp[clave]:
            e = emp[clave][y]
            rec.update({'emp_t': e['t'], 'emp_m': e['m'], 'emp_h': e['h']})
        if clave in act and y in act[clave] and I['act_tot'] is not None:
            rec['activo'] = act[clave][y][I['act_tot']]
        if clave in pas and y in pas[clave]:
            v = pas[clave][y]
            for k, ix in [('pasivo','pas_tot'), ('pn','pn_tot'), ('res_ej_pn','res_ej')]:
                if I[ix] is not None: rec[k] = v[I[ix]]
        if clave in pyg_nv and y in pyg_nv[clave]:
            v = pyg_nv[clave][y]
            for k, ix in [('primas_nv','nv_prim'), ('siniestralidad_nv','nv_sin'),
                          ('gastos_expl_nv','nv_gas'), ('res_tec_nv','nv_res')]:
                if I[ix] is not None: rec[k] = v[I[ix]]
        if clave in pyg_vi and y in pyg_vi[clave]:
            v = pyg_vi[clave][y]
            for k, ix in [('primas_vi','vi_prim'), ('siniestralidad_vi','vi_sin'),
                          ('gastos_expl_vi','vi_gas'), ('res_tec_vi','vi_res')]:
                if I[ix] is not None: rec[k] = v[I[ix]]
        if clave in pyg_nt and y in pyg_nt[clave]:
            v = pyg_nt[clave][y]
            for k, ix in [('res_no_vida','nt_rnv'), ('res_vida','nt_rvi'),
                          ('res_no_tec','nt_rnt'), ('res_antes_imp','nt_ai'),
                          ('res_ejercicio','nt_rej')]:
                if I[ix] is not None: rec[k] = v[I[ix]]
        if clave in sol and y in sol[clave]:
            sv = sol[clave][y]
            for short, long_id in SOL_HEAD.items():
                if long_id in sv: rec[short] = sv[long_id]
        rec = {k: v for k, v in rec.items() if v is not None}
        if rec: out[y] = rec
    return out


# ---- ENSAMBLAJE ----------------------------------------------------------
data = {}
for clave in ent:
    rec = {}
    k = build_kpi(clave)
    if k:               rec['k']  = k
    if clave in act:    rec['a']  = act[clave]
    if clave in pas:    rec['p']  = pas[clave]
    if clave in pyg_nv: rec['nv'] = pyg_nv[clave]
    if clave in pyg_vi: rec['vi'] = pyg_vi[clave]
    if clave in pyg_nt: rec['nt'] = pyg_nt[clave]
    if clave in sol:    rec['s']  = sol[clave]
    data[clave] = rec

dataset = {
    'meta': {
        'fuente': 'DGSFP — Libro de Balances y Cuentas',
        'years': sorted({y for e in ent.values() for y in e['years']}),
        'n': len(ent),
    },
    'lit': {
        'act': order_lits(L_ACT),
        'pas': order_lits(L_PAS),
        'nv':  order_lits(L_NV),
        'vi':  order_lits(L_VI),
        'nt':  order_lits(L_NT),
        'sol': SOL_CELLS,
    },
    'ent': sorted(ent.values(), key=lambda x: x['nombre']),
    'd': data,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(dataset, f, ensure_ascii=False, separators=(',', ':'))

size_kb = OUT.stat().st_size / 1024
print(f"OK → {OUT.relative_to(ROOT)} ({size_kb:.1f} KB)")
print(f"   Entidades: {len(ent)}")
print(f"   Años:      {dataset['meta']['years']}")
print(f"   Literales: act={len(L_ACT)} pas={len(L_PAS)} nv={len(L_NV)} vi={len(L_VI)} nt={len(L_NT)} sol={len(SOL_CELLS)}")
