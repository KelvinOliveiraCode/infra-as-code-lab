<div align="center">

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/tests-121%20passing-brightgreen?style=flat-square" alt="Tests">
  <img src="https://img.shields.io/badge/coverage-88%25-yellowgreen-brightgreen?style=flat-square" alt="Coverage">
  <img src="https://img.shields.io/badge/deps-PyYAML%20only-blue?style=flat-square" alt="Deps">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows-blue?style=flat-square" alt="Windows">
</p>

</div>

# infra-as-code-lab

Infraestrutura de rede e servidores declarada em YAML, gerada em arquivos de
configuração, com o plano mostrando o diff antes de qualquer escrita.

Network and server infrastructure declared in YAML, rendered to configuration
files, with the plan showing the diff before anything is written.

> **Nada aqui é real.** Os equipamentos `SW-LAB-01`, `FW-LAB-01`, `AP-LAB-01`,
> `SRV-APP-01` não existem. As configurações são sintaxe Cisco-like escrita
> para este projeto, e não há SSH, SNMP ou SDK de equipamento em lugar
> nenhum — o pacote tem uma dependência externa e ela é o PyYAML.

## O que é

Infraestrutura como código declarativo: você escreve o que é verdade sobre a
rede em um YAML, e a ferramenta gera o arquivo de configuração de cada
equipamento a partir disso. Antes de gerar, ela mostra o diff — e o diff não é
uma opção, é o único comando que existe.

## Por que foi feito

Administração manual de infraestrutura não é sustainable em nenhum sentido:
não escala, não é revisável, e o estado real de um andar inteiro vive na
cabeça de quem configurou por último. IaC resolve os três problemas, mas
introduz um quarto que ninguém menciona: **um erro no YAML vira erro em
cinco equipamentos ao mesmo tempo**, e a revisão de um diff de texto não é o
mesma coisa que revisar um comando.

Este projeto trata a revisão como o problema central. O plano é o produto
principal e a geração é secundária. Não existe comando que aplique mudança,
porque uma ferramenta de IaC cujo passo único é "aplicar" reproduz em escala
o problema que promete resolver.

## Como rodar

Um comando, saída esperada:

```powershell
python -m iaclab plano --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
```

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
+ description 30
+ exit
+! portas
+interface Gi0/1
...

firewall:FW-LAB-01: drift manual, 33 adicionada(s), 0 removida(s)
...

