import csv
import os
import sys

import pymysql
from config import DB_CONFIG, DATA_DIR


def get_conn(with_db=True):
    cfg = DB_CONFIG.copy()
    if not with_db:
        cfg.pop('database', None)
    return pymysql.connect(**cfg)


def init_db():
    conn = get_conn(with_db=False)
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" % DB_CONFIG['database'])
        conn.commit()
    finally:
        conn.close()


def create_tables():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS host_detail (
                    hostid VARCHAR(20) PRIMARY KEY,
                    hostname VARCHAR(100),
                    owner VARCHAR(50),
                    model VARCHAR(50),
                    location1 VARCHAR(50),
                    location2 VARCHAR(50),
                    INDEX idx_location1 (location1),
                    INDEX idx_model (model)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mod_detail (
                    `mod` VARCHAR(40) PRIMARY KEY,
                    `type` VARCHAR(20),
                    `desc` VARCHAR(200),
                    unit VARCHAR(20),
                    tag VARCHAR(50),
                    INDEX idx_type (`type`),
                    INDEX idx_tag (tag)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS disk_tsar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    ts BIGINT NOT NULL,
                    hostid VARCHAR(20) NOT NULL,
                    `type` VARCHAR(20),
                    `mod` VARCHAR(40),
                    `value` DOUBLE,
                    tag VARCHAR(50),
                    INDEX idx_hostid (hostid),
                    INDEX idx_mod (`mod`),
                    INDEX idx_ts (ts),
                    INDEX idx_host_ts (`hostid`, `ts`),
                    INDEX idx_tag (tag)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pref_tsar (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    ts BIGINT NOT NULL,
                    hostid VARCHAR(20) NOT NULL,
                    `type` VARCHAR(20),
                    `mod` VARCHAR(40),
                    `value` DOUBLE,
                    tag VARCHAR(50),
                    INDEX idx_hostid (hostid),
                    INDEX idx_mod (`mod`),
                    INDEX idx_ts (ts),
                    INDEX idx_host_ts (`hostid`, `ts`),
                    INDEX idx_tag (tag)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.commit()
    finally:
        conn.close()


def load_tsv(filename):
    path = os.path.join(DATA_DIR, filename)
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for r in reader:
            rows.append(r)
    return rows


def insert_host_detail():
    rows = load_tsv('host_detail.dat')
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE host_detail")
            sql = "INSERT INTO host_detail (hostid, hostname, owner, model, location1, location2) VALUES (%s,%s,%s,%s,%s,%s)"
            cur.executemany(sql, [(r['hostid'], r['hostname'], r['owner'], r['model'], r['location1'], r['location2']) for r in rows])
        conn.commit()
        print('host_detail loaded:', len(rows))
    finally:
        conn.close()


def insert_mod_detail():
    rows = load_tsv('mod_detail.dat')
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE mod_detail")
            sql = "INSERT INTO mod_detail (`mod`, `type`, `desc`, unit, tag) VALUES (%s,%s,%s,%s,%s)"
            cur.executemany(sql, [(r['mod'], r['type'], r['desc'], r['unit'], r['tag']) for r in rows])
        conn.commit()
        print('mod_detail loaded:', len(rows))
    finally:
        conn.close()


def _batch_insert(table, rows):
    if not rows:
        return
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE %s" % table)
            sql = "INSERT INTO %s (ts, hostid, `type`, `mod`, `value`, tag) VALUES (%%s,%%s,%%s,%%s,%%s,%%s)" % table
            batch = []
            for i, r in enumerate(rows, 1):
                try:
                    val = float(r['value']) if r['value'] != '' else None
                except ValueError:
                    val = None
                batch.append((int(r['ts']), r['hostid'], r['type'], r['mod'], val, r['tag']))
                if i % 5000 == 0:
                    cur.executemany(sql, batch)
                    batch = []
            if batch:
                cur.executemany(sql, batch)
        conn.commit()
        print('%s loaded:' % table, len(rows))
    finally:
        conn.close()


def insert_disk_tsar():
    rows = load_tsv('disk_tsar.dat')
    _batch_insert('disk_tsar', rows)


def insert_pref_tsar():
    rows = load_tsv('pref_tsar.dat')
    _batch_insert('pref_tsar', rows)


def main():
    print('Initializing database...')
    init_db()
    create_tables()
    print('Loading data...')
    insert_host_detail()
    insert_mod_detail()
    insert_disk_tsar()
    insert_pref_tsar()
    print('ETL completed.')


if __name__ == '__main__':
    main()
