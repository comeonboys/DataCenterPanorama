from datetime import datetime

import pymysql
from flask import Flask, jsonify, render_template, request

from config import DB_CONFIG

app = Flask(__name__)


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def query(sql, params=()):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def ts_to_dt(ts):
    return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/summary')
def api_summary():
    total_hosts = query("SELECT COUNT(*) c FROM host_detail")[0]['c']
    total_models = query("SELECT COUNT(DISTINCT model) c FROM host_detail")[0]['c']
    total_locations = query("SELECT COUNT(DISTINCT location1) c FROM host_detail")[0]['c']
    total_records = query("SELECT (SELECT COUNT(*) FROM disk_tsar)+(SELECT COUNT(*) FROM pref_tsar) c")[0]['c']
    latest_pref = query("SELECT MAX(ts) ts FROM pref_tsar")[0]['ts']
    latest_disk = query("SELECT MAX(ts) ts FROM disk_tsar")[0]['ts']

    # alert count: latest snapshot hosts exceeding thresholds
    alerts_sql = """
    WITH pref_latest AS (
        SELECT hostid, `mod`, `value`
        FROM pref_tsar p
        WHERE (hostid, ts) IN (SELECT hostid, MAX(ts) FROM pref_tsar GROUP BY hostid)
    ),
    pref_pivot AS (
        SELECT hostid,
            MAX(CASE WHEN `mod`='cpu_usage' THEN `value` END) cpu_usage,
            MAX(CASE WHEN `mod`='cpu_wait' THEN `value` END) cpu_wait,
            MAX(CASE WHEN `mod`='load1' THEN `value` END) load1,
            MAX(CASE WHEN `mod`='mem_used' THEN `value` END) mem_used,
            MAX(CASE WHEN `mod`='mem_free' THEN `value` END) mem_free,
            MAX(CASE WHEN `mod`='mem_buff' THEN `value` END) mem_buff,
            MAX(CASE WHEN `mod`='mem_cache' THEN `value` END) mem_cache
        FROM pref_latest GROUP BY hostid
    ),
    disk_max AS (
        SELECT hostid, MAX(`value`) max_util
        FROM disk_tsar d
        WHERE `mod` LIKE '%%_util' AND (hostid, ts) IN (SELECT hostid, MAX(ts) FROM disk_tsar GROUP BY hostid)
        GROUP BY hostid
    )
    SELECT COUNT(*) c
    FROM pref_pivot p
    LEFT JOIN disk_max d ON p.hostid=d.hostid
    WHERE p.cpu_usage > 80
       OR p.cpu_wait > 30
       OR p.load1 > 5
       OR (p.mem_used / (p.mem_used+p.mem_free+p.mem_buff+p.mem_cache) * 100) > 85
       OR d.max_util > 90
    """
    alerts = query(alerts_sql)[0]['c']

    return jsonify({
        'total_hosts': total_hosts,
        'total_models': total_models,
        'total_locations': total_locations,
        'total_records': total_records,
        'latest_pref_ts': ts_to_dt(latest_pref) if latest_pref else None,
        'latest_disk_ts': ts_to_dt(latest_disk) if latest_disk else None,
        'alerts': alerts,
        'healthy_hosts': total_hosts - alerts,
    })