RESUMO: 7 equipamento(s) com diferenca: 7 drift manual
```

Depois de gerar, o mesmo plano sai limpo:

```powershell
python -m iaclab gerar --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
python -m iaclab plano --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
```

```
RESUMO: sem mudancas
```

Instalação:

```powershell
pip install -e ".[dev]"
```

## Os três estados do diff

A distinção que faz a diferença entre uma ferramenta útil e uma que ninguém
lê.

| Estado | O que aconteceu | Alerta | Saída |
|---|---|---|---|
| `sem mudanca` | desejado e atual são iguais | não | 0 |
| `mudanca gerenciada` | o YAML mudou, o arquivo ficou para trás | **sim** | 1 |
| `drift manual` | alguém editou o arquivo depois de gerado | **sim** | 1 |

Os dois estados com alerta recebem a mesma urgência na saída, mas significam
coisas diferentes para o time: **mudança gerenciada é trabalho agendado**,
alguém editou o YAML e o render está atrasado. **Drift manual é incidente**,
alguém mexeu no equipamento e o YAML não sabe.

Separar os dois exige o manifesto — `.manifesto.json` registra o que foi
gerado por último. Sem ele, as duas situações produzem a mesma comparação, e a
classificação vira palpite.

## Como funciona

| Módulo | Responsabilidade |
|---|---|
| `modelo.py` | O schema: o que um YAML pode dizer e o que não pode |
| `cargador.py` | Lê os YAMLs do disco, resolve o alias `servidores:` |
| `geradores/` | Um gerador por tipo: `switch`, `firewall`, `ap`, `servidor` |
| `render.py` | Guarda os arquivos gerados e o manifesto |
| `diff.py` | Compara desejado × atual e classifica em três estados |
| `plano.py` | Monta o plano; `--dry-run` é o padrão e não há como escrever |
| `cli.py` | `plano`, `gerar`, `regras` |

Os geradores devolvem **texto**; quem escreve é o `render.py`. Essa separação é
o que torna o dry-run honesto: um gerador que abrisse arquivo teria o poder de
escrever antes de alguém pedir o plano, e o `--dry-run` seria promessa em vez
de garantia.

### Por que dois arquivos por equipamento

Cada equipamento gera um `.cfg` (o bruto) e um `.normalizado` (o mesmo texto
sem o cabeçalho de geração). O diff compara o normalizado.

O bruto é o que permite descobrir que a normalização está errada. Se só o
normalizado fosse guardado, o arquivo "compara igual" justamente porque a
informação que faltava foi removida dos dois lados. O cabeçalho — que carrega
o caminho do YAML de origem — também sai da comparação por essa razão.

### Por que a idempotência é uma decisão, não um acidente

O critério de aceite é "rodar duas vezes dá sem mudanças". Três decisões
sustentam isso, e cada uma delas quebra se mudar:

1. **Sem timestamp** em nenhum lugar. Uma data por arquivo faria toda
   execução diferir da anterior.
2. **Ordem fixa** dos equipamentos e das seções, sem depender de hash.
3. **Comparação do normalizado**, sem o cabeçalho.

O `tools/verificar_aceite.py` verifica as duas metades do critério, e o CI
roda o gerador do exemplo com `git diff --exit-code` para garantir que o
exemplo do repositório ainda corresponde ao que o código faz.

## Formato dos dados

`infra/rede.yaml` — rede desejada:

```yaml
vlans:
  - id: 10
    nome: CORPORATIVO
    faixa: 192.168.10.0/24
    gateway: 192.168.10.1

equipamentos:
  - tipo: switch
    hostname: SW-LAB-01
    modelo: CAT-2960X-FICT
    vlan: 30
    portas:
      - nome: Gi0/3
        modo: trunk
        vlan: 30
        trunks: ['10', '20', '30']
```

`infra/servidores.yaml` usa a chave `servidores:` em vez de `equipamentos:` —
mesmo schema, nome de arquivo diferente. `infra/acessos.yaml` é separado de
propósito: rede responde "o pacote chega", servidores responde "o processo
roda", acessos responde "esta pessoa pode".

Campos aceitos, direto do código:

```powershell
python -m iaclab regras
```

## O que aprendi

- **O diff mais importante é o que some.** Uma mudança gerenciada costuma
  remover mais do que adiciona, e a remoção é a parte que ninguém lê com
  atenção. Por isso o plano mostra as duas direções.
- **Classificar drift sem histórico é adivinhação.** A primeira versão
  classificava pela existência do arquivo no disco, e um arquivo editado à mão
  aparecia como "mudança gerenciada" — a resposta errada para a pergunta
  errada. O manifesto resolveu, e o custo foi um arquivo.
- **O schema precisa recusar, não ignorar.** Campo desconhecido aceito em
  silêncio vira equipamento sem a configuração que o YAML pediu. A lista de
  campos por tipo é fechada, e um teste garante que os YAMLs do projeto não
  saem dela.
- **CRLF não é detalhe de estilo.** Uma virgula entre LF e CRLF produz um diff
  inteiro de arquivo, com dezenas de linhas "alteradas" que não mudaram. É o
  pior tipo de alarme: o número deixa de significar nada. A leitura normaliza,
  deliberadamente.
- **O `--dry-run` só é uma garantia se não houver caminho alternatif.** Uma
  flag que pode ser esquecida por pressa não é padrão; é sugestão. Aqui não
  existe comando que aplique.

## Testes

```powershell
python -m pytest -v
```

121 testes, 88% de cobertura. Cobrem o schema e as três camadas de recusa, os
quatro geradores (incluindo que nenhum deles emite senha), as três
classificações do diff, a idempotência, o dry-run não escrevendo, e a CLI
inteira incluindo o `--help`.

Portões que a suíte não cobre sozinha:

```powershell
python tools/verificar_aceite.py     # as duas metades do critério de aceite
python tools/verificar_encoding.py   # nenhum caractere corrompido
python tools/gerar_exemplo.py        # regera o exemplo de forma determinística
```

A prova de aceite é a mais importante, porque a suíte prova que cada função
funciona e não que a ferramenta inteira se comporta:

```
1) o dry-run mostra o diff e nao escreve nada
   7 equipamento(s) com diff, zero bytes escritos

