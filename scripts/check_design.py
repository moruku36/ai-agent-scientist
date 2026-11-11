#!/usr/bin/env python3
"""Offline documentation/JSON-shape checks, never scientific runtime acceptance."""
import copy
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
FORMATS = FormatChecker()


@FORMATS.checks('date-time', raises=ValueError)
def check_datetime(value):
    # jsonschema's optional RFC3339 dependency is absent in some offline setups.
    # This profile accepts ordinary RFC3339 instants, not leap-second notation.
    if not isinstance(value, str):
        return True
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})', value):
        return False
    if value[-1] not in 'Zz' and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        return False
    datetime.fromisoformat(value.upper().replace('Z', '+00:00'))
    return True


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite JSON number: {value}")
    return result


def parse_json(text):
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=reject_constant, parse_float=finite_float)


def read_json(path):
    return parse_json(path.read_text())


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def check():
    for malformed in ('{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}', '{"x": 1e999}'):
        try:
            parse_json(malformed)
        except ValueError:
            pass
        else:
            raise AssertionError('Unsafe JSON parser input accepted')
    print('PASS: duplicate-key and 3 non-finite JSON parser negatives rejected')
    validators = {}
    for path in sorted((ROOT / 'schemas').glob('*.schema.json')):
        schema = read_json(path)
        for node in walk(schema):
            if isinstance(node, dict) and '$ref' in node:
                assert node['$ref'].startswith('#/'), f"Non-local $ref: {path}"
        Draft202012Validator.check_schema(schema)
        validators[path.stem.removesuffix('.schema')] = Draft202012Validator(
            schema, format_checker=FORMATS)
    print(f"PASS: {len(validators)} schema definitions (local references only)")

    mapping = {'cpu-pilot.json': 'experiment-plan',
               'evaluation-protocol.synthetic.json': 'evaluation-protocol',
               'handoff.synthetic.json': 'handoff',
               'verification-contract.synthetic.json': 'verification-contract',
               'verification-report.synthetic.json': 'verification-report'}
    fixtures = {}
    paths = sorted((ROOT / 'examples').glob('*.json'))
    assert {p.name for p in paths} == set(mapping), 'Update explicit fixture map'
    for path in paths:
        data = read_json(path)
        name = mapping[path.name]
        validators[name].validate(data)
        fixtures[name] = data
        if 'enabled' in data:
            assert data['enabled'] is False, f"Active example: {path}"
        if 'synthetic' in data:
            assert data['synthetic'] is True, f"Non-synthetic example: {path}"
    # The legacy run-record has no on-disk example: check a minimal inactive shape.
    run = dict(run_id='synthetic', attempt_id='synthetic', replicate_id='synthetic',
               project_id='synthetic', protocol_revision='synthetic',
               candidate_revision='synthetic', status='partial', validity='unchecked',
               artifacts=[], metrics={'score': None},
               usage={'wall_seconds': None, 'incremental_api_usd': None},
               limitations=['Shape fixture; no execution.'])
    validators['run-record'].validate(run)
    fixtures['run-record'] = run
    print(f"PASS: {len(paths)} inert JSON examples and 1 in-memory legacy run shape")

    # The initial adapter is empirical; formal evidence may be absent when a
    # check is incomplete. Neither positive shape test authenticates a result.
    empirical_contract = copy.deepcopy(fixtures['verification-contract'])
    empirical_contract['claim_obligations'] = [empirical_contract['claim_obligations'][1]]
    del empirical_contract['formal_policy']
    validators['verification-contract'].validate(empirical_contract)
    empirical_report = copy.deepcopy(fixtures['verification-report'])
    empirical_report['claims'] = [empirical_report['claims'][1]]
    validators['verification-report'].validate(empirical_report)
    incomplete = copy.deepcopy(fixtures['verification-report'])
    incomplete['claims'][0].pop('formal_evidence', None)
    validators['verification-report'].validate(incomplete)
    print('PASS: empirical-only contract/report and incomplete formal report shapes')

    mutations = 0

    def rejected(name, data):
        nonlocal mutations
        assert not validators[name].is_valid(data), f"Accepted negative shape: {name}, mutation {mutations + 1}"
        mutations += 1

    for name, fixture in fixtures.items():
        changed = copy.deepcopy(fixture)
        changed.pop(next(iter(changed)))
        rejected(name, changed)
        changed = copy.deepcopy(fixture)
        changed['unexpected_field'] = True
        rejected(name, changed)
    changed = copy.deepcopy(fixtures['verification-contract'])
    del changed['formal_policy']
    rejected('verification-contract', changed)
    changed = copy.deepcopy(fixtures['verification-contract'])
    changed['specification']['sha256'] = 'not-a-hash'
    rejected('verification-contract', changed)
    changed = copy.deepcopy(fixtures['verification-report'])
    changed['synthetic'] = False
    changed['claims'][0]['outcome'] = 'passed'
    changed['claims'][0]['evidence'] = [copy.deepcopy(changed['candidate'])]
    changed['claims'][0].pop('formal_evidence', None)
    rejected('verification-report', changed)
    changed = copy.deepcopy(fixtures['verification-report'])
    changed['issued_at'] = '2000-99-01T00:00:00Z'
    rejected('verification-report', changed)
    changed = copy.deepcopy(fixtures['verification-report'])
    changed['outcome'] = 'passed'
    rejected('verification-report', changed)
    changed = copy.deepcopy(fixtures['verification-report'])
    changed['synthetic'] = False
    changed['outcome'] = 'passed'
    rejected('verification-report', changed)
    print(f"PASS: {mutations} negative schema mutations rejected")

    links = pairs = 0
    markdown = sorted(ROOT.glob('*.md'))
    for directory in ('docs', 'schemas', 'examples', 'templates', 'scripts'):
        markdown += sorted((ROOT / directory).glob('*.md'))
    for path in markdown:
        body = path.read_text()
        # Repository uses inline Markdown links. External URLs are not fetched;
        # fragments are not checked, only local file/directory existence.
        targets = re.findall(r'\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', body)
        for target in targets:
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = path.parent / unquote(parsed.path)
            assert resolved.exists(), f"Broken local link: {path.relative_to(ROOT)} -> {target}"
            links += 1
        if path.name == 'AGENTS.md':
            continue
        other = (path.with_name(path.name.replace('.ja.md', '.md'))
                 if path.name.endswith('.ja.md') else path.with_suffix('.ja.md'))
        assert other.exists(), f"Missing language pair: {path.relative_to(ROOT)}"
        assert other.name in targets, f"Missing reciprocal language link: {path}"
        pairs += 1
    print(f"PASS: {links} local link targets; {pairs // 2} reciprocal language pairs")

    # Narrow status guards, not a natural-language semantic equivalence checker.
    for name, marker in [('README.md', 'design'), ('README.ja.md', '設計')]:
        assert marker in (ROOT / name).read_text(), f"Missing design status: {name}"
    for name, marker in [('12-protocol-and-acceptance.md', 'not executed'),
                         ('12-protocol-and-acceptance.ja.md', '未実施')]:
        body = (ROOT / 'docs' / name).read_text()
        assert marker in body, f"Missing unexecuted acceptance status: {name}"
        assert all(f'SCI-{n:02}' in body for n in range(1, 13))
    for name, marker in [('13-verified-discovery.md', 'not executed'),
                         ('13-verified-discovery.ja.md', 'schema検査では実施しません')]:
        body = (ROOT / 'docs' / name).read_text()
        assert marker in body, f"Missing unexecuted verification status: {name}"
        assert all(f'SCI-{n:02}' in body for n in range(13, 21))
    print('PASS: inactive examples and limited design/unexecuted-status guards (SCI-01–20)')
    print('NOT RUN: scientific experiments, SCI runtime acceptance, artifact/hash resolution,')
    print('issuer authentication, sandbox enforcement, formal proof checking or cost measurement.')


if __name__ == '__main__':
    try:
        check()
    except (AssertionError, ValueError, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        sys.exit(1)
