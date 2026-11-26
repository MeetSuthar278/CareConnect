"""Static SQL inventory. Reads source/Git only; never imports the app or opens a DB.

    python tools/audit_sql_inventory.py
    python tools/audit_sql_inventory.py --revision HEAD --output docs/testing/sql_inventory_head

Counts query families rather than row values, sort/page combinations or repeated
executions. CSV/JSON include excluded maintenance, demo and transaction operations.
"""
import argparse
import ast
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GIT = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
MODELS = {'Role': 'roles', 'User': 'users', 'Service': 'services', 'ServiceArea': 'service_areas',
          'PriorityLevel': 'priority_levels', 'ServiceRequest': 'service_requests', 'Referral': 'referrals',
          'ReferralStatusHistory': 'referral_status_history', 'OrganizationService': 'organization_services',
          'Notification': 'notifications', 'EventOutbox': 'event_outbox'}
PURPOSES = {
    'auth': 'Resolve verified identity, SQL-owned roles and organization membership without email-only linking.',
    'coordinator': 'Review all requests, organizations, attention cases, dashboard totals and coordinator decisions.',
    'member': 'Read or update an authenticated member profile, owned requests and dashboard statistics.',
    'organization': 'Read or update organization-owned services, referrals, approval status and dashboard totals.',
    'registration': 'Complete verified registration transactionally without role injection or duplicate accounts.',
    'guest_requests': 'Validate catalog/area/time-frame choices and atomically create an owned request and outbox event.',
    'service_browsing': 'Find eligible public services with complete-dataset filters and current-page provider summaries.',
    'matching': 'Choose eligible partners and rank load, acceptance and attendance reliability for primary/backup matching.',
    'referrals': 'Authorize and record an owned referral response while preserving capacity and backup events.',
    'attendance': 'Record first attendance once and verify attendance-target results and recipients.',
    'completions': 'Complete an attended service once and release its reserved capacity transactionally.',
    'feedback': 'Save owned completed-request feedback once and deliver partner/coordinator follow-up notifications.',
    'notifications': 'Deliver in-app alerts to the correct active recipients using stable deduplication keys.',
    'offerings': 'Validate and manage approved-organization offerings, coverage, availability and referral capacity.',
    'organization_approvals': 'Review the latest pending application and authorize idempotent coordinator decisions.',
    'organization_registration': 'Create or recover one verified pending organization application without promoting existing accounts.',
    'member_registration': 'Create or recover one verified member/profile transaction without changing existing details.',
    'organization_status': 'Authorize organization suspension/reactivation while preserving existing application decisions.',
    'organization_profiles': 'Read or update the representative-owned organization contact profile.',
    'member_profiles': 'Validate and update the authenticated member contact profile.',
    'manual_assignment': 'Assign only an eligible partner to an unmatched request without replacing active work or resetting SLA.',
    'cancellations': 'Cancel only an owned waiting request with no active referral or recorded attendance.',
    'outbox': 'Persist business events with mutations and dispatch pending events with confirmed, retryable delivery.',
    'overdue': 'Discover past-target unattended requests and deduplicate coordinator follow-up events/alerts.',
    'timeouts': 'Discover/expire unanswered referrals once, release capacity and schedule the existing backup event.',
    'reports': 'Calculate complete-dataset request/category, approved-partner and helpful-feedback aggregates.',
    'password_sessions': 'Read the authenticated account identity for recent-authentication password changes.',
    'catalog': 'Read active catalog reference choices for existing API contracts.',
    'frontend': 'Load public/request form data and preserve the active template contract.',
}
ACADEMIC_NAMES = [
    'Question 1 Eligible partners by service area and time frame',
    'Question 2 Partner workload and remaining capacity',
    'Question 3 Attendance deadline breaches and responsible referrals',
    'Question 4 Partner referral acceptance decline and timeout statistics',
    'Question 5 Partner on-time attendance rate',
    'Question 6 Community demand by category area and time frame',
    'Question 7 Requests rescued by backup partners',
    'Question 7 detail Primary failure and successful backup history',
    'Question 8 Negative feedback by organization and service',
    'Bonus SDG 17 network impact aggregates',
]


