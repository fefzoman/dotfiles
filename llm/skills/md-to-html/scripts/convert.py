"""Convert trusted local lessons with an approved lesson UI; never overwrite output."""

import argparse
from collections import Counter
from html import escape
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from markdown_it import MarkdownIt


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.ids = []
        self.refs = []
        self.image = None
        self.tags = []

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        key = 'href' if tag in ('a', 'link') else 'src' if tag in ('img', 'script') else None
        if key and attrs.get(key):
            self.refs.append(attrs[key])
        if tag == 'img':
            self.image = attrs


def document(html):
    parsed = Document()
    parsed.feed(html)
    return parsed


def text(html):
    return re.sub(r'\s+', ' ', ''.join(document(html).text)).strip()


def heading_ids(tokens, renderer):
    counts = Counter()
    for index, token in enumerate(tokens):
        if token.type != 'heading_open':
            continue
        base = re.sub(r'[^\w\- ]', '', text(renderer.renderInline(tokens[index + 1].content)).lower()).replace(' ', '-')
        identifier = base if not counts[base] else f'{base}-{counts[base]}'
        counts[base] += 1
        token.attrSet('id', identifier)


def figures(html):
    lines = []
    for line in html.splitlines(keepends=True):
        candidate = line.strip()
        if candidate.startswith('<p>') and candidate.endswith('</p>'):
            candidate = candidate[3:-4]
        if candidate.startswith('<img'):
            parsed = document(candidate)
            if parsed.tags == ['img'] and parsed.image.get('src'):
                image = parsed.image
                alt = escape(image.get('alt', ''), quote=True)
                src = escape(image['src'], quote=True)
                line = f'<figure><a href="{src}" aria-label="View full image: {alt}">{candidate}</a><figcaption>{alt}</figcaption></figure>\n'
        lines.append(line)
    return ''.join(lines)


