from __future__ import annotations

import logging
import sys
from argparse import ArgumentParser
from pathlib import Path

from .loader import Loader
from .assembler import Assembler
from .renderer import Renderer


def main():
    parser = ArgumentParser(
        description='Generate an OGC standards document from Building Blocks'
    )
    parser.add_argument(
        '--register', required=True, metavar='REGISTER_JSON',
        help='Path to compiled register.json (e.g. build-local/register.json)',
    )
    parser.add_argument(
        '--prefix', default=None, metavar='PREFIX',
        help='BB identifier prefix to select a standard (required when register contains multiple)',
    )
    parser.add_argument(
        '--build-dir', default='build/standard', metavar='DIR',
        help='Output directory (default: build/standard)',
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
    extra_registers = [Path(p) for p in args.extra_register]

    if not register_path.exists():
        print(f"ERROR: register.json not found: {register_path}", file=sys.stderr)
        sys.exit(1)

    loader = Loader(register_path, prefix=args.prefix, extra_registers=extra_registers)
    metadata, clauses, resolver = loader.load()

    assembler = Assembler(metadata, clauses, resolver)
    doc = assembler.assemble()

    templates_dir = Path(__file__).parent.parent.parent / 'templates'
    renderer = Renderer(resolver, templates_dir)
    renderer.render(doc, build_dir)

    print(f"Generated: {build_dir / 'index.html'}")


if __name__ == '__main__':
    main()
