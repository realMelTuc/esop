from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row

bp = Blueprint('wrecks', __name__)


@bp.route('/wrecks/')
def wrecks_index():
    return render_template('partials/wrecks/index.html')


# ── API ─────────────────────────────────────────────────────────────────────────

@bp.route('/api/wrecks')
def list_wrecks():
    op_id      = request.args.get('operation_id')
    ship_class = request.args.get('ship_class', '')
    faction    = request.args.get('faction', '')
    limit      = min(int(request.args.get('limit', 200)), 1000)
    offset     = int(request.args.get('offset', 0))

    where = ['1=1']
    params = []
    if op_id:
        where.append('w.operation_id = %s')
        params.append(int(op_id))
    if ship_class:
        where.append('w.ship_class = %s')
        params.append(ship_class)
    if faction:
        where.append('w.faction ILIKE %s')
        params.append(f'%{faction}%')

    params += [limit, offset]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT w.id, w.operation_id, w.ship_class, w.ship_name, w.faction,
               w.quantity, w.salvaged_count, w.unsalvageable_count,
               w.expected_yield_isk, w.notes, w.created_at,
               o.op_ref, o.title AS op_title, o.system_name, o.region
        FROM esop_wrecks w
        JOIN esop_operations o ON o.id = w.operation_id
        WHERE {' AND '.join(where)}
        ORDER BY w.created_at DESC
        LIMIT %s OFFSET %s
    """, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])


@bp.route('/api/wrecks', methods=['POST'])
def add_wreck():
    data = request.get_json() or {}
    if not data.get('operation_id') or not data.get('ship_class'):
        return jsonify({'error': 'operation_id and ship_class are required'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO esop_wrecks
            (operation_id, ship_class, ship_name, faction, quantity,
             salvaged_count, unsalvageable_count, expected_yield_isk, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, [
        data['operation_id'],
        data['ship_class'],
        data.get('ship_name'),
        data.get('faction'),
        data.get('quantity', 1),
        data.get('salvaged_count', 0),
        data.get('unsalvageable_count', 0),
        data.get('expected_yield_isk', 0),
        data.get('notes'),
    ])
    row = cur.fetchone()

    cur.execute("""
        UPDATE esop_operations
        SET total_wreck_count = (
            SELECT COALESCE(SUM(quantity), 0) FROM esop_wrecks WHERE operation_id = %s
        ), updated_at = NOW()
        WHERE id = %s
    """, [data['operation_id'], data['operation_id']])

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'id': row['id']}), 201


@bp.route('/api/wrecks/<int:wreck_id>', methods=['PATCH'])
def update_wreck(wreck_id):
    data = request.get_json() or {}
    allowed = ['ship_class', 'ship_name', 'faction', 'quantity',
               'salvaged_count', 'unsalvageable_count', 'expected_yield_isk', 'notes']
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'No valid fields'}), 400

    set_clause = ', '.join(f'{k} = %s' for k in fields)
    values = list(fields.values()) + [wreck_id]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'UPDATE esop_wrecks SET {set_clause} WHERE id = %s', values)
    if cur.rowcount == 0:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    if 'quantity' in fields:
        cur.execute("""
            UPDATE esop_operations SET
                total_wreck_count = (
                    SELECT COALESCE(SUM(quantity), 0) FROM esop_wrecks WHERE operation_id = esop_operations.id
                ),
                updated_at = NOW()
            WHERE id = (SELECT operation_id FROM esop_wrecks WHERE id = %s)
        """, [wreck_id])

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/api/wrecks/<int:wreck_id>', methods=['DELETE'])
def delete_wreck(wreck_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT operation_id FROM esop_wrecks WHERE id = %s', [wreck_id])
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    op_id = row['operation_id']
    cur.execute('DELETE FROM esop_wrecks WHERE id = %s', [wreck_id])

    cur.execute("""
        UPDATE esop_operations SET
            total_wreck_count = (
                SELECT COALESCE(SUM(quantity), 0) FROM esop_wrecks WHERE operation_id = %s
            ),
            updated_at = NOW()
        WHERE id = %s
    """, [op_id, op_id])

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/api/wrecks/summary')
def wreck_summary():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            ship_class,
            COUNT(*) AS wreck_entries,
            SUM(quantity) AS total_quantity,
            SUM(salvaged_count) AS total_salvaged,
            ROUND(AVG(expected_yield_isk)::numeric, 0) AS avg_expected_isk,
            SUM(expected_yield_isk) AS total_expected_isk
        FROM esop_wrecks
        GROUP BY ship_class
        ORDER BY total_expected_isk DESC NULLS LAST
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])
