from __future__ import annotations

import json
import logging
import sys
from argparse import ArgumentParser
from pathlib import Path

from .generate import DEFAULT_BUILD_DIR, DEFAULT_STANDARDS_FILE, generate, load_standards


def main():
    parser = ArgumentParser(
        description='Generate an OGC standards document from Building Blocks'
    )
    parser.add_argument(
        '--register', required=True, metavar='REGISTER_JSON',
        help='Path to compiled register.json (e.g. build-local/register.json)',
    )
    parser.add_argument(
        '--standards-file', default=None, metavar='STANDARDS_YAML',
        help=f'Standards definitions (default: {DEFAULT_STANDARDS_FILE} in the repo root)',
    )
    parser.add_argument(
        '--root-dir', default=None, metavar='DIR',
        help='Repo root (default: the parent of the register.json directory)',
    )
    parser.add_argument(
        '--only', action='append', default=[], metavar='ID',
        help='Generate only this standard id (repeatable; default: all)',
    )
    parser.add_argument(
        '--build-dir', default=DEFAULT_BUILD_DIR, metavar='DIR',
        help=f'Output directory (default: {DEFAULT_BUILD_DIR})',
    )
    parser.add_argument(
        '--extra-register', action='append', default=[], metavar='REGISTER_JSON',
        help='Additional compiled register.json files to import',
    )
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='Enable debug logging',
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(levelname)s %(name)s: %(message)s',
    )

    register_path = Path(args.register)
    build_dir = Path(args.build_dir)

    if not register_path.exists():
        print(f"ERROR: register.json not found: {register_path}", file=sys.stderr)
        sys.exit(1)

    register = json.loads(register_path.read_text())
    source_dir = Path(args.root_dir) if args.root_dir else register_path.parent.parent  # build-local/ → repo root
    standards = load_standards(
        Path(args.standards_file) if args.standards_file else source_dir / DEFAULT_STANDARDS_FILE
    )
    extra_registers = [json.loads(Path(p).read_text()) for p in args.extra_register]

    out = generate(
        register,
        standards,
        source_dir=source_dir,
        build_dir=build_dir,
        only=args.only,
        extra_registers=extra_registers,
    )

    print(f"Generated: {out}")


if __name__ == '__main__':
    main()