@app.route('/api/host_status')
def api_host_status():
    sql = """
    WITH pref_latest AS (
        SELECT hostid, `mod`, `value`
        FROM pref_tsar p
        WHERE (hostid, ts) IN (SELECT hostid, MAX(ts) FROM pref_tsar GROUP BY hostid)
    ),
    pref_pivot AS (
        SELECT hostid,
            MAX(CASE WHEN `mod`='cpu_usage' THEN `value` END) cpu_usage,
            MAX(CASE WHEN `mod`='cpu_wait' THEN `value` END) cpu_wait,
            MAX(CASE WHEN `mod`='load1' THEN `value` END) load1,
            MAX(CASE WHEN `mod`='mem_used' THEN `value` END) mem_used,
            MAX(CASE WHEN `mod`='mem_free' THEN `value` END) mem_free,
            MAX(CASE WHEN `mod`='mem_buff' THEN `value` END) mem_buff,
            MAX(CASE WHEN `mod`='mem_cache' THEN `value` END) mem_cache
        FROM pref_latest GROUP BY hostid
    ),
    disk_max AS (
        SELECT hostid, MAX(`value`) max_util
        FROM disk_tsar d
        WHERE `mod` LIKE '%%_util' AND (hostid, ts) IN (SELECT hostid, MAX(ts) FROM disk_tsar GROUP BY hostid)
        GROUP BY hostid
    )
    SELECT h.hostid, h.hostname, h.owner, h.model, h.location1, h.location2,
           p.cpu_usage, p.cpu_wait, p.load1, p.mem_used,
           ROUND(p.mem_used / (p.mem_used+p.mem_free+p.mem_buff+p.mem_cache) * 100, 2) mem_pct,
           d.max_util disk_max_util
    FROM host_detail h
    LEFT JOIN pref_pivot p ON h.hostid=p.hostid
    LEFT JOIN disk_max d ON h.hostid=d.hostid
    ORDER BY p.cpu_usage DESC
    """
    return jsonify(query(sql))


@app.route('/api/trends')
def api_trends():
    metric = request.args.get('metric', 'cpu_usage')
    hours = request.args.get('hours', type=int)
    # build safe literal condition to avoid %% formatting conflict with params
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cond = "`mod`=%s" % conn.escape(metric)
            if hours:
                latest = query("SELECT MAX(ts) ts FROM pref_tsar")[0]['ts']
                cond += " AND ts >= %s" % (latest - hours * 3600 * 1000)
            sql = """
            SELECT DATE_FORMAT(FROM_UNIXTIME(ts/1000), '%%Y-%%m-%%d %%H:00') as hour,
                   ROUND(AVG(`value`), 2) avg_value,
                   COUNT(*) cnt
            FROM pref_tsar
            WHERE %s
            GROUP BY hour
            ORDER BY hour
            """ % cond
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            return jsonify([dict(zip(cols, r)) for r in rows])
    finally:
        conn.close()


@app.route('/api/rank')
def api_rank():
    metric = request.args.get('metric', 'cpu_usage')
    limit = request.args.get('limit', 10, type=int)
    if metric == 'disk_max_util':
        sql = """
        SELECT h.hostid, h.hostname, h.model, d.max_util as value
        FROM host_detail h
        LEFT JOIN (
            SELECT hostid, MAX(`value`) max_util
            FROM disk_tsar
            WHERE `mod` LIKE '%%_util' AND (hostid, ts) IN (SELECT hostid, MAX(ts) FROM disk_tsar GROUP BY hostid)
            GROUP BY hostid
        ) d ON h.hostid=d.hostid
        ORDER BY d.max_util DESC
        LIMIT %s
        """
        return jsonify(query(sql, [limit]))
    sql = """
    SELECT h.hostid, h.hostname, h.model, p.value
    FROM host_detail h
    JOIN (
        SELECT hostid, `value`
        FROM pref_tsar p
        WHERE `mod`=%s AND (hostid, ts) IN (SELECT hostid, MAX(ts) FROM pref_tsar GROUP BY hostid)
    ) p ON h.hostid=p.hostid
    ORDER BY p.value DESC
    LIMIT %s
    """
    return jsonify(query(sql, [metric, limit]))


