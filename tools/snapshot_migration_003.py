"""Read-only row fingerprints for the migration 003 maintenance checklist."""
import hashlib
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine, inspect, select, text


def snapshot(engine):
    result = {'tables': {}}
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        inspector = inspect(connection)
        metadata = MetaData()
        metadata.reflect(bind=connection)
        result['legacy_flag_present'] = 'is_backup' in metadata.tables['referrals'].c
        if result['legacy_flag_present']:
            result['legacy_flag_mismatches'] = connection.execute(text(
                'SELECT COUNT(*) FROM referrals WHERE NOT (is_backup <=> (attempt_number > 1))'
            )).scalar_one()
        for name in sorted(inspector.get_table_names()):
            table = metadata.tables[name]
            columns = [column for column in table.columns
                       if (name, column.name) != ('referrals', 'is_backup')]
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute(select(*columns).order_by(*table.primary_key.columns)):
                digest.update((json.dumps(list(row), default=str, ensure_ascii=False, sort_keys=True) + '\n').encode())
                count += 1
            result['tables'][name] = {'count': count, 'sha256': digest.hexdigest()}
    return result


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    engine = None
    try:
        engine = create_engine(os.environ['DATABASE_URL'], hide_parameters=True)
        print(json.dumps(snapshot(engine), sort_keys=True))
    except Exception as error:
        print('Snapshot failed (' + type(error).__name__ + ')', file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
