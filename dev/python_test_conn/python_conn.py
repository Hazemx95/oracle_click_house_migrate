import oracledb

user = "admin"
password = "SiliconDba23"
dsn = "p5-ora-quality.cdyue4j7h7u5.us-east-1.rds.amazonaws.com:1521/quality"

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