"""키 없이 코드·웹·일관된 장서 snapshot을 배포 폴더에 준비합니다."""
import argparse
from pathlib import Path
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'work/data/catalog.sqlite3')
    parser.add_argument('--output', type=Path, default=ROOT / 'work/deploy-preview/production')
    args = parser.parse_args()
    target = args.output.resolve()
    if not target.is_relative_to(ROOT / 'work') or target == ROOT / 'work':
        parser.error('배포 폴더는 저장소의 work 하위여야 합니다.')
    if target.exists():
        parser.error('기존 파일 보호를 위해 새 배포 폴더를 지정하세요.')
    source = args.catalog.resolve()
    if not source.is_file():
        parser.error('완성된 장서 DB 파일이 필요합니다.')
    target.mkdir(parents=True)
    for directory in ('app', 'web', 'data'):
        for path in (ROOT / directory).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            if directory == 'app' and path.suffix != '.py':
                continue
            if directory == 'data' and path.name != 'README.md':
                continue
            destination = target / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    for name in ('Dockerfile', '.dockerignore', 'railway.json', 'server.py', 'requirements.txt'):
        shutil.copyfile(ROOT / name, target / name)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(target / 'data/catalog.sqlite3') as backup:
            original.backup(backup)
            if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('장서 snapshot 검증 실패')
    print(f'Prepared: {target}')


if __name__ == '__main__':
    main()
