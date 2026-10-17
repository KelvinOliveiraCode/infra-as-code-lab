<img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/tests-121%20passing-brightgreen?style=flat-square" alt="Tests">
<img src="https://img.shields.io/badge/coverage-88%25-yellowgreen?style=flat-square" alt="Coverage">
<img src="https://img.shields.io/badge/deps-PyYAML%20only-blue?style=flat-square" alt="Deps">
<img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="License">

# infra-as-code-lab

Infraestrutura de rede e servidores declarada em YAML, renderizada em arquivos de configuracao, com o plano mostrando o diff antes de qualquer escrita.

## Problema / Por que existe

Administrar infraestrutura a mao nao escala, nao e revisavel e deixa o estado real de um andar na cabeca de quem configurou por ultimo. Infraestrutura como codigo resolve isso, mas introduz um problema que raramente se menciona: um erro no YAML vira erro em cinco equipamentos ao mesmo tempo, e revisar um diff de texto nao e a mesma coisa que revisar um comando.

Este projeto trata a revisao como o problema central. O plano e o produto principal e a geracao e secundaria. Nao existe comando que aplique mudança, porque uma ferramenta de IaC cujo passo unico e aplicar reproduz em escala o problema que promete resolver.

Nada aqui e real: SW-LAB-01, FW-LAB-01, AP-LAB-01, SRV-APP-01 nao existem. As configuracoes sao sintaxe Cisco-like escrita para este projeto. Nao ha SSH, SNMP nem SDK de equipamento, e a unica dependencia externa e o PyYAML.

## O que faz

Le um ou mais YAMLs de infraestrutura, valida o schema na carga, gera o arquivo de configuracao de cada equipamento e mostra o diff entre o desejado e o atual antes de escrever qualquer coisa. Sao tres comandos.

- plano: mostra o diff e nao escreve nada. E o padrao e nao pode escrever.
- gerar: escreve os arquivos em saida/gerado/ e registra o manifesto. Continua sem tocar em equipamento real.
- regras: lista os tipos aceitos e os campos de cada um, direto do codigo.

O plano compara cada equipamento e classifica em um de tres estados: sem mudanca, mudanca gerenciada (o YAML mudou e o arquivo ficou atras) ou drift manual (alguem editou o arquivo depois de gerado).

## Stack

- Python 3.10 ou superior
- PyYAML>=6.0, a unica dependencia de execucao, usada somente para ler o YAML declarativo
- O restante e biblioteca padrao. difflib faz o diff, f-strings e listas fazem a geracao
- pytest>=7.4 e pytest-cov>=4.1 apenas para desenvolvimento
- Nenhuma biblioteca de rede, SSH, SNMP ou SDK de equipamento

## Como funciona

O fluxo e sempre leitura, geracao, comparacao, impressao, e escrita so quando o modo permite.

1. cargador.py le os YAMLs do disco, resolve o alias `servidores:` e junta varios arquivos em uma infraestrutura so, recusando chaves e campos desconhecidos.
2. modelo.py define o schema fechado: tipos conhecidos (switch, firewall, ap, servidor) e a lista exata de campos de cada um. A validacao acontece na carga, antes de qualquer geracao, para que um YAML invalido nao escreva metade dos arquivos e quebre no quarto.
3. geradores/ tem um gerador por tipo. Cada um devolve texto, nunca abre arquivo. Isso torna o dry-run uma garantia, nao uma promessa.
4. render.py guarda o arquivo bruto (.cfg) e o normalizado (.normalizado, sem o cabecalho de geracao), e escreve o manifesto .manifesto.json com o que foi gerado por ultima vez.
5. diff.py compara o desejado com o atual e classifica usando o manifesto. Sem o manifesto, mudanca gerenciada e drift manual produzem a mesma comparacao e nao ha como separa-las.
6. plano.py monta o plano. --dry-run e o padrao e nao existe modo que escreva em equipamento real.

Cada equipamento gera dois arquivos porque o bruto e o que a ferramenta produz e o normalizado e o que se quer comparar. Se so o normalizado fosse guardado, um erro na normalizacao seria invisivel: o arquivo compararia igual porque a informacao que faltou foi removida dos dois lados.

A idempotencia e uma decisao, nao um acidente. Rodar duas vezes seguido deve dar sem mudancas. Tres decisoes sustentam isso: nao ha timestamp em nenhum lugar, a ordem dos equipamentos e das secoes e fixa e nao depende de hash, e a comparacao usa o normalizado sem o cabecalho. O CI verifica isso com git diff --exit-code no exemplo do repositorio.

