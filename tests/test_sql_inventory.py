"""Inventory extraction reads code; test SQL is never executed."""
from tools.audit_sql_inventory import build, canonical, orm_key, sources, split_sql


def test_statement_split_preserves_quoted_comments_and_semicolons():
    source = "-- example\nSELECT 'a;--b#c$$' AS value;\nSELECT COUNT(*) FROM users;"
    statements = list(split_sql(source))
    assert len(statements) == 2
    assert "'a;--b#c$$'" in statements[0][0]
    assert statements[0][1] == 2


def test_duplicate_schema_seed_rows_and_query_bindings_do_not_inflate_count():
    result = build({
        'database/schema.sql': 'CREATE TABLE roles(role_id INT PRIMARY KEY);',
        'database/schema_safe.sql': '-- duplicate\nCREATE TABLE roles ( role_id INT PRIMARY KEY );',
        'database/seed.sql': "INSERT INTO roles(role_id) VALUES(1); INSERT INTO roles(role_id) VALUES(2),(3);",
        'app/example.py': '''def read(database):
    database.execute(text("SELECT user_id FROM users WHERE email=:email ORDER BY user_id LIMIT 20"))
    database.execute(text("SELECT user_id FROM users WHERE email=:address ORDER BY user_id DESC LIMIT 50"))
''',
    })
    assert result['totals'] == {'Application': 1, 'Schema/DDL': 1, 'Seed INSERT': 1}
    assert result['total_distinct_meaningful_statements'] == 3
    assert len(next(row for row in result['queries'] if row['group'] == 'Schema/DDL')['sources']) == 2


def test_firebase_migration_copies_count_once():
    data = sources()
    result = build({name: data[name] for name in (
        'database/migrations/002_firebase_authentication.sql',
        'teammate_review/dhairya/001_firebase_auth.sql')})
    assert result['totals']['Schema/DDL'] == 1
    row = next(row for row in result['queries'] if row['counted'])
    assert len(row['sources']) == 2


def test_orm_bound_names_get_order_and_lock_variants_are_one_read_family():
    first = 'select(ServiceRequest).where(ServiceRequest.request_id == request_id).with_for_update()'
    second = "select(ServiceRequest).where(ServiceRequest.request_id == event['request_id'])"
    third = 'database.get(ServiceRequest, chosen_id)'
    assert orm_key(first) == orm_key(second) == orm_key(third)


def test_original_twenty_tables_and_ten_academic_queries_are_preserved():
    # Pin the pre-submission schema. HEAD moves when these changes are committed.
    current, previous = sources(), sources('abad5c82c1b33441ec37ec672d629a34a5f82047')
    for name, count in [('database/schema.sql', 20), ('database/schema_safe.sql', 20), ('database/queries.sql', 10)]:
        def meaningful(source):
            return [canonical(sql, literals=True) for sql, _ in split_sql(source)
                    if sql.startswith(('CREATE TABLE', 'SELECT'))]
        expected = previous[name]
        if name.endswith(('schema.sql', 'schema_safe.sql')):
            # The user's already-applied Firebase migration is the sole approved
            # baseline change. Compare every other column/constraint exactly.
            assert expected.count('password_hash VARCHAR(255) NOT NULL') == 1
            expected = expected.replace('password_hash VARCHAR(255) NOT NULL',
                'firebase_uid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,\n'
                '    password_hash VARCHAR(255) NULL')
            expected = expected.replace('INDEX idx_users_email (email)',
                'INDEX idx_users_email (email),\n'
                '    CONSTRAINT uq_users_firebase_uid UNIQUE (firebase_uid)')
            expected = expected.replace('    is_backup BOOLEAN NOT NULL DEFAULT FALSE,\n', '')
            expected = expected.replace('    INDEX idx_ref_is_backup (is_backup),\n', '')
        else:
            expected = expected.replace('ref.is_backup,', '(ref.attempt_number > 1) AS is_backup,')
            expected = expected.replace('r_rescue.is_backup = TRUE', 'r_rescue.attempt_number > 1')
            expected = expected.replace('WHERE is_backup = TRUE', 'WHERE attempt_number > 1')
        assert meaningful(current[name]) == meaningful(expected)
        assert len(meaningful(current[name])) == count
    assert current['app/services/reports.py'] == previous['app/services/reports.py']


def test_active_application_queries_exceed_minimum_without_ddl_or_seeds():
    result = build(sources())
    assert not result['unresolved_expressions']
    assert result['meaningful_application_queries'] >= 25
    assert result['totals']['Schema/DDL'] == 26
    assert result['totals']['Seed INSERT'] == 20
    assert result['totals']['Academic demonstration'] == 10
    demo = [row for row in result['queries']
            if any(site['file'] == 'database/demo_data.sql' for site in row['sources'])]
    assert sum(row['operation'] == 'SELECT' for row in demo) == 11
    assert {row['operation'] for row in demo} >= {'SELECT', 'INSERT', 'UPDATE'}
    assert all(row['group'] == 'Ancillary/control' and not row['counted'] for row in demo)
    assert result['schema_review']['declared_table_count'] == 21
    assert result['schema_review']['declared_primary_key_count'] == 21
    assert result['schema_review']['declared_foreign_key_count'] == 34
    assert not result['schema_review']['invalid_declared_references']
    assert 'CHARACTER' not in result['schema_review']['entities']['users']['columns']
    assert all(not row['counted'] for row in result['queries'] if row['group'] in {'Transaction control', 'Legacy demonstration', 'Ancillary/control'})
