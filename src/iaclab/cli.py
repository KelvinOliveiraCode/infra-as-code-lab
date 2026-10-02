"""A linha de comando do iaclab.

The iaclab command line.

Tres comandos, e a ordem em que eles contam a historia do projeto:

- `plano` - o que mudaria. Nao escreve nada. E o padrao.
- `gerar` - escreve os arquivos em `gerado/`. Continua sem tocar em
  equipamento nenhum: "gerar" aqui significa gerar arquivo, e nao aplicar.
- `regras` - as regras de normalizacao e os campos aceitos por tipo, para
  quem esta escrevendo o YAML e precisa saber o que o schema aceita.

A distincao entre `plano` e `gerar` e a mesma do Terraform, e e deliberada:
existe um comando que mostra e existe um comando que escreve, e nenhum deles
aplica. Quem quiser aplicar, nao esta neste pacote - e essa e a conclusao do
projeto, nao uma limitacao.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import diff as modulo_diff
from . import plano as modulo_plano
from .cargador import carregar_arquivo
from .geradores import todos
from .modelo import CAMPOS_POR_TIPO, TIPOS_CONHECIDOS, ErroDeSchema

# Codigos de saida. Different de zero quando ha problema, para o comando
# unico de validacao poder ser usado em script e no CI.
SAIDA_OK = 0
SAIDA_ALERTA = 1
SAIDA_ERRO = 2

# Data fixa para a saida ser deterministica. Um plano que mostra a hora do
# relogio muda a cada execucao e quebra o diff do proprio plano.
DATA_FIXA = "2026-01-15 14:00"


def _constroi_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos.

    Build the argument parser.

    Returns:
        O parser pronto.
    """
    parser = argparse.ArgumentParser(
        prog="iaclab",
        description=(
            "Infraestrutura declarativa em YAML, gerada em arquivos de "
            "configuracao. Nada e aplicado em equipamento real / "
            "Declarative infrastructure in YAML, rendered to config files. "
            "Nothing is applied to a real device."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    # ------------------------------------------------------------- plano
    p_plano = sub.add_parser(
        "plano",
        help="mostra o diff sem escrever nada (padrao)",
        description=(
            "Mostra o diff entre o desejado e o atual, sem escrever nada. "
            "Este e o modo padrao e nao ha como escrever aqui. / "
            "Shows the diff without writing anything."
        ),
    )
    p_plano.add_argument(
        "--infra",
        action="append",
        required=True,
        help="YAML de infraestrutura. Repita para varios arquivos.",
    )
    p_plano.add_argument(
        "--saida",
        default="saida",
        help="diretorio onde o estado atual mora (padrao: saida)",
    )
    p_plano.add_argument(
        "--dry-run",
        action="store_true",
        help="aceito e ignorado: o plano ja e dry-run por padrao",
    )
    p_plano.add_argument(
        "--contexto",
        type=int,
        default=3,
        help="linhas de contexto no diff (padrao: 3)",
    )

    # ------------------------------------------------------------- gerar
    p_gerar = sub.add_parser(
        "gerar",
        help="escreve os arquivos gerados em disco",
        description=(
            "Gera os arquivos de configuracao em <saida>/gerado/. "
            "Continua sem aplicar em equipamento nenhum. / "
            "Renders the config files. Still nothing applied."
        ),
    )
    p_gerar.add_argument(
        "--infra",
        action="append",
        required=True,
        help="YAML de infraestrutura. Repita para varios arquivos.",
    )
    p_gerar.add_argument(
        "--saida",
        default="saida",
        help="diretorio de saida (padrao: saida)",
    )
    p_gerar.add_argument(
        "--dry-run",
        action="store_true",
        help="faz o plano e nao escreve mesmo assim",
    )

    # ------------------------------------------------------------ regras
    p_regras = sub.add_parser(
        "regras",
        help="mostra os campos aceitos por tipo de equipamento",
        description=(
            "Mostra os campos que o schema aceita em cada tipo. "
            "Serve para quem escreve o YAML. / "
            "Shows the fields the schema accepts."
        ),
    )
    p_regras.add_argument(
        "--texto", action="store_true", help="saida em texto, sem cor"
    )

    return parser


def _imprime_plano(plano: modulo_plano.Plano, contexto: int, destino) -> int:
    """Imprime o plano e devolve o codigo de saida.

    Print the plan and return the exit code.

    Args:
        plano: O plano calculado.
        contexto: Linhas de contexto no diff.
        destino: Onde imprimir.

    Returns:
        0 se limpo, 1 se ha alerta, 2 se ha erro de schema.
    """
    print("modo: dry-run (nada e escrito em equipamento nenhum)", file=destino)
    print(f"equipamentos: {len(plano.diffs)}", file=destino)
    print(f"data de referencia: {DATA_FIXA}\n", file=destino)

    if plano.problemas:
        print(f"PROBLEMAS DE SCHEMA ({len(plano.problemas)}):", file=destino)
        for problema in plano.problemas:
            print(f"  - {problema}", file=destino)
        print("", file=destino)

    print("DIFFS:", file=destino)
    for d in plano.diffs:
        print(f"\n{d.resumo()}", file=destino)
        texto = d.texto(contexto=contexto)
        if texto:
            print(texto.rstrip("\n"), file=destino)

    alertas = plano.com_alerta
    if plano.problemas:
        print(
            f"\nRESUMO: {len(alertas)} equipamento(s) com diferenca, "
            f"{len(plano.problemas)} problema(s) de schema",
            file=destino,
        )
        return SAIDA_ERRO

    if alertas:
        estados: dict[str, int] = {}
        for d in alertas:
            estados[d.estado] = estados.get(d.estado, 0) + 1
        resumo = ", ".join(
            f"{n} {modulo_diff.ROTULO_ESTADO[e]}" for e, n in sorted(estados.items())
        )
        print(
            f"\nRESUMO: {len(alertas)} equipamento(s) com diferenca: {resumo}",
            file=destino,
        )
        return SAIDA_ALERTA

    print("\nRESUMO: sem mudancas", file=destino)
    return SAIDA_OK


def _cmd_plano(args: argparse.Namespace, destino) -> int:
    """Executa o comando `plano`.

    Run the `plano` command.

    Args:
        args: Os argumentos parseados.
        destino: Onde imprimir.

    Returns:
        O codigo de saida.
    """
    plano = modulo_plano.planejar(args.infra, args.saida, escrever=False)
    return _imprime_plano(plano, args.contexto, destino)


def _cmd_gerar(args: argparse.Namespace, destino) -> int:
    """Executa o comando `gerar`.

    Run the `gerar` command.

    Args:
        args: Os argumentos parseados.
        destino: Onde imprimir.

    Returns:
        O codigo de saida.
    """
    escrever = not args.dry_run
    plano = modulo_plano.planejar(args.infra, args.saida, escrever=escrever)

    codigo = _imprime_plano(plano, contexto=3, destino=destino)

    if not escrever:
        print("\n(dry-run: nenhum arquivo foi escrito)", file=destino)
        return codigo

    if plano.problemas:
        print(
            "\nnada foi escrito: o schema tem problemas",
            file=destino,
        )
        return SAIDA_ERRO

    caminhos = plano.aplicar(args.saida)
    print(f"\nescritos: {len(caminhos)} arquivo(s) em {args.saida}/gerado/", file=destino)
    return SAIDA_OK


def _cmd_regras(args: argparse.Namespace, destino) -> int:
    """Executa o comando `regras`.

    Run the `regras` command.

    Args:
        args: Os argumentos parseados.
        destino: Onde imprimir.

    Returns:
        Sempre 0.
    """
    registro = todos()
    print("tipos aceitos em 'tipo:'", file=destino)
    for tipo in TIPOS_CONHECIDOS:
        gerador = "sim" if tipo in registro else "NAO"
        print(f"  {tipo}  (gerador: {gerador})", file=destino)

    print("\ncampos aceitos por tipo:", file=destino)
    for tipo, campos in CAMPOS_POR_TIPO.items():
        print(f"\n  {tipo}:", file=destino)
        for campo in campos:
            print(f"    - {campo}", file=destino)

    return SAIDA_OK


def main(argv: list[str] | None = None) -> int:
    """O ponto de entrada.

    The entry point.

    Args:
        argv: Os argumentos, sem `argv[0]`. `None` usa `sys.argv`.

    Returns:
        O codigo de saida do processo.
    """
    parser = _constroi_parser()
    args = parser.parse_args(argv)

    destino = sys.stdout

    try:
        if args.comando == "plano":
            return _cmd_plano(args, destino)
        if args.comando == "gerar":
            return _cmd_gerar(args, destino)
        if args.comando == "regras":
            return _cmd_regras(args, destino)
    except ErroDeSchema as erro:
        print(f"erro de schema: {erro}", file=sys.stderr)
        return SAIDA_ERRO

    parser.error(f"comando desconhecido: {args.comando}")
    return SAIDA_ERRO