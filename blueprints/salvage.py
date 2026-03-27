from flask import Blueprint, render_template, jsonify, request
from db import get_db, serialize_row

bp = Blueprint('salvage', __name__)


@bp.route('/salvage/')
def salvage_index():
    return render_template('partials/salvage/index.html')


# ── API ─────────────────────────────────────────────────────────────────────────

@bp.route('/api/salvage')
def list_salvage():
    op_id     = request.args.get('operation_id')
    item_name = request.args.get('item_name', '')
    tier      = request.args.get('tier', '')
    sold      = request.args.get('sold', '')
    limit     = min(int(request.args.get('limit', 200)), 1000)
    offset    = int(request.args.get('offset', 0))

    where = ['1=1']
    params = []
    if op_id:
        where.append('s.operation_id = %s')
        params.append(int(op_id))
    if item_name:
        where.append('s.item_name ILIKE %s')
        params.append(f'%{item_name}%')
    if tier:
        where.append('s.tier = %s')
        params.append(tier)
    if sold == 'true':
        where.append('s.sold = TRUE')
    elif sold == 'false':
        where.append('s.sold = FALSE')

    params += [limit, offset]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT s.id, s.operation_id, s.item_name, s.tier, s.quantity,
               s.unit_value_isk, s.total_value_isk, s.sold, s.sold_at,
               s.notes, s.created_at,
               o.op_ref, o.title AS op_title, o.system_name, o.region
        FROM esop_salvage_items s
        JOIN esop_operations o ON o.id = s.operation_id
        WHERE {' AND '.join(where)}
        ORDER BY s.total_value_isk DESC NULLS LAST, s.created_at DESC
        LIMIT %s OFFSET %s
    """, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])


@bp.route('/api/salvage', methods=['POST'])
def add_salvage_item():
    data = request.get_json() or {}
    if not data.get('operation_id') or not data.get('item_name'):
        return jsonify({'error': 'operation_id and item_name are required'}), 400

    items = data.get('items')
    if not items:
        items = [{
            'item_name':     data.get('item_name'),
            'tier':          data.get('tier', 't1'),
            'quantity':      data.get('quantity', 1),
            'unit_value_isk': data.get('unit_value_isk', 0),
            'notes':         data.get('notes'),
        }]

    op_id = data['operation_id']
    conn = get_db()
    cur = conn.cursor()
    inserted = []
    for item in items:
        cur.execute("""
            INSERT INTO esop_salvage_items
                (operation_id, item_name, tier, quantity, unit_value_isk, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, [
            op_id,
            item.get('item_name'),
            item.get('tier', 't1'),
            item.get('quantity', 1),
            item.get('unit_value_isk', 0),
            item.get('notes'),
        ])
        row = cur.fetchone()
        inserted.append(row['id'])

    cur.execute("""
        UPDATE esop_operations SET
            actual_isk = (
                SELECT COALESCE(SUM(total_value_isk), 0) FROM esop_salvage_items WHERE operation_id = %s
            ),
            updated_at = NOW()
        WHERE id = %s
    """, [op_id, op_id])

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ids': inserted}), 201


@bp.route('/api/salvage/<int:item_id>', methods=['PATCH'])
def update_salvage_item(item_id):
    data = request.get_json() or {}
    allowed = ['item_name', 'tier', 'quantity', 'unit_value_isk', 'sold', 'sold_at', 'notes']
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'No valid fields'}), 400

    set_clause = ', '.join(f'{k} = %s' for k in fields)
    values = list(fields.values()) + [item_id]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'UPDATE esop_salvage_items SET {set_clause} WHERE id = %s', values)
    if cur.rowcount == 0:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    cur.execute("""
        UPDATE esop_operations SET
            actual_isk = (
                SELECT COALESCE(SUM(total_value_isk), 0) FROM esop_salvage_items WHERE operation_id = esop_operations.id
            ),
            updated_at = NOW()
        WHERE id = (SELECT operation_id FROM esop_salvage_items WHERE id = %s)
    """, [item_id])

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/api/salvage/<int:item_id>', methods=['DELETE'])
def delete_salvage_item(item_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT operation_id FROM esop_salvage_items WHERE id = %s', [item_id])
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    op_id = row['operation_id']
    cur.execute('DELETE FROM esop_salvage_items WHERE id = %s', [item_id])

    cur.execute("""
        UPDATE esop_operations SET
            actual_isk = (
                SELECT COALESCE(SUM(total_value_isk), 0) FROM esop_salvage_items WHERE operation_id = %s
            ),
            updated_at = NOW()
        WHERE id = %s
    """, [op_id, op_id])

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/api/salvage/summary')
def salvage_summary():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            item_name,
            tier,
            SUM(quantity) AS total_qty,
            ROUND(AVG(unit_value_isk)::numeric, 0) AS avg_unit_isk,
            SUM(total_value_isk) AS total_isk,
            COUNT(DISTINCT operation_id) AS op_count
        FROM esop_salvage_items
        GROUP BY item_name, tier
        ORDER BY total_isk DESC NULLS LAST
        LIMIT 30
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])


@bp.route('/api/salvage/unsold')
def unsold_inventory():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            item_name,
            tier,
            SUM(quantity) AS total_qty,
            ROUND(AVG(unit_value_isk)::numeric, 0) AS avg_unit_isk,
            SUM(total_value_isk) AS total_isk
        FROM esop_salvage_items
        WHERE sold = FALSE
        GROUP BY item_name, tier
        ORDER BY total_isk DESC NULLS LAST
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])
