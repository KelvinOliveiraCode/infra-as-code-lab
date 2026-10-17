# infra-as-code-lab

<img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/tests-121%20passing-brightgreen?style=flat-square" alt="Tests">
<img src="https://img.shields.io/badge/coverage-88%25-yellowgreen?style=flat-square" alt="Coverage">
<img src="https://img.shields.io/badge/deps-PyYAML%20only-blue?style=flat-square" alt="Deps">
<img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License">

Network and server infrastructure declared in YAML, rendered into configuration files, with the plan showing the diff before any writing.

## Problem / Why it exists

Managing infrastructure by hand does not scale, is not reviewable, and leaves the real state of a floor in the head of whoever configured it last. Infrastructure as code solves that, but introduces a problem rarely mentioned: an error in the YAML becomes an error in five devices at once, and reviewing a text diff is not the same as reviewing a command.

This project treats review as the central problem. The plan is the main product and generation is secondary. There is no command that applies changes, because an IaC tool whose single step is to apply reproduces at scale the problem it promises to solve.

Nothing here is real: SW-LAB-01, FW-LAB-01, AP-LAB-01, SRV-APP-01 do not exist. The configurations are Cisco-like syntax written for this project. There is no SSH, SNMP or device SDK, and the only external dependency is PyYAML.

## What it does

Reads one or more infrastructure YAMLs, validates the schema on load, generates each device's configuration file and shows the diff between desired and current before writing anything. Three commands.

- plan: shows the diff and writes nothing. Default and cannot write.
- generate: writes files to saida/gerado/ and records the manifest. Still never touches real equipment.
- rules: lists accepted types and fields for each, straight from the code.

The plan compares each device and classifies it into one of three states: no change, managed change (YAML changed and file fell behind) or manual drift (someone edited the file after generation).

## Stack

- Python 3.10 or higher
- PyYAML>=6.0, the only runtime dependency, used only to read declarative YAML
- The rest is standard library. difflib does the diff, f-strings and lists do generation
- pytest>=7.4 and pytest-cov>=4.1 for development only
- No network, SSH, SNMP or device SDK library

## How it works

The flow is always read, generate, compare, print, and write only when the mode allows.

1. cargador.py reads the YAMLs from disk, resolves the `servidores:` alias and joins several files into a single infrastructure, rejecting unknown keys and fields.
2. modelo.py defines the closed schema: known types (switch, firewall, ap, servidor) and the exact field list for each. Validation happens on load, before any generation, so an invalid YAML does not write half the files and break on the fourth.
3. geradores/ has one generator per type. Each returns text, never opens a file. That makes dry-run a guarantee, not a promise.
4. render.py stores the raw file (.cfg) and the normalized one (.normalizado, without the generation header), and writes the .manifesto.json manifest with what was generated last.
5. diff.py compares desired against current and classifies using the manifest. Without the manifest, managed change and manual drift produce the same comparison and cannot be separated.
6. plano.py assembles the plan. --dry-run is the default and no mode writes to real equipment.

Each device generates two files because the raw one is what the tool produces and the normalized one is what you want to compare. If only the normalized were kept, an error in normalization would be invisible: the file would compare equal because the information that went missing was removed from both sides.

Idempotency is a decision, not an accident. Running twice in a row must yield no changes. Three decisions support that: no timestamp anywhere, equipment and section order is fixed and does not depend on hash, and comparison uses the normalized file without the header. CI verifies this with git diff --exit-code on the repository example.

## How to run

Install the package in editable mode:

```
pip install -e ".[dev]"
```

Initial plan, before generating any file:

```
python -m iaclab plano --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
```

Expected output:

```
modo: dry-run (nada e escrito em equipamento nenhum)
equipamentos: 7
data de referencia: 2026-01-15 14:00

DIFFS:

switch:SW-LAB-01: drift manual, 39 adicionada(s), 0 removida(s)
--- switch:SW-LAB-01 (atual)
+++ switch:SW-LAB-01 (desejado)
@@ -0,0 +1,39 @@
+hostname SW-LAB-01
+! modelo CAT-2960X-FICT
+interface Vlan30
...
RESUMO: 7 equipamento(s) com diferenca: 7 drift manual
```

After generating, the same plan comes out clean:

```
python -m iaclab gerar --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
python -m iaclab plano --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
```

```
RESUMO: sem mudancas
```

Exit codes are 0 with no change, 1 with difference or alert, and 2 schema error.

Accepted fields per type, straight from the code:

```
python -m iaclab regras
```

Tests:

```
python -m pytest -v
python tools/verificar_aceite.py   # acceptance proof: two halves and three classifications
python tools/verificar_encoding.py # no corrupted characters
python tools/gerar_exemplo.py      # regenerates the example deterministically
```

The suite has 121 tests and 88 percent coverage; the floor is 70 percent and a regression fails the build.

## Project structure

```
infra-as-code-lab/
├── src/iaclab/              # the package: modelo, cargador, plano, diff, render, cli, geradores/
├── geradores/               # one generator per type: switch, firewall, ap, servidor
├── infra/                   # rede.yaml, servidores.yaml, acessos.yaml
├── docs/                    # declarative model, why dry-run matters
├── exemplos/                # generated execution plan, deterministic
├── tests/                   # 121 tests
├── tools/                   # example generator and acceptance gates
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```

## Trade-offs and decisions

- Plan default, application nonexistent: no command applies. That is the project's thesis, not a pending item.
- Generators return text; only render.py writes. A generator that opened a file could write before anyone asked for the plan, and dry-run would be a promise instead of a guarantee.
- No timestamp anywhere. A date per file would make every execution differ from the previous one and break the acceptance criterion.
- Fixed equipment and section order, no hash. A plan that reorders between runs reports reordering as a configuration change.
- Normalized comparison, without the generation header, which carries the source YAML path.
- Local manifest (.manifesto.json) to classify drift. Without it, the two situations produce the same comparison and classification becomes a guess. The manifest is local state, not versioned, and two machines with the same YAML and different manifests classify differently because they are in fact in different states.
- Schema closes the field list. An unknown field accepted silently becomes a device without the configuration the YAML asked for; a test ensures the project's YAMLs stay inside it.
- Validation on load, not on generation. An invalid YAML that only fails when the generator runs produces an error in the least useful place: halfway through an output file.
- Reading normalizes CRLF to LF. A newline difference between LF and CRLF produces a full diff of lines that did not change, the worst kind of alarm because the number stops meaning anything.

## Known limitations

- Applies nothing, anywhere. No command applies; the tool does not demonstrate the path to the device.
- Does not validate connectivity. The plan compares text: it does not test routes, open sessions, or verify the resulting configuration boots. A clean diff is a statement about files, not about service.
- The syntax is fictional Cisco-like. Generators write a plausible form of configuration, not the real output of any product. A real device would require a rewritten generator, not an adjustment.
- Unstable ordering between runs would be treated as a change. Each generator orders what it writes according to the declaration; a YAML whose order changes produces a diff, correct behavior that requires stable declaration.
- A single YAML per run is simpler than it needs to be. --infra is repeatable and the join detects identity conflicts, but there is no support for inheritance, variables between files or templates.
- The manifest is local state, lives in saida/gerado/ and is not versioned.

## License

MIT.

## Author

Kelvin Oliveira