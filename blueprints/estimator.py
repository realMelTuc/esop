from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row

bp = Blueprint('estimator', __name__)

SHIP_CLASS_ORDER = ['frigate', 'destroyer', 'cruiser', 'battlecruiser', 'battleship', 'capital', 'structure', 'drone']
SITE_TYPE_MULTS = {
    'anomaly':     1.0,
    'mission_l1':  0.5,
    'mission_l2':  0.7,
    'mission_l3':  1.1,
    'mission_l4':  1.4,
    'combat_site': 1.2,
    'deadspace':   1.5,
    'wormhole':    1.8,
    'other':       1.0,
}
DIFFICULTY_MULTS = {
    'rookie':    0.6,
    'standard':  1.0,
    'superior':  1.3,
    'overseer':  1.8,
    'escalation': 2.2,
}


@bp.route('/estimator/')
def estimator_index():
    return render_template('partials/estimator/index.html')


@bp.route('/api/estimator/ship-classes')
def ship_classes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT ship_class FROM esop_yield_reference ORDER BY ship_class')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([r['ship_class'] for r in rows])


@bp.route('/api/estimator/factions')
def factions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT faction FROM esop_yield_reference WHERE faction IS NOT NULL ORDER BY faction')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([r['faction'] for r in rows])


@bp.route('/api/estimator/reference')
def yield_reference():
    ship_class = request.args.get('ship_class', '')
    faction    = request.args.get('faction', 'generic')
    conn = get_db()
    cur = conn.cursor()
    where = ['1=1']
    params = []
    if ship_class:
        where.append('ship_class = %s')
        params.append(ship_class)
    if faction:
        where.append('faction = %s')
        params.append(faction)
    cur.execute(f"""
        SELECT * FROM esop_yield_reference
        WHERE {' AND '.join(where)}
        ORDER BY ship_class, avg_qty * unit_value_isk DESC
    """, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])


@bp.route('/api/estimator/calculate', methods=['POST'])
def calculate_estimate():
    data = request.get_json() or {}
    site_type  = data.get('site_type', 'anomaly')
    difficulty = data.get('difficulty', 'standard')
    faction    = data.get('faction', 'generic')
    wrecks     = data.get('wrecks', [])

    if not wrecks:
        return jsonify({'error': 'wrecks list is required'}), 400

    site_mult = SITE_TYPE_MULTS.get(site_type, 1.0)
    diff_mult = DIFFICULTY_MULTS.get(difficulty, 1.0)
    combined_mult = site_mult * diff_mult

    conn = get_db()
    cur = conn.cursor()

    breakdown = []
    grand_min = 0.0
    grand_max = 0.0
    grand_avg = 0.0
    item_totals = {}

    for wreck in wrecks:
        ship_class = wreck.get('ship_class', '')
        qty        = int(wreck.get('quantity', 1))
        if not ship_class or qty <= 0:
            continue

        cur.execute("""
            SELECT item_name, tier, min_qty, max_qty, avg_qty, drop_prob, unit_value_isk
            FROM esop_yield_reference
            WHERE ship_class = %s AND faction = %s
            ORDER BY avg_qty * unit_value_isk DESC
        """, [ship_class, faction])
        ref_rows = cur.fetchall()
        if not ref_rows and faction != 'generic':
            cur.execute("""
                SELECT item_name, tier, min_qty, max_qty, avg_qty, drop_prob, unit_value_isk
                FROM esop_yield_reference
                WHERE ship_class = %s AND faction = 'generic'
                ORDER BY avg_qty * unit_value_isk DESC
            """, [ship_class])
            ref_rows = cur.fetchall()

        class_min = 0.0
        class_max = 0.0
        class_avg = 0.0
        items_for_class = []

        for ref in ref_rows:
            item_min = ref['min_qty'] * ref['drop_prob'] * ref['unit_value_isk'] * qty * combined_mult
            item_max = ref['max_qty'] * ref['unit_value_isk'] * qty * combined_mult
            item_avg = ref['avg_qty'] * ref['drop_prob'] * ref['unit_value_isk'] * qty * combined_mult

            class_min += item_min
            class_max += item_max
            class_avg += item_avg

            key = ref['item_name']
            if key not in item_totals:
                item_totals[key] = {'item_name': key, 'tier': ref['tier'], 'avg_qty': 0.0, 'avg_isk': 0.0}
            item_totals[key]['avg_qty'] += float(ref['avg_qty']) * float(ref['drop_prob']) * qty
            item_totals[key]['avg_isk'] += item_avg

            items_for_class.append({
                'item_name':     ref['item_name'],
                'tier':          ref['tier'],
                'drop_prob':     float(ref['drop_prob']),
                'unit_value_isk': float(ref['unit_value_isk']),
                'min_isk':       round(item_min, 0),
                'max_isk':       round(item_max, 0),
                'avg_isk':       round(item_avg, 0),
            })

        grand_min += class_min
        grand_max += class_max
        grand_avg += class_avg

        breakdown.append({
            'ship_class': ship_class,
            'quantity':   qty,
            'min_isk':    round(class_min, 0),
            'max_isk':    round(class_max, 0),
            'avg_isk':    round(class_avg, 0),
            'items':      items_for_class,
        })

    cur.close()
    conn.close()

    item_list = sorted(item_totals.values(), key=lambda x: x['avg_isk'], reverse=True)

    return jsonify({
        'site_type':   site_type,
        'difficulty':  difficulty,
        'faction':     faction,
        'site_mult':   site_mult,
        'diff_mult':   diff_mult,
        'combined_mult': combined_mult,
        'estimate': {
            'min_isk': round(grand_min, 0),
            'max_isk': round(grand_max, 0),
            'avg_isk': round(grand_avg, 0),
        },
        'breakdown':   breakdown,
        'item_totals': item_list,
    })


@bp.route('/api/estimator/reference/<ship_class>/update', methods=['POST'])
def update_reference(ship_class):
    data = request.get_json() or {}
    faction   = data.get('faction', 'generic')
    item_name = data.get('item_name')
    if not item_name:
        return jsonify({'error': 'item_name required'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO esop_yield_reference
            (ship_class, faction, item_name, tier, min_qty, max_qty, avg_qty,
             drop_prob, unit_value_isk, source, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'manual', NOW())
        ON CONFLICT (ship_class, faction, item_name)
        DO UPDATE SET
            tier = EXCLUDED.tier,
            min_qty = EXCLUDED.min_qty,
            max_qty = EXCLUDED.max_qty,
            avg_qty = EXCLUDED.avg_qty,
            drop_prob = EXCLUDED.drop_prob,
            unit_value_isk = EXCLUDED.unit_value_isk,
            source = 'manual',
            updated_at = NOW()
        RETURNING id
    """, [
        ship_class, faction, item_name,
        data.get('tier', 't1'),
        data.get('min_qty', 0),
        data.get('max_qty', 1),
        data.get('avg_qty', 0.5),
        data.get('drop_prob', 0.5),
        data.get('unit_value_isk', 0),
    ])
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': row['id']}), 200