def uncomment(sql):
    """Remove comments without damaging quoted semicolons, hashes or SQL values."""
    result, index, quote = [], 0, None
    while index < len(sql):
        char = sql[index]
        if quote:
            result.append(char)
            if char == '\\' and index + 1 < len(sql):
                index += 1
                result.append(sql[index])
            elif char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 1
                    result.append(sql[index])
                else:
                    quote = None
        elif char in "'\"`":
            quote = char
            result.append(char)
        elif sql.startswith('--', index) or char == '#':
            end = sql.find('\n', index)
            index = len(sql) if end < 0 else end + 1
            result.append('\n')
            continue
        elif sql.startswith('/*', index):
            end = sql.find('*/', index + 2)
            end = len(sql) if end < 0 else end + 2
            result.append('\n' * sql[index:end].count('\n') or ' ')
            index = end
            continue
        else:
            result.append(char)
        index += 1
    return ''.join(result)


def split_sql(source):
    source = uncomment(source)
    source = re.sub(r'(?m)^[ \t]*DELIMITER[ \t]+\S+[^\S\r\n]*(?:\r?\n|$)', '\n', source)
    start, index, quote = 0, 0, None
    while index < len(source):
        char = source[index]
        if quote:
            if char == '\\':
                index += 1
            elif char == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "'\"`":
            quote = char
        elif char == ';' or source.startswith('$$', index):
            segment = source[start:index]
            statement = segment.strip()
            if statement:
                first = start + len(segment) - len(segment.lstrip())
                yield statement, source.count('\n', 0, first) + 1
            width = 2 if source.startswith('$$', index) else 1
            start = index + width
            index += width - 1
        index += 1
    if source[start:].strip():
        yield source[start:].strip(), source.count('\n', 0, start) + 1


def canonical(sql, *, literals=False):
    sql = uncomment(sql)
    if not literals:
        sql = re.sub(r"'(?:''|\\.|[^'])*'|\"(?:\"\"|\\.|[^\"])*\"", '?', sql)
    sql = re.sub(r':\w+|%s|\?', ':value', sql)
    sql = re.sub(r'\bFOR\s+UPDATE(?:\s+SKIP\s+LOCKED)?\b', '', sql, flags=re.I)
    # Sort directions/page sizes are variants of one business query, not extra queries.
    sql = re.sub(r'\s+ORDER\s+BY\s+[^()]*$', '', sql, flags=re.I)
    sql = re.sub(r'\s+LIMIT\s+[^()]*$', '', sql, flags=re.I)
    tokens = re.findall(r"'(?:''|\\.|[^'])*'|\"(?:\"\"|\\.|[^\"])*\"|`[^`]*`|:\w+|[A-Za-z_]\w*|\d+(?:\.\d+)?|<=|>=|<>|!=|\S", sql)
    return ' '.join(token if literals and token.startswith(("'", '"')) else token.lower() for token in tokens).rstrip(' ;')