def convert(source, md, head, header, sidebar, first_page, neighbors):
    original = source.read_text()
    tokens = md.parse(original)
    if not tokens or tokens[0].type != 'heading_open' or tokens[0].tag != 'h1':
        raise ValueError(f'{source}: expected a level-one title at the start; inspect front matter or unsupported syntax')
    title = tokens[1].content
    tokens = tokens[3:]
    heading_ids(tokens, md)
    boundaries = [i for i, token in enumerate(tokens) if token.type == 'heading_open' and token.tag in ('h1', 'h2')]
    intro = figures(md.renderer.render(tokens[:boundaries[0]], md.options, {})) if boundaries else ''
    sections = []
    navigation = []
    for number, start in enumerate(boundaries, 1):
        end = boundaries[number] if number < len(boundaries) else len(tokens)
        identifier = tokens[start].attrGet('id')
        label = md.renderInline(tokens[start + 1].content)
        navigation.append(f'<li><a href="#{identifier}"><span>{number:02}</span>{label}</a></li>')
        body = figures(md.renderer.render(tokens[start + 3:end], md.options, {}))
        sections.append(f'<section class="chapter" aria-labelledby="{identifier}"><h2 id="{identifier}">{label}</h2>{body}</section>')
    if not sections:
        navigation = ['<li><a href="#article-body">Overview</a></li>']
        sections = [f'<section class="chapter" id="article-body">{figures(md.renderer.render(tokens, md.options, {}))}</section>']
    article = intro + ''.join(sections)
    article = re.sub(r'<table>(.*?)</table>', r'<div class="table-scroll" role="region" aria-label="Reference table" tabindex="0"><table>\1</table></div>', article, flags=re.S)
    article = re.sub(r'<li>\[ \] (.*?)</li>', r'<li><label><input type="checkbox"> \1</label></li>', article)
    page_head = re.sub(r'<title>.*?</title>', lambda _: f'<title>{escape(text(md.renderInline(title)))}</title>', head, count=1, flags=re.S)
    page_head = re.sub(r'<meta name="description"[^>]*>', lambda _: f'<meta name="description" content="{escape(text(md.renderInline(title)), quote=True)}">', page_head, count=1)
    page_header = re.sub(r'(class="brand" href=")[^"]+', lambda match: match[1] + first_page, header, count=1)
    edition = re.match(r'\d+', source.stem)
    page_header = re.sub(r'A practical guide · Lesson \d+', f'A practical guide · Lesson {edition[0]}' if edition else 'A practical guide', page_header)
    footer = '<footer class="footer">'
    for name, label in neighbors:
        footer += f'<a href="{escape(name, quote=True)}">{label}</a>'
    footer += '<a href="#main">Back to top ↑</a></footer>'
    html = f'''<!doctype html>
<html lang="en"><head>{page_head}</head><body><a class="skip" href="#main">Skip to lesson</a>{page_header}
<div class="layout"><aside>{sidebar}<nav id="lesson-menu" aria-label="Lesson sections"><ol>{''.join(navigation)}</ol></nav></aside>
<main id="main"><header class="hero"><h1>{md.renderInline(title)}</h1></header>{article}{footer}</main></div></body></html>'''
    codes = lambda value: re.findall(r'<pre><code[^>]*>(.*?)</code></pre>', value, re.S)
    rendered = md.render(original)
    if codes(rendered) != codes(html):
        raise ValueError(f'{source}: code preservation failed')
    output_text = text(html)
    for paragraph in re.findall(r'<p>(.*?)</p>', rendered, re.S):
        if text(paragraph) not in output_text:
            raise ValueError(f'{source}: paragraph preservation failed: {text(paragraph)[:100]}')
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--template', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--trusted-html', action='store_true', help='Preserve raw HTML only for trusted source documents')
    args = parser.parse_args()
    sources = [path.resolve() for path in args.sources]
    output = args.output_dir.resolve()
    if len({path.parent for path in sources}) != 1 or len(set(sources)) != len(sources):
        parser.error('Sources must be distinct sibling Markdown files, in the desired lesson order')
    if any(path.suffix.lower() != '.md' for path in sources):
        parser.error('Only Markdown source files are supported')
    if output.exists():
        parser.error('Output directory already exists; choose a new destination and review before replacing files')
    template = args.template.resolve()
    shell = template.read_text()
    head = re.search(r'<head>(.*?)</head>', shell, re.S)
    header = re.search(r'<header class="site-header">.*?</header>', shell, re.S)
    sidebar = re.search(r'<aside>(.*?)<nav ', shell, re.S)
    if not all((head, header, sidebar)):
        parser.error('Template must contain the approved lesson head, site header, and sidebar')
    md = MarkdownIt('commonmark', {'html': args.trusted_html}).enable('table')
    names = {path.name: path.with_suffix('.html').name for path in sources}
    plans = {}
    for index, source in enumerate(sources):
        neighbors = []
        if index:
            neighbors.append((sources[index - 1].with_suffix('.html').name, '← Previous lesson'))
        if index + 1 < len(sources):
            neighbors.append((sources[index + 1].with_suffix('.html').name, 'Next lesson →'))
        html = convert(source, md, head[1], header[0], sidebar[1], sources[0].with_suffix('.html').name, neighbors)
        def rewrite(match):
            url = urlsplit(match[1])
            relative = Path(unquote(url.path))
            key = relative.as_posix()
            if not url.scheme and not url.netloc and not relative.is_absolute() and key in names:
                return 'href="' + urlunsplit(('', '', quote(names[key]), url.query, url.fragment)) + '"'
            return match[0]
        html = re.sub(r'href="([^"]*)"', rewrite, html)
        plans[source.with_suffix('.html').name] = html
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='markdown-html-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'site'
        staged.mkdir()
        parsed = {name: document(html) for name, html in plans.items()}
        template_refs = set(document(head[1]).refs)
        for name, html in plans.items():
            (staged / name).write_text(html)
            page = parsed[name]
            if len(page.ids) != len(set(page.ids)):
                raise ValueError(f'{name}: duplicate heading IDs')
            for ref in page.refs:
                url = urlsplit(ref)
                if url.scheme or url.netloc:
                    continue
                path = unquote(url.path)
                if path and path not in plans:
                    relative = Path(path)
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError(f'{name}: resource escapes output directory: {ref}')
                    origin = template.parent if ref in template_refs else sources[0].parent
                    resource = (origin / relative).resolve()
                    if not resource.is_relative_to(origin):
                        raise ValueError(f'{name}: resource resolves outside its source directory: {ref}')
                    destination = staged / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if not destination.exists():
                        shutil.copy2(resource, destination)
                target = path or name
                if target in parsed and url.fragment and unquote(url.fragment) not in parsed[target].ids:
                    raise ValueError(f'{name}: unresolved fragment: {ref}')
        os.rename(staged, output)
    print(f'Converted {len(plans)} documents to {output}; source paragraphs and code preserved.')


if __name__ == '__main__':
    main()
