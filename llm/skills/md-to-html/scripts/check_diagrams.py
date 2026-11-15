"""Check inline diagram structure without a browser or third-party dependencies."""

import argparse
from collections import Counter
from html.parser import HTMLParser
from itertools import accumulate
from pathlib import Path
import re
import xml.etree.ElementTree as ET


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.offsets = [0, *accumulate(map(len, source.splitlines(keepends=True)))]
        self.ids = []
        self.svgs = []
        self.figures = []
        self.svg_depth = self.figure_depth = 0
        self.feed(source)
        self.close()
        if self.svg_depth or self.figure_depth:
            raise ValueError('Unclosed SVG or figure')

    def source_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'figure':
            if not self.figure_depth:
                self.figure_start = self.source_offset()
            self.figure_depth += 1
        if tag == 'svg':
            if not self.svg_depth:
                self.svg_start = self.source_offset()
                self.is_diagram = attrs.get('aria-hidden') != 'true' and attrs.get('role') not in ('presentation', 'none')
            self.svg_depth += 1

    def handle_endtag(self, tag):
        if tag == 'svg':
            if not self.svg_depth:
                raise ValueError('Unexpected closing SVG')
            self.svg_depth -= 1
            if not self.svg_depth and self.is_diagram:
                end = self.source.index('>', self.source_offset()) + 1
                self.svgs.append(self.source[self.svg_start:end])
        if tag == 'figure':
            if not self.figure_depth:
                raise ValueError('Unexpected closing figure')
            self.figure_depth -= 1
            if not self.figure_depth:
                self.figures.append((self.figure_start, self.source.index('>', self.source_offset()) + 1))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ('svg', 'figure'):
            self.handle_endtag(tag)

    def outside_figures(self):
        parts = []
        end = 0
        for start, stop in self.figures:
            parts.extend((self.source[end:start], '<figure/>'))
            end = stop
        return ''.join(parts) + self.source[end:]


def check(path, before=None):
    doc = Document(path.read_text())
    duplicates = [identifier for identifier, count in Counter(doc.ids).items() if count > 1]
    if duplicates:
        raise ValueError(f'Duplicate document IDs: {duplicates}')
    ids = set(doc.ids)
    for markup in doc.svgs:
        root = ET.fromstring(markup)
        children = {child.tag.rsplit('}', 1)[-1]: child for child in root}
        for name in ('title', 'desc'):
            if name not in children or not ''.join(children[name].itertext()).strip():
                raise ValueError(f'Diagram needs a nonempty SVG {name}')
        labelled = root.get('aria-labelledby', '').split()
        if root.get('role') != 'img' or not labelled or children['title'].get('id') not in labelled:
            raise ValueError('Diagram needs role="img" and aria-labelledby referencing its title')
        described = labelled + root.get('aria-describedby', '').split()
        if children['desc'].get('id') not in described:
            raise ValueError('Diagram description must be referenced by aria-labelledby or aria-describedby')
        for element in root.iter():
            refs = element.get('aria-labelledby', '').split() + element.get('aria-describedby', '').split()
            for value in element.attrib.values():
                refs.extend(re.findall(r'url\(\s*[\'"]?#([^\s)\'";]+)', value))
            for name, value in element.attrib.items():
                if name.rsplit('}', 1)[-1] == 'href' and value.startswith('#'):
                    refs.append(value[1:])
            if element.tag.rsplit('}', 1)[-1] == 'style':
                refs.extend(re.findall(r'url\(\s*[\'"]?#([^\s)\'";]+)', ''.join(element.itertext())))
            missing = set(refs) - ids
            if missing:
                raise ValueError(f'Unresolved SVG references: {sorted(missing)}')
    if before:
        original = Document(before.read_text())
        if original.outside_figures() != doc.outside_figures():
            raise ValueError('Content outside figure bodies changed')
    return len(doc.svgs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pages', nargs='+', type=Path)
    parser.add_argument('--before-dir', type=Path, help='Compare same-named snapshots for figure-only edits')
    args = parser.parse_args()
    if args.before_dir and len({page.name for page in args.pages}) != len(args.pages):
        parser.error('Snapshot comparison requires distinct page filenames')
    total = 0
    for page in args.pages:
        try:
            count = check(page, args.before_dir / page.name if args.before_dir else None)
        except (OSError, ValueError, ET.ParseError) as error:
            parser.exit(1, f'{page}: {error}\n')
        total += count
        print(f'PASS: {page}: {count} SVG diagrams; IDs, accessibility and local SVG references checked.')
    print(f'Checked {total} diagrams in {len(args.pages)} pages. Layout, contrast and semantic accuracy still require review.')


if __name__ == '__main__':
    main()