def sources(revision=None):
    if revision:
        paths = subprocess.check_output(GIT + ['ls-tree', '-r', '--name-only', revision], cwd=ROOT, text=True).splitlines()
    else:
        paths = [path.relative_to(ROOT).as_posix() for folder in ('app', 'database', 'tools', 'deploy')
                 for path in (ROOT / folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts]
        paths += ['teammate_review/dhairya/001_firebase_auth.sql']
    result = {}
    for name in sorted(set(paths)):
        if not (name.endswith('.py') and name.startswith(('app/', 'database/', 'tools/', 'deploy/')) or
                name.endswith('.sql') and (name.startswith('database/') or name == 'teammate_review/dhairya/001_firebase_auth.sql')):
            continue
        if revision:
            result[name] = subprocess.check_output(GIT + ['show', revision + ':' + name], cwd=ROOT).decode('utf-8-sig')
        elif (ROOT / name).is_file():
            result[name] = (ROOT / name).read_text(encoding='utf-8-sig')
    return result


def expression(node, bindings, seen=()):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in bindings and node.id not in seen:
        value = bindings[node.id]
        return value if isinstance(value, str) else expression(value, bindings, seen + (node.id,))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return expression(node.left, bindings, seen) + expression(node.right, bindings, seen)
    if isinstance(node, ast.JoinedStr):
        return ''.join(part.value if isinstance(part, ast.Constant) else '{' + ast.unparse(part.value) + '}' for part in node.values)
    return '{' + ast.unparse(node) + '}'


def operation(sql):
    match = re.match(r'\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|SET|USE|SHOW|CALL)\b', sql, re.I)
    return match.group(1).upper() if match else None


def tables(sql):
    return list(dict.fromkeys(re.findall(r'\b(?:FROM|JOIN|UPDATE|INTO|TABLE)\s+`?([a-z_]\w*)', sql, re.I)))


def orm_key(equivalent):
    """Collapse Python binding names and ordering/lock variants of the same read."""
    primary_keys = dict(Role='role_id', User='user_id', Service='service_id', ServiceArea='area_id',
                        PriorityLevel='priority_id', ServiceRequest='request_id', Referral='referral_id',
                        ReferralStatusHistory='history_id', OrganizationService='organization_service_id',
                        Notification='notification_id', EventOutbox='event_id')

    class Normalize(ast.NodeTransformer):
        def visit_Call(self, node):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in {'order_by', 'limit', 'with_for_update', 'all', 'first', 'one', 'scalar_one_or_none'}:
                    return self.visit(node.func.value)
                if node.func.attr == 'get' and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in MODELS:
                    model = node.args[0].id
                    node = ast.parse(f'select({model}).where({model}.{primary_keys[model]} == _bound)', mode='eval').body
            elif isinstance(node.func, ast.Name) and node.func.id not in {'select', 'and_', 'or_'}:
                return ast.Name(id='_bound', ctx=ast.Load())
            return self.generic_visit(node)

        def visit_Subscript(self, node):
            return ast.Name(id='_bound', ctx=ast.Load())

        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id not in MODELS:
                return ast.Name(id='_bound', ctx=ast.Load())
            return self.generic_visit(node)

        def visit_Name(self, node):
            return node if node.id in MODELS or node.id in {'select', 'and_', 'or_'} else ast.Name(id='_bound', ctx=ast.Load())

        def visit_Constant(self, node):
            return ast.Name(id='_bound', ctx=ast.Load())

    return ast.dump(Normalize().visit(ast.parse(equivalent, mode='eval')), include_attributes=False)


class Inventory:
    def __init__(self):
        self.records = {}
        self.ignored = []

    def add(self, sql, file, line, function='', *, group='Application', equivalent='', note=''):
        kind = operation(sql)
        if not kind:
            self.ignored.append({'source': file, 'line': line, 'expression': equivalent or sql})
            return
        target = tables(sql)
        included = group in {'Application', 'Schema/DDL', 'Seed INSERT', 'Academic demonstration'}
        if group == 'Seed INSERT':
            # Each populated entity counts once, regardless of rows/column variants.
            key = 'seed-insert:' + (target[0] if target else canonical(sql))
        else:
            if kind == 'SELECT' and equivalent and ('select(' in equivalent or '.get(' in equivalent):
                key = group + ':orm:' + orm_key(equivalent)
            else:
                key = group + ':' + canonical(sql, literals=group == 'Schema/DDL')
                # The reviewed teammate migration and migration 002 implement
                # the same UID/null-password change. Column position and an
                # explicit index name do not constitute another query family.
                normalized = canonical(sql, literals=True)
                firebase_versions = {
                    canonical('ALTER TABLE users ADD COLUMN firebase_uid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL UNIQUE, MODIFY COLUMN password_hash VARCHAR(255) NULL', literals=True),
                    canonical('ALTER TABLE users ADD COLUMN firebase_uid VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER email, MODIFY COLUMN password_hash VARCHAR(255) NULL, ADD CONSTRAINT uq_users_firebase_uid UNIQUE (firebase_uid)', literals=True),
                }
                if group == 'Schema/DDL' and normalized in firebase_versions:
                    key = group + ':firebase-uid-migration'
        location = {'file': file, 'line': line, 'function': function,
                    'sql_or_equivalent': equivalent or sql, 'note': note}
        if key in self.records:
            if location not in self.records[key]['sources']:
                self.records[key]['sources'].append(location)
            feature = Path(file).stem + ('.' + function if function else '')
            if feature not in self.records[key]['application_feature'].split('; '):
                self.records[key]['application_feature'] += '; ' + feature
            return
        stem = Path(file).stem
        purpose = PURPOSES.get(stem, 'Support schema validation, synthetic data preparation or maintenance; not counted as active application behavior.')
        if group == 'Schema/DDL':
            purpose = 'Define or strengthen persisted entities, keys, relationships, constraints and indexes.'
        elif group == 'Seed INSERT':
            purpose = 'Populate synthetic ' + ', '.join(target) + ' data; repeated rows and alternate insert forms are one family.'
        elif group == 'Academic demonstration':
            purpose = 'Demonstrate the preserved standalone analytical/operational question; nested subqueries are part of this statement.'
        name = (function.replace('_', ' ') + ': ' if function else '') + kind + (' ' + ', '.join(target) if target else '')
        self.records[key] = {
            'query_fingerprint': hashlib.sha256(key.encode('utf-8')).hexdigest(),
            'query_name': name, 'group': group, 'query_category': ('DQL' if kind == 'SELECT' else 'DML' if kind in {'INSERT','UPDATE','DELETE'} else 'DDL' if kind in {'CREATE','ALTER','DROP'} else 'Control'),
            'operation': kind, 'statement_or_equivalent': equivalent or sql,
            'business_purpose': purpose, 'application_feature': stem + ('.' + function if function else ''),
            'verification_status': 'Static source inventory; consult FINAL_TEST_REPORT.md for executed integration paths',
            'counted': included, 'sources': [location],
        }


def sql_files(data, inventory):
    for file, source in data.items():
        if not file.endswith('.sql'):
            continue
        academic_index = 0
        clean = uncomment(source)
        wrapper = re.search(r'CREATE\s+PROCEDURE[\s\S]*?END\$\$', clean, re.I)
        if wrapper:
            inventory.add(wrapper.group(), file, clean[:wrapper.start()].count('\n') + 1,
                          group='Ancillary/control', note='Routine wrapper is excluded; its table/constraint operations are inventoried once as DDL.')
        for statement, line in split_sql(source):
            kind = operation(statement)
            if kind is None or re.match(r'CREATE\s+PROCEDURE', statement, re.I):
                continue  # Procedure control wrappers are not extra table operations.
            if file == 'database/demo_data.sql' or file.startswith('database/proposals/'):
                group = 'Ancillary/control'
                inventory.add(statement, file, line, group=group,
                              note='Synthetic scenario setup/verification or approval-only schema proposal.')
                continue
            if re.match(r'(CREATE|ALTER)\s+TABLE\b', statement, re.I):
                group = 'Schema/DDL'
            elif kind == 'INSERT':
                group = 'Seed INSERT'
                statement = re.split(r'\bVALUES\b', statement, maxsplit=1, flags=re.I)[0] + ' VALUES (<synthetic values omitted>)'
            elif kind == 'SELECT' and file == 'database/queries.sql':
                group = 'Academic demonstration'
            else:
                group = 'Ancillary/control'
            label = ''
            if group == 'Academic demonstration':
                label = ACADEMIC_NAMES[academic_index] if academic_index < len(ACADEMIC_NAMES) else 'Additional academic query'
                academic_index += 1
            inventory.add(statement, file, line, label, group=group)


def schema_metadata(data):
    entities = {}
    for file, source in data.items():
        if not file.endswith('.sql'):
            continue
        for statement, line in split_sql(source):
            found = re.match(r'CREATE\s+TABLE\s+(\w+)\s*\(', statement, re.I)
            if not found:
                continue
            name = found[1]
            if name in entities:
                entities[name]['source_files'].append(file)
                continue
            columns = [column for column, _ in re.findall(r'(?m)^\s*(\w+)\s+([A-Za-z]+)', statement)
                       if column.upper() not in {'CREATE','CONSTRAINT','PRIMARY','FOREIGN','UNIQUE','INDEX','KEY','CHECK','ON','REFERENCES','CHARACTER','COLLATE'}]
            primary = re.findall(r'(?m)^\s*(\w+)\s+[^\n]*\bPRIMARY\s+KEY\b', statement)
            references = [{'columns': [part.strip() for part in local.split(',')], 'target_table': target,
                           'target_columns': [part.strip() for part in remote.split(',')]}
                          for local,target,remote in re.findall(r'FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+(\w+)\s*\(([^)]+)\)', statement, re.I)]
            entities[name] = {'source_files': [file], 'line': line, 'columns': columns,
                              'primary_key_columns': primary, 'foreign_keys': references}
    invalid = []
    for name, entity in entities.items():
        for reference in entity['foreign_keys']:
            target = entities.get(reference['target_table'])
            if not target or not set(reference['columns']) <= set(entity['columns']) or not set(reference['target_columns']) <= set(target['columns']):
                invalid.append({'table': name, 'reference': reference})
    return {'declared_table_count': len(entities), 'declared_primary_key_count': sum(bool(entity['primary_key_columns']) for entity in entities.values()),
            'declared_foreign_key_count': sum(len(entity['foreign_keys']) for entity in entities.values()),
            'invalid_declared_references': invalid, 'entities': entities,
            'verification_scope': 'Static authoritative DDL review, not an inspection of the live database. Partial ORM mappings are not additional tables.'}


def model_of(node, bindings):
    if isinstance(node, ast.Name) and node.id in bindings:
        return model_of(bindings[node.id], {}) if isinstance(bindings[node.id], ast.AST) else None
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in MODELS:
            return node.func.id
        if isinstance(node.func, ast.Name) and node.func.id == '_lock_request':
            return 'ServiceRequest'
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == 'select':
                if child.args and isinstance(child.args[0], ast.Name) and child.args[0].id in MODELS:
                    return child.args[0].id
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == 'get':
                if child.args and isinstance(child.args[0], ast.Name) and child.args[0].id in MODELS:
                    return child.args[0].id


def python_files(data, inventory):
    parsed = {name: ast.parse(source) for name, source in data.items() if name.endswith('.py')}
    # Resolve SQL-only shared fragments; do not evaluate source code or credentials.
    shared = {}
    for tree in parsed.values():
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id in {'ELIGIBLE_AREAS', 'SERVICE_FROM'}:
                    shared[node.targets[0].id] = node.value
    transactions = {name: [] for name in ('BEGIN', 'COMMIT', 'ROLLBACK')}
    for file, tree in parsed.items():
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for function in [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            nodes = sorted((node for node in ast.walk(function) if hasattr(node, 'lineno')), key=lambda node: (node.lineno, node.col_offset))
            assignments = [node for node in nodes if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)]
            bindings = dict(shared)
            models, updates = {}, {}
            base_group = 'Application' if file.startswith('app/') else 'Seed INSERT' if file == 'database/create_demo_data.py' else 'Ancillary/control'
            if file == 'app/requests.py' and function.name in {'create_request', 'get_requests', 'get_request'}:
                base_group = 'Legacy demonstration'
            for node in nodes:
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name):
                        model = model_of(node.value, bindings)
                        if model:
                            models[target.id] = model
                        # Resolve strings at assignment time, preserving earlier values.
                        if isinstance(node.value, (ast.Constant, ast.BinOp, ast.JoinedStr)):
                            bindings[target.id] = expression(node.value, bindings)
                        else:
                            bindings[target.id] = node.value
                    elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id in models:
                        updates.setdefault(models[target.value.id], []).append((node, target.attr))
                if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Attribute) and isinstance(node.target.value, ast.Name) and node.target.value.id in models:
                    updates.setdefault(models[node.target.value.id], []).append((node, node.target.attr))
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                if name == 'begin' and isinstance(node.func, ast.Attribute):
                    for boundary in transactions:
                        transactions[boundary].append({'file': file, 'line': node.lineno, 'function': function.name})
                elif name in {'commit', 'rollback'} and isinstance(node.func, ast.Attribute):
                    transactions[name.upper()].append({'file': file, 'line': node.lineno, 'function': function.name})
                if name == 'text' and node.args:
                    if function.name in {'page_rows', 'candidate_ids'}:
                        continue  # Concrete caller families are recorded instead.
                    sql = expression(node.args[0], bindings)
                    if not operation(sql):
                        inventory.ignored.append({'source': file, 'line': node.lineno, 'expression': ast.unparse(node)})
                        continue
                    group = base_group
                    if group == 'Seed INSERT' and operation(sql) != 'INSERT':
                        group = 'Ancillary/control'
                    if canonical(sql) == canonical('SELECT 1'):
                        group = 'Ancillary/control'
                    modifiers = [ast.unparse(item) for item in nodes if isinstance(item, ast.AugAssign) and item.lineno <= node.lineno and isinstance(item.target, ast.Name) and item.target.id in {'sql','filters'}]
                    note = 'One SQL template family; optional clauses are not additional queries. ' + '; '.join(modifiers) if modifiers else ''
                    if operation(sql) == 'INSERT' and group == 'Seed INSERT':
                        sql = re.split(r'\bVALUES\b', sql, maxsplit=1, flags=re.I)[0] + ' VALUES (<synthetic values omitted>)'
                    inventory.add(sql, file, node.lineno, function.name, group=group, note=note)
                elif name in {'page_rows', 'candidate_ids'} and isinstance(node.func, ast.Name) and len(node.args) > 1:
                    sql = expression(node.args[1], bindings)
                    inventory.add(sql, file, node.lineno, function.name, group=base_group,
                                  note='Filtered query family; helper adds whitelisted order, bound limit/offset and lookahead. No sort/page variant is counted twice.')
                elif name == 'execute' and node.args and not any(isinstance(part, ast.Call) and isinstance(part.func, ast.Name) and part.func.id == 'text' for part in ast.walk(node.args[0])):
                    value = node.args[0]
                    if any(isinstance(part, ast.Call) and isinstance(part.func, ast.Name) and part.func.id == 'select' for part in ast.walk(value)):
                        equivalent = ast.unparse(value)
                        inventory.add('SELECT ' + equivalent, file, node.lineno, function.name, group=base_group, equivalent=equivalent)
                    elif isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == 'on_duplicate_key_update':
                        definition = next((item.value for item in assignments if isinstance(item.targets[0], ast.Name) and item.targets[0].id == ast.unparse(value.func.value)), None)
                        if definition:
                            equivalent = ast.unparse(definition) + '.' + ast.unparse(value).split('.', 1)[1]
                            inventory.add('INSERT INTO notifications ' + equivalent, file, node.lineno, function.name, group=base_group, equivalent=equivalent)
                elif name == 'query' and isinstance(node.func, ast.Attribute) and 'session' in ast.unparse(node.func.value):
                    outer = node
                    while isinstance(parents.get(outer), ast.Attribute) and isinstance(parents.get(parents[outer]), ast.Call):
                        outer = parents[parents[outer]]
                    equivalent = ast.unparse(outer)
                    inventory.add('SELECT ' + equivalent, file, node.lineno, function.name, group=base_group, equivalent=equivalent)
                elif name == 'get' and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in MODELS:
                    model = node.args[0].id
                    sql = f'SELECT * FROM {MODELS[model]} WHERE <primary key> = :id'
                    inventory.add(sql, file, node.lineno, function.name, group=base_group, equivalent=ast.unparse(node))
                elif name == 'add' and node.args:
                    value = node.args[0]
                    if isinstance(value, ast.Name):
                        value = next((item.value for item in assignments if item.targets[0].id == value.id), value)
                    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in MODELS:
                        model = value.func.id
                        columns = ','.join(sorted(keyword.arg for keyword in value.keywords if keyword.arg))
                        sql = f'INSERT INTO {MODELS[model]} ({columns}) VALUES (<bound values>)'
                        inventory.add(sql, file, node.lineno, function.name, group=base_group,
                                      equivalent=f'{ast.unparse(node)}; object definition: {ast.unparse(value)}')
            for model, changes in updates.items():
                columns = sorted({column for _, column in changes})
                sql = f'UPDATE {MODELS[model]} SET ' + ','.join(column+'=:value' for column in columns) + ' WHERE <loaded primary key>=:id'
                inventory.add(sql, file, changes[0][0].lineno, function.name, group=base_group,
                              equivalent='SQLAlchemy dirty-object flush/commit: ' + '; '.join(ast.unparse(node) for node, _ in changes),
                              note='One ORM update family per entity/field set; branch values are not separate statements.')
    for name, equivalent in [('BEGIN', 'with session.begin(): or engine.begin(): establishes a transaction'),
                             ('COMMIT', 'successful transaction context exit or explicit session.commit()'),
                             ('ROLLBACK', 'failed transaction context exit or explicit session.rollback()')]:
        if not transactions[name]:
            continue
        inventory.records['transaction:' + name] = {
            'query_fingerprint': hashlib.sha256(('transaction:' + name).encode('utf-8')).hexdigest(),
            'query_name': name + ' transaction boundary', 'group': 'Transaction control', 'query_category': 'TCL',
            'operation': name, 'statement_or_equivalent': equivalent,
            'business_purpose': 'Keep related business mutations, capacity changes and outbox writes atomic.',
            'application_feature': 'Transactional workflow integrity', 'verification_status': 'Source boundary inventory; selected rollback/replay/locking paths verified on isolated MySQL, not every listed execution path',
            'counted': False, 'sources': transactions[name],
        }


