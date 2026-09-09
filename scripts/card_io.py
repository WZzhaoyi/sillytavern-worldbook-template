#!/usr/bin/env python3
"""Lossless PNG/JSON inspection and explicitly mapped entry recovery. Never executes scripts."""
import argparse
import base64
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

SIGNATURE = b'\x89PNG\r\n\x1a\n'


def png_chunks(raw):
    if not raw.startswith(SIGNATURE):
        raise ValueError('Not a PNG')
    offset = 8
    ended = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ValueError('Truncated PNG chunk')
        size = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        data = raw[offset + 8:offset + 8 + size]
        end = offset + size + 12
        if end > len(raw) or zlib.crc32(kind + data) & 0xffffffff != struct.unpack('>I', raw[end - 4:end])[0]:
            raise ValueError('Invalid PNG length or CRC')
        yield kind, data
        offset = end
        if kind == b'IEND':
            ended = True
            break
    if not ended:
        raise ValueError('PNG missing IEND')


def text_chunk(kind, data):
    if kind == b'tEXt':
        return data.split(b'\0', 1)
    if kind == b'zTXt':
        key, value = data.split(b'\0', 1)
        if value[0] != 0:
            raise ValueError('Unknown PNG compression')
        return key, zlib.decompress(value[1:])
    if kind == b'iTXt':
        key, value = data.split(b'\0', 1)
        flag, method = value[:2]
        if method != 0 or flag not in (0, 1):
            raise ValueError('Invalid international PNG text')
        _, _, text = value[2:].split(b'\0', 2)
        return key, zlib.decompress(text) if flag else text
    return None, None


def read_card(path):
    raw = Path(path).read_bytes()
    if not raw.startswith(SIGNATURE):
        return json.loads(raw)
    payloads = {}
    for kind, data in png_chunks(raw):
        key, value = text_chunk(kind, data)
        if key in (b'chara', b'ccv3'):
            payload = json.loads(base64.b64decode(value, validate=True))
            if key in payloads and payloads[key] != payload:
                raise ValueError(f'Conflicting duplicate card metadata: {key}')
            payloads[key] = payload
    if not payloads:
        raise ValueError('PNG has no chara/ccv3 data')
    return payloads.get(b'ccv3', payloads.get(b'chara'))


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def write_card_png(cover, card, output):
    chunks = list(png_chunks(Path(cover).read_bytes()))
    result = bytearray(SIGNATURE)
    for kind, data in chunks:
        key, _ = text_chunk(kind, data)
        if key in (b'chara', b'ccv3'):
            continue
        if kind == b'IEND':
            legacy = {**card, 'spec': 'chara_card_v2', 'spec_version': '2.0'}
            for keyword, payload in ((b'chara', legacy), (b'ccv3', card)):
                result.extend(chunk(b'tEXt', keyword + b'\0' + base64.b64encode(json.dumps(payload, ensure_ascii=False).encode())))
        result.extend(chunk(kind, data))
    Path(output).write_bytes(result)


def card_entries(card):
    entries = card.get('data', card).get('character_book', card).get('entries', [])
    return list(entries.values()) if isinstance(entries, dict) else entries


def normalize_entry(entry):
    """Preserve original extra keys, map card-book wire names to standalone lorebook names."""
    result = dict(entry.get('extensions') or {})
    result.update(entry)
    for old, new in [('keys', 'key'), ('secondary_keys', 'keysecondary'), ('insertion_order', 'order')]:
        if old in entry:
            result[new] = entry[old]
    result['comment'] = entry.get('comment') or entry.get('name') or str(entry.get('id', entry.get('uid', '')))
    if 'enabled' in entry:
        result['disable'] = not entry['enabled']
    if isinstance(entry.get('position'), str):
        result['position'] = (entry.get('extensions') or {}).get('position', {'before_char': 0, 'after_char': 1}.get(entry['position'], 0))
    result.setdefault('key', [])
    result.setdefault('keysecondary', [])
    return result


def inspect_card(source):
    card = read_card(source)
    entries = card_entries(card)
    titles = {e.get('comment') or e.get('name') for e in entries}
    report = []
    for index, entry in enumerate(entries):
        text = entry.get('content', '')
        title = entry.get('comment') or entry.get('name') or ''
        refs = re.findall(r'getwi\([^,]*,\s*[\'"]([^\'"]+)', text)
        kind = 'runtime' if '[mvu' in title or '[initvar]' in title else 'character' if '<character' in text else 'relationship' if title.startswith('关系_') else 'unknown'
        report.append({'index': index, 'source_id': entry.get('id', entry.get('uid')), 'title': title,
                       'enabled': entry.get('enabled', not entry.get('disable', False)),
                       'suggested_category': kind, 'references': refs, 'missing_references': [r for r in refs if r not in titles],
                       'category': None, 'entry': entry})
    return {'source': str(Path(source).resolve()), 'sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'card': card, 'entries': report,
            'instructions': 'Review every category: character/setting/relationship/raw/runtime/archive. Runtime and archive entries stay in original data only. Scripts and regexes remain archived and are not activated.'}


def restore(report, work):
    categories = {'character', 'setting', 'relationship', 'raw', 'runtime', 'archive'}
    if any(row.get('category') not in categories for row in report['entries']):
        raise ValueError('Review and fill every entry category before restore')
    # A deliberately new destination prevents overwriting authored or previously recovered assets.
    target = Path(work) / 'literature/imported'
    if target.exists():
        raise ValueError(f'Recovery destination already exists: {target}')
    target.mkdir(parents=True)
    (target / 'original-card.json').write_text(json.dumps(report['card'], ensure_ascii=False, indent=2), encoding='utf-8')
    (target / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    entries = [normalize_entry(row['entry']) for row in report['entries'] if row['category'] not in ('runtime', 'archive')]
    (target / 'entries.json').write_text(json.dumps({'entries': entries}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Recovered verbatim entries. Enable with imports.entries: ["literature/imported/entries.json"] in config.yaml.')
    print('Original narrator, greetings, scripts and regexes are archived in original-card.json for explicit manual migration.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('source', type=Path)
    inspect.add_argument('--output', required=True, type=Path)
    recover = commands.add_parser('restore')
    recover.add_argument('review', type=Path)
    recover.add_argument('--work', required=True, type=Path)
    pack = commands.add_parser('pack')
    pack.add_argument('--card', required=True, type=Path)
    pack.add_argument('--cover', required=True, type=Path)
    pack.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if getattr(args, 'output', None) and args.output.exists():
        parser.error('Output already exists; choose a new destination')
    try:
        if args.command == 'inspect':
            args.output.write_text(json.dumps(inspect_card(args.source), ensure_ascii=False, indent=2), encoding='utf-8')
        elif args.command == 'restore':
            restore(json.loads(args.review.read_text(encoding='utf-8')), args.work)
        else:
            write_card_png(args.cover, read_card(args.card), args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