@app.route('/api/disk_heatmap')
def api_disk_heatmap():
    sql = """
    SELECT hostid,
           SUBSTRING_INDEX(`mod`, '_', 1) as disk,
           `value` util
    FROM disk_tsar
    WHERE `mod` LIKE '%%_util'
      AND (hostid, ts) IN (SELECT hostid, MAX(ts) FROM disk_tsar GROUP BY hostid)
    ORDER BY hostid, disk
    """
    rows = query(sql)
    hosts = sorted({r['hostid'] for r in rows})
    disks = ['sda', 'sdb', 'sdc', 'sdd', 'sde']
    data = []
    for i, h in enumerate(hosts):
        for j, d in enumerate(disks):
            val = next((r['util'] for r in rows if r['hostid'] == h and r['disk'] == d), 0)
            data.append([j, i, round(val, 2) if val else 0])
    return jsonify({'hosts': hosts, 'disks': disks, 'data': data})


@app.route('/api/network_io')
def api_network_io():
    sql = """
    SELECT DATE_FORMAT(FROM_UNIXTIME(ts/1000), '%%Y-%%m-%%d %%H:00') as hour,
           ROUND(SUM(CASE WHEN `mod`='net_in' THEN `value` ELSE 0 END), 2) net_in,
           ROUND(SUM(CASE WHEN `mod`='net_out' THEN `value` ELSE 0 END), 2) net_out
    FROM pref_tsar
    WHERE `mod` IN ('net_in', 'net_out')
    GROUP BY hour
    ORDER BY hour
    """
    return jsonify(query(sql))


@app.route('/api/distribution')
def api_distribution():
    field = request.args.get('field', 'model')
    if field not in ('model', 'location1'):
        field = 'model'
    sql = "SELECT %s as name, COUNT(*) value FROM host_detail GROUP BY %s ORDER BY value DESC" % (field, field)
    return jsonify(query(sql))


@app.route('/api/alerts')
def api_alerts():
    sql = """
    WITH pref_latest AS (
        SELECT hostid, `mod`, `value`
        FROM pref_tsar p
        WHERE (hostid, ts) IN (SELECT hostid, MAX(ts) FROM pref_tsar GROUP BY hostid)
    ),
    pref_pivot AS (
        SELECT hostid,
            MAX(CASE WHEN `mod`='cpu_usage' THEN `value` END) cpu_usage,
            MAX(CASE WHEN `mod`='cpu_wait' THEN `value` END) cpu_wait,
            MAX(CASE WHEN `mod`='load1' THEN `value` END) load1,
            MAX(CASE WHEN `mod`='mem_used' THEN `value` END) mem_used,
            MAX(CASE WHEN `mod`='mem_free' THEN `value` END) mem_free,
            MAX(CASE WHEN `mod`='mem_buff' THEN `value` END) mem_buff,
            MAX(CASE WHEN `mod`='mem_cache' THEN `value` END) mem_cache
        FROM pref_latest GROUP BY hostid
    ),
    disk_max AS (
        SELECT hostid, MAX(`value`) max_util
        FROM disk_tsar d
        WHERE `mod` LIKE '%%_util' AND (hostid, ts) IN (SELECT hostid, MAX(ts) FROM disk_tsar GROUP BY hostid)
        GROUP BY hostid
    )
    SELECT h.hostid, h.hostname, h.model, h.location1,
           p.cpu_usage, p.cpu_wait, p.load1,
           ROUND(p.mem_used / (p.mem_used+p.mem_free+p.mem_buff+p.mem_cache) * 100, 2) mem_pct,
           d.max_util disk_max_util
    FROM pref_pivot p
    LEFT JOIN host_detail h ON p.hostid=h.hostid
    LEFT JOIN disk_max d ON p.hostid=d.hostid
    WHERE p.cpu_usage > 80
       OR p.cpu_wait > 30
       OR p.load1 > 5
       OR (p.mem_used / (p.mem_used+p.mem_free+p.mem_buff+p.mem_cache) * 100) > 85
       OR d.max_util > 90
    ORDER BY p.cpu_usage DESC
    """
    return jsonify(query(sql))


@app.route('/api/metrics_meta')
def api_metrics_meta():
    sql = "SELECT `mod`, `desc`, unit FROM mod_detail WHERE `type`='pref' ORDER BY `mod`"
    return jsonify(query(sql))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