2) rodar duas vezes seguidas produz 'sem mudancas'
   15 arquivo(s) na 1a, identico na 2a, plano limpo

3) uma edicao a mao no arquivo gerado e drift manual
   SW-LAB-01: drift_manual, 2 diferenca(s)

4) mudar o YAML e mudanca gerenciada
   SW-LAB-01: mudanca_gerenciada, 2 diferenca(s)

ok: dry-run sem escrita, duas geracoes identicas, e as tres
classificacoes do diff corretas
```

## Estrutura

```
infra-as-code-lab/
├── src/iaclab/              # o pacote
│   └── geradores/           # um gerador por tipo de equipamento
├── infra/                   # rede, servidores e acessos em YAML
├── docs/                    # modelo declarativo, dry-run
├── exemplos/                # plano de execução gerado
├── tests/                   # 121 testes
└── tools/                   # gerador e portões
```

## Limitações

- **Não aplica nada, em lugar nenhum.** Não existe comando que aplique. Isso é
  a tese do projeto, não uma pendência — mas significa que a ferramenta não
  demonstra o caminho até o equipamento.
- **Não valida conectividade.** O plano compara texto. Ele não testa rota,
  não abre sessão, não verifica se a configuração resultante sobe. Um diff
  limpo é uma afirmação sobre arquivos, não sobre serviço.
- **A sintaxe é Cisco-like fictícia.** Os geradores escrevem uma forma
  plausível de configuração, não a saída real de nenhum produto. Um equipamento
  real exigiria um gerador reescrito, não ajustado.
- **Uma tabela MAC com ordem instável seria tratada como mudança.** Cada
  gerador ordena o que escreve, e a ordem vem da declaração. Um YAML cuja
  ordem muda entre execuções gera diff — que é o comportamento correto, mas
  exige que a declaração seja estável.
- **O manifesto é estado local.** Ele vive em `saida/gerado/` e não é
  versionado. Duas máquinas com o mesmo YAML e manifestos diferentes dão
  classificações diferentes — o que é correto, porque elas estão de fato em
  estados diferentes.
- **Um único YAML por execução fica mais simples do que precisaria.** O
  `--infra` é repetível e a junção detecta conflito de identidade, mas não há
  suporte a herança, a variáveis entre arquivos ou a templates.

## Licença

MIT.

---

## English

Infrastructure as code, declared in YAML, rendered to per-device
configuration files, with the diff shown before anything is written.

### What it is

You write what is true about the network in a YAML file; the tool generates
each device's configuration from it. Before generating, it shows the diff —
and the diff is not a flag, it is the only command that exists.

### Why it was built

Manual infrastructure administration does not scale, is not reviewable, and the
real state of a floor lives in the head of whoever configured it last. IaC
fixes those three and introduces a fourth nobody mentions: **a mistake in the
YAML becomes a mistake on five devices at once**, and reviewing a text diff is
not the same as reviewing a command.

This project treats review as the central problem. The plan is the product,
generation is secondary. There is no command that applies, because an IaC tool
whose only step is "apply" reproduces at scale the problem it claims to solve.

### How to run

```powershell
python -m iaclab plano --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
```

```
modo: dry-run (nada e escrito em equipamento nenhum)
equipamentos: 7

switch:SW-LAB-01: drift manual, 39 adicionada(s), 0 removida(s)
--- switch:SW-LAB-01 (atual)
+++ switch:SW-LAB-01 (desejado)
@@ -0,0 +1,39 @@
+hostname SW-LAB-01
...

