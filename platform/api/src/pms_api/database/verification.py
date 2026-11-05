"""Compare full structural catalogs before adopting the reviewed SQL baseline."""

import json
from importlib.resources import files

QUERIES = {
    "views": "SELECT viewname,definition FROM pg_views WHERE schemaname='device_platform' ORDER BY viewname",
    "columns": """SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid),a.attidentity,a.attgenerated
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
 LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
 WHERE n.nspname='device_platform' AND c.relkind IN ('r','p','v') AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum""",
    "constraints": """SELECT c.relname,co.conname,pg_get_constraintdef(co.oid),co.convalidated FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='device_platform' ORDER BY c.relname,co.conname""",
    "indexes": """SELECT c.relname,i.relname,pg_get_indexdef(i.oid),x.indisvalid,x.indisready FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid JOIN pg_class i ON i.oid=x.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='device_platform' ORDER BY c.relname,i.relname""",
    "functions": """SELECT p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='device_platform' ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)""",
    "triggers": """SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='device_platform' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
    "tables": """SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='device_platform' AND c.relkind IN ('r','p','v','m','S') ORDER BY c.relname""",
    "policies": """SELECT tablename,policyname,permissive,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname='device_platform' ORDER BY tablename,policyname""",
}


def signature(connection):
    connection.execute("SET LOCAL search_path=pg_catalog")
    return {key: [list(row) for row in connection.execute(sql).fetchall()] for key, sql in QUERIES.items()}


def verify_baseline(connection):
    expected = json.loads(files("pms_api.database.baseline").joinpath("signature.json").read_text())
    actual = signature(connection)
    differences = [key for key in expected if actual.get(key) != expected[key]]
    if differences:
        raise RuntimeError("Baseline adoption refused; structural drift in: " + ", ".join(differences))
    if (
        connection.execute("SELECT count(*) FROM device_platform.platform_settings WHERE id=1").fetchone()[0]
        != 1
    ):
        raise RuntimeError("Baseline adoption refused; platform singleton is absent")
    return True