## Como rodar

Instale o pacote em modo editavel:

```
pip install -e ".[dev]"
```

Plano inicial, antes de gerar qualquer arquivo:

```
python -m iaclab plano --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
```

Saida esperada:

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

Depois de gerar, o mesmo plano sai limpo:

```
python -m iaclab gerar --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
python -m iaclab plano --infra infra/rede.yaml --infra infra/servidores.yaml --infra infra/acessos.yaml
```

```
RESUMO: sem mudancas
```

Os codigos de saida sao 0 sem mudanca, 1 com diferenca ou alerta, e 2 erro de schema.

Os campos aceitos por tipo, direto do codigo:

```
python -m iaclab regras
```

Testes:

```
python -m pytest -v
python tools/verificar_aceite.py   # prova de aceite: duas metades e tres classificacoes
python tools/verificar_encoding.py # nenhum caractere corrompido
python tools/gerar_exemplo.py      # regera o exemplo de forma deterministica
```

A suíte tem 121 testes e 88 por cento de cobertura; o piso e 70 por cento e uma regressao derruba o build.

## Estrutura do projeto

```
infra-as-code-lab/
├── src/iaclab/              # o pacote: modelo, cargador, plano, diff, render, cli, geradores/
├── geradores/               # um gerador por tipo: switch, firewall, ap, servidor
├── infra/                   # rede.yaml, servidores.yaml, acessos.yaml
├── docs/                    # modelo declarativo, por que o dry-run importa
├── exemplos/                # plano de execucao gerado, deterministico
├── tests/                   # 121 testes
├── tools/                   # gerador de exemplo e portoes de aceite
├── pyproject.toml
├── requirements.txt
├── LICENSE
└── README.md
```

## Trade-offs e decisoes

- Plano padrao, aplicacao inexistente: nao existe comando que aplique. Isso e a tese do projeto, nao uma pendencia.
- Geradores devolvem texto; so render.py escreve. Um gerador que abrisse arquivo poderia escrever antes de alguem pedir o plano, e o dry-run seria promessa em vez de garantia.
- Nao ha timestamp em nenhum lugar. Uma data por arquivo faria toda execucao diferir da anterior e quebraria o criterio de aceite.
- Ordem fixa de equipamentos e secoes, sem hash. Um plano que reordena entre execucoes acusa reordenacao como mudanca de configuracao.
- Comparacao do normalizado, sem o cabecalho de geracao, que carrega o caminho do YAML de origem.
- Manifesto local (.manifesto.json) para classificar drift. Sem ele, as duas situacoes produzem a mesma comparacao e a classificacao vira palpite. O manifesto e estado local, nao versionado, e duas maquinas com o mesmo YAML e manifestos diferentes classificam diferente porque estao de fato em estados diferentes.
- Schema fecha a lista de campos. Um campo desconhecido aceito em silencio vira equipamento sem a configuracao que o YAML pediu; um teste garante que os YAMLs do projeto nao saem dela.
- Validacao na carga, nao na geracao. Um YAML invalido que so falha quando o gerador roda produz erro no lugar menos util: a meio de um arquivo de saida.
- Leitura normaliza CRLF para LF. Uma virgula entre LF e CRLF produz um diff inteiro de linhas que nao mudaram, o pior tipo de alarme porque o numero deixa de significar nada.

## Limitações conhecidas

- Nao aplica nada, em lugar nenhum. Nao existe comando que aplique; a ferramenta nao demonstra o caminho ate o equipamento.
- Nao valida conectividade. O plano compara texto: nao testa rota, nao abre sessao, nao verifica se a configuracao resultante sobe. Um diff limpo e uma afirmacao sobre arquivos, nao sobre servico.
- A sintaxe e Cisco-like ficticia. Os geradores escrevem uma forma plausivel de configuracao, nao a saida real de nenhum produto. Um equipamento real exigiria um gerador reescrito, nao ajustado.
- Uma ordem instavel entre execucoes seria tratada como mudanca. Cada gerador ordena o que escreve segundo a declaracao; um YAML cuja ordem muda gera diff, comportamento correto que exige declaracao estavel.
- Um unico YAML por execucao fica mais simples do que precisaria. O --infra e repetavel e a juncao detecta conflito de identidade, mas na ha suporte a heranca, variaveis entre arquivos ou templates.
- O manifesto e estado local, vive em saida/gerado/ e nao e versionado.

## Licença

MIT.

## Autor

Kelvin
