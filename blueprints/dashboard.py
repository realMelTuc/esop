from flask import Blueprint, render_template, jsonify
from db import get_db, serialize_row

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard/')
def dashboard():
    return render_template('partials/dashboard/index.html')


@bp.route('/api/dashboard/stats')
def stats():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE status NOT IN ('abandoned')) AS total_ops,
            COUNT(*) FILTER (WHERE status = 'in_progress') AS active_ops,
            COUNT(*) FILTER (WHERE status = 'complete') AS completed_ops,
            COUNT(*) FILTER (WHERE status = 'planned') AS planned_ops,
            COALESCE(SUM(actual_isk) FILTER (WHERE status = 'complete'), 0) AS total_isk_earned,
            COALESCE(SUM(actual_isk) FILTER (WHERE status = 'complete'
                AND completed_at >= date_trunc('month', NOW())), 0) AS isk_this_month,
            COALESCE(AVG(actual_isk) FILTER (WHERE status = 'complete' AND actual_isk > 0), 0) AS avg_op_isk,
            COALESCE(SUM(total_wreck_count) FILTER (WHERE status = 'complete'), 0) AS total_wrecks_salvaged
        FROM esop_operations
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify(serialize_row(row) if row else {})


@bp.route('/api/dashboard/recent-ops')
def recent_ops():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, op_ref, title, system_name, region, site_type, difficulty,
               status, ship_used, character_name, total_wreck_count,
               estimated_isk, actual_isk, completed_at
        FROM esop_operations
        ORDER BY COALESCE(completed_at, created_at) DESC
        LIMIT 15
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])


@bp.route('/api/dashboard/top-regions')
def top_regions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COALESCE(region, 'Unknown') AS region,
            COUNT(*) AS op_count,
            COALESCE(SUM(actual_isk), 0) AS total_isk,
            COALESCE(AVG(actual_isk) FILTER (WHERE actual_isk > 0), 0) AS avg_isk,
            COALESCE(SUM(total_wreck_count), 0) AS total_wrecks
        FROM esop_operations
        WHERE status = 'complete'
        GROUP BY region
        ORDER BY total_isk DESC
        LIMIT 8
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])


@bp.route('/api/dashboard/yield-by-site-type')
def yield_by_site_type():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COALESCE(site_type, 'other') AS site_type,
            COUNT(*) AS op_count,
            COALESCE(SUM(actual_isk), 0) AS total_isk,
            COALESCE(AVG(actual_isk) FILTER (WHERE actual_isk > 0), 0) AS avg_isk
        FROM esop_operations
        WHERE status = 'complete'
        GROUP BY site_type
        ORDER BY total_isk DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])


@bp.route('/api/dashboard/active-ops')
def active_ops():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, op_ref, title, system_name, region, site_type, difficulty,
               status, ship_used, character_name, total_wreck_count,
               estimated_isk, started_at
        FROM esop_operations
        WHERE status IN ('planned', 'in_progress')
        ORDER BY
            CASE status WHEN 'in_progress' THEN 1 WHEN 'planned' THEN 2 END,
            created_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([serialize_row(r) for r in rows])