RESUMO: 7 equipamento(s) com diferenca: 7 drift manual
```

```
$ python -m iaclab gerar --infra ...   # writes saida/gerado/
$ python -m iaclab plano --infra ...   # RESUMO: sem mudancas
```

Install:

```powershell
pip install -e ".[dev]"
```

### The three states

| State | What happened | Alert | Exit |
|---|---|---|---|
| `sem mudanca` | desired equals current | no | 0 |
| `mudanca gerenciada` | the YAML changed, the file fell behind | **yes** | 1 |
| `drift manual` | someone edited the file after it was generated | **yes** | 1 |

Both alerting states mean different things to the team: a **managed change is
scheduled work**, and **manual drift is an incident**. Telling them apart needs
the manifest — `.manifesto.json` records what was last generated. Without it
both situations produce the same comparison and the classification is a guess.

### How it works

| Module | Responsibility |
|---|---|
| `modelo.py` | The schema: what a YAML may say and what it may not |
| `cargador.py` | Reads the YAMLs, resolves the `servidores:` alias |
| `geradores/` | One generator per device type |
| `render.py` | Stores the generated files and the manifest |
| `diff.py` | Compares desired vs current, classifies in three states |
| `plano.py` | Builds the plan; dry-run is the default and cannot write |
| `cli.py` | `plano`, `gerar`, `regras` |

Generators return **text**; `render.py` is what writes. That split is what
makes the dry-run honest: a generator that opened files would be able to write
before anyone asked for a plan, and `--dry-run` would be a promise rather than
a guarantee.

Two files per device: a `.cfg` (raw) and a `.normalized` (the same text without
the generation header). The diff compares the normalized one. The raw file is
what lets you discover that the normalization is wrong — keeping only the
normalized version would make the file "compare equal" precisely because the
missing information was stripped from both sides.

The idempotence criterion — two runs report no changes — rests on three
decisions: no timestamp anywhere, fixed ordering that never depends on a hash,
and comparing the normalized text without the header.

### Data format

`infra/rede.yaml` holds the network, `infra/servidores.yaml` holds servers
(using the `servidores:` key, same schema), and `infra/acessos.yaml` is
separate on purpose: the network answers "does the packet arrive", servers
answer "does the process run", and access answers "may this person".

```powershell
python -m iaclab regras   # fields accepted per type, from the code
```

### What I learned

- **The diff that matters most is what disappears.** A managed change usually
  removes more than it adds, and the removal is what nobody reads closely.
- **Classifying drift without history is guessing.** The first version keyed
  off whether the file existed, and a hand-edited file showed up as a managed
  change — the wrong answer to the wrong question. The manifest fixed it.
- **The schema must refuse, not ignore.** An unknown field accepted in
  silence becomes a device missing the configuration the YAML asked for.
- **CRLF is not a style detail.** A single comma between LF and CRLF produces
  a whole-file diff of lines that did not change.
- **Dry-run is only a guarantee if there is no alternative path.** A flag that
  can be forgotten in a hurry is a suggestion. Here, no command applies.

### Tests

121 tests, 88% coverage.

```powershell
python -m pytest -v
python tools/verificar_aceite.py     # both halves of the acceptance criterion
python tools/verificar_encoding.py   # no corrupted characters
python tools/gerar_exemplo.py        # regenerates the example deterministically
```

### Limitations

- **It applies nothing, anywhere.** No command applies. That is the thesis,
  not a to-do — but it means the tool never demonstrates the path to a device.
- **It does not validate connectivity.** A clean diff is a claim about files,
  not about service.
- **The syntax is fictitious Cisco-like.** The generators write a plausible
  form, not any product's real output. A real device needs a rewritten
  generator, not a tweaked one.
- **The manifest is local state.** Two machines with the same YAML and
  different manifests classify differently — which is correct, because they
  genuinely are in different states.
- **Single YAML stays simpler than it should need to be.** `--infra` repeats
  and joining detects identity conflicts, but there is no inheritance, no
  cross-file variables, no templates.

### License

MIT.