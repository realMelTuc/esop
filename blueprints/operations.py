import uuid
from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row

bp = Blueprint('operations', __name__)


@bp.route('/operations/')
def operations_index():
    return render_template('partials/operations/index.html')


@bp.route('/operations/<int:op_id>/')
def operations_detail(op_id):
    return render_template('partials/operations/detail.html', op_id=op_id)


# ── API ─────────────────────────────────────────────────────────────────────────

@bp.route('/api/operations')
def list_operations():
    status    = request.args.get('status', '')
    region    = request.args.get('region', '')
    site_type = request.args.get('site_type', '')
    search    = request.args.get('q', '')
    limit     = min(int(request.args.get('limit', 100)), 500)
    offset    = int(request.args.get('offset', 0))

    where = ['1=1']
    params = []
    if status:
        where.append('status = %s')
        params.append(status)
    if region:
        where.append('region ILIKE %s')
        params.append(f'%{region}%')
    if site_type:
        where.append('site_type = %s')
        params.append(site_type)
    if search:
        where.append('(title ILIKE %s OR system_name ILIKE %s OR op_ref ILIKE %s)')
        params += [f'%{search}%', f'%{search}%', f'%{search}%']

    params += [limit, offset]

    conn = get_db()
    cur = conn.cursor()

    cur.execute(f"""
        SELECT id, op_ref, title, system_name, region, site_type, site_name,
               difficulty, status, ship_used, character_name,
               total_wreck_count, salvage_runs, estimated_isk, actual_isk,
               started_at, completed_at, created_at
        FROM esop_operations
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(completed_at, started_at, created_at) DESC
        LIMIT %s OFFSET %s
    """, params)
    ops = cur.fetchall()

    count_params = params[:-2] if len(params) > 2 else None
    cur.execute(f"""
        SELECT COUNT(*) AS total FROM esop_operations WHERE {' AND '.join(where[:-2]) if len(where) > 2 else '1=1'}
    """, count_params)
    count = cur.fetchone()

    cur.close()
    conn.close()
    return jsonify({
        'operations': [serialize_row(o) for o in ops],
        'total': count['total'] if count else 0
    })


@bp.route('/api/operations/<int:op_id>')
def get_operation(op_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT o.*,
               COALESCE((SELECT SUM(total_value_isk) FROM esop_salvage_items WHERE operation_id = o.id), 0) AS salvage_total_isk,
               (SELECT COUNT(*) FROM esop_wrecks WHERE operation_id = o.id) AS wreck_types,
               (SELECT SUM(quantity) FROM esop_wrecks WHERE operation_id = o.id) AS wreck_count_db
        FROM esop_operations o
        WHERE o.id = %s
    """, [op_id])
    op = cur.fetchone()
    if not op:
        cur.close()
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    cur.execute("""
        SELECT id, ship_class, ship_name, faction, quantity, salvaged_count,
               unsalvageable_count, expected_yield_isk, notes, created_at
        FROM esop_wrecks
        WHERE operation_id = %s
        ORDER BY ship_class, ship_name
    """, [op_id])
    wrecks = cur.fetchall()

    cur.execute("""
        SELECT id, item_name, tier, quantity, unit_value_isk, total_value_isk,
               sold, sold_at, notes, created_at
        FROM esop_salvage_items
        WHERE operation_id = %s
        ORDER BY total_value_isk DESC
    """, [op_id])
    items = cur.fetchall()

    cur.close()
    conn.close()
    result = serialize_row(op)
    result['wrecks'] = [serialize_row(w) for w in wrecks]
    result['salvage_items'] = [serialize_row(i) for i in items]
    return jsonify(result)


@bp.route('/api/operations', methods=['POST'])
def create_operation():
    data = request.get_json() or {}
    if not data.get('title'):
        return jsonify({'error': 'title is required'}), 400

    op_ref = data.get('op_ref') or f"OP-{uuid.uuid4().hex[:8].upper()}"

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO esop_operations
            (op_ref, title, system_name, region, site_type, site_name,
             difficulty, status, ship_used, character_name,
             estimated_isk, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, op_ref
    """, [
        op_ref,
        data.get('title'),
        data.get('system_name'),
        data.get('region'),
        data.get('site_type', 'anomaly'),
        data.get('site_name'),
        data.get('difficulty', 'standard'),
        data.get('status', 'planned'),
        data.get('ship_used'),
        data.get('character_name'),
        data.get('estimated_isk', 0),
        data.get('notes'),
    ])
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': row['id'], 'op_ref': row['op_ref']}), 201


@bp.route('/api/operations/<int:op_id>', methods=['PATCH'])
def update_operation(op_id):
    data = request.get_json() or {}
    allowed = ['title', 'system_name', 'region', 'site_type', 'site_name',
               'difficulty', 'status', 'ship_used', 'character_name',
               'total_wreck_count', 'salvage_runs', 'estimated_isk', 'actual_isk',
               'started_at', 'completed_at', 'notes']
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'No valid fields to update'}), 400

    set_clause = ', '.join(f'{k} = %s' for k in fields)
    set_clause += ', updated_at = NOW()'
    values = list(fields.values()) + [op_id]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'UPDATE esop_operations SET {set_clause} WHERE id = %s', values)
    if cur.rowcount == 0:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/api/operations/<int:op_id>', methods=['DELETE'])
def delete_operation(op_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM esop_operations WHERE id = %s', [op_id])
    if cur.rowcount == 0:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/api/operations/filters/regions')
def list_regions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT region FROM esop_operations
        WHERE region IS NOT NULL AND region <> ''
        ORDER BY region
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([r['region'] for r in rows])
