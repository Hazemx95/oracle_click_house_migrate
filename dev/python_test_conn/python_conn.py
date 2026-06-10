import os

import oracledb

user = os.getenv("P5_QA_ORACLE_USER", "")
password = os.getenv("P5_QA_ORACLE_PASSWORD", "")
dsn = os.getenv("P5_QA_ORACLE_DSN", "")

if not user or not password or not dsn:
    raise RuntimeError("Oracle test connection requires environment variables")

try:
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        print("Oracle connection: SUCCESS")

        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM dual")
            print("Result:", cur.fetchone())

except Exception as e:
    print("Oracle connection: FAILED")
    print(e)
    print(e.__class__)