def build(data):
    inventory = Inventory()
    sql_files(data, inventory)
    python_files(data, inventory)
    records = sorted(inventory.records.values(), key=lambda row: (row['group'], row['sources'][0]['file'], row['sources'][0]['line'], row['query_name']))
    for number, record in enumerate(records, 1):
        record['query_number'] = f'Q{number:03}'
    counts = Counter(row['group'] for row in records if row['counted'])
    qualifying = [row for row in records if row['counted']]
    shapes = {
        'JOIN': r'\bJOIN\b|\.join\(',
        'aggregate': r'\b(?:COUNT|SUM|AVG|MIN|MAX|GROUP_CONCAT)\s*\(',
        'GROUP BY': r'\bGROUP\s+BY\b|\.group_by\(',
        'HAVING': r'\bHAVING\b|\.having\(',
        'subquery': r'\(\s*SELECT\b|\.subquery\(',
    }
    return {'counting_method': 'Distinct conservative statement/template families; duplicate schemas, repeated seed rows and sort/page executions are not additional queries. Maintenance/control, legacy demos and transaction boundaries are listed but excluded from the meaningful total.',
            'totals': dict(counts), 'total_distinct_meaningful_statements': sum(counts.values()),
            'meaningful_application_queries': counts.get('Application', 0),
            'qualifying_operation_totals': dict(Counter(row['operation'] for row in qualifying)),
            'overlapping_query_shape_totals': {name: sum(bool(re.search(pattern, row['statement_or_equivalent'], re.I)) for row in qualifying) for name, pattern in shapes.items()},
            'total_inventory_families_including_exclusions': len(records),
            'source_text_sha256': {name: hashlib.sha256(source.encode('utf-8')).hexdigest() for name, source in sorted(data.items())},
            'excluded_totals': dict(Counter(row['group'] for row in records if not row['counted'])),
            'unresolved_expressions': inventory.ignored, 'schema_review': schema_metadata(data), 'queries': records}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision')
    parser.add_argument('--output', default='docs/testing/sql_inventory')
    args = parser.parse_args(argv)
    result = build(sources(args.revision))
    result['source_revision'] = args.revision or 'working tree'
    result['head_commit'] = subprocess.check_output(GIT + ['rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    fields = ['query_number','query_name','source_file','sql_statement_or_sqlalchemy_equivalent','query_category','inventory_group','business_purpose','application_feature','verification_status','counted','variants_and_optional_clauses']
    with output.with_suffix('.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in result['queries']:
            writer.writerow(dict(zip(fields, [row['query_number'], row['query_name'],
                '; '.join(f"{location['file']}:{location['line']} ({location.get('function','')})" for location in row['sources']),
                row['statement_or_equivalent'],row['query_category'],row['group'],row['business_purpose'],
                row['application_feature'],row['verification_status'],row['counted'],
                '; '.join(dict.fromkeys(location.get('note','') for location in row['sources'] if location.get('note')))])))
    print(json.dumps({key: result[key] for key in ('source_revision','totals','total_distinct_meaningful_statements','meaningful_application_queries','total_inventory_families_including_exclusions','excluded_totals')}, indent=2))
    print('Unresolved helper expressions:', len(result['unresolved_expressions']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
