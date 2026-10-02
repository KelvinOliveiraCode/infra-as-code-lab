"""Prova de aceite do iaclab.

iaclab acceptance proof.

O criterio de aceite do projeto tem duas metades, e este script verifica as
duas:

1. **O dry-run mostra o diff completo sem escrever nada.** Antes de gerar, o
   plano tem que acusar todos os equipamentos, e o diretorio de saida tem que
   continuar vazio depois do plano. Um dry-run que escreve em algum lugar -
   nem que seja um `.manifesto.json` - nao e dry-run.
2. **Rodar duas vezes seguidas produz "sem mudancas".** A segunda geracao tem
   que ser identica a primeira, e o plano posterior tem que sair limpo. E o
   teste que separa IaC de "gera um arquivo diferente toda vez", que e o modo
   como uma ferramenta de declaracao vira ruido no dia a dia.

O script tambem verifica as tres classificacoes do diff - sem mudanca,
gerenciada e drift manual - porque e a terceira que a suite nao prova sozinha:
depende do manifesto em disco, e um manifesto escrito errado faz a
classificacao silenciosamente errada.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from iaclab import diff as modulo_diff  # noqa: E402
from iaclab import render  # noqa: E402
from iaclab.cli import main as cli_main  # noqa: E402
from iaclab.plano import planejar  # noqa: E402

YAML_REDE = "infra/rede.yaml"
YAML_SERVIDORES = "infra/servidores.yaml"
YAML_ACESSOS = "infra/acessos.yaml"

TODOS_YAML = [YAML_REDE, YAML_SERVIDORES, YAML_ACESSOS]


def _quieto() -> object:
    """Um `redirect_stdout` descartando a saida da CLI.

    A CLI imprime o diff inteiro - que e o comportamento correto dela e o que
    o README promete. Na prova de aceite isso e ruido: o que interessa aqui e
    o codigo de saida e o estado calculado, nao o relatorio. O relatorio
    completo e verificado a parte, com o `plano` da linha de comando.

    Returns:
        O contexto, para usar em `with`.
    """
    return contextlib.redirect_stdout(io.StringIO())


def rodar_cli(argv: list[str]) -> int:
    """Roda a CLI sem deixar a saida poluir o log da prova.

    Run the CLI without polluting the proof log.

    Args:
        argv: Os argumentos.

    Returns:
        O codigo de saida da CLI.
    """
    with _quieto():
        return cli_main(argv)


class Falha(Exception):
    """Uma condicao de aceite nao foi satisfeita."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)


def checar(condicao: bool, mensagem: str) -> None:
    """Falha se a condicao e falsa.

    Fail if the condition is false.

    Args:
        condicao: A condicao.
        mensagem: O que deu errado, se ela for falsa.

    Raises:
        Falha: Se a condicao for falsa.
    """
    if not condicao:
        raise Falha(mensagem)


def caminhos_completos() -> list[str]:
    """Os YAMLs do projeto, em caminho absoluto.

    The project YAMLs, absolute.

    Returns:
        Os caminhos, na ordem de precedencia.
    """
    return [str(RAIZ / y) for y in TODOS_YAML]


def test_dry_run_nao_escreve(tmp: Path) -> None:
    """O plano nao escreve nada em disco.

    The plan writes nothing to disk.

    Args:
        tmp: Diretorio temporario de saida.

    Raises:
        Falha: Se o plano tiver escrito algo.
    """
    print("1) o dry-run mostra o diff e nao escreve nada")
    saida = tmp / "saida-dryrun"
    plano = planejar(caminhos_completos(), saida, escrever=False)

    checar(len(plano.diffs) > 0, "o plano nao produziu nenhum diff")
    checar(
        len(plano.com_alerta) == len(plano.diffs),
        "antes de gerar, todo equipamento deveria acusar diferenca; "
        f"acusaram {len(plano.com_alerta)} de {len(plano.diffs)}",
    )
    for d in plano.diffs:
        checar(d.alerta, f"{d.equipamento}: nao acusou diferenca antes de gerar")
        checar(d.texto(contexto=1) != "", f"{d.equipamento}: diff vazio")

    # O dry-run nao pode ter criado nem o diretorio `gerado/`.
    checar(
        not (saida / render.SUBDIR).exists(),
        "o dry-run criou a pasta de saida; ele nao deveria escrever nada",
    )

    # E o codigo de saida tem a dizer que ha diferenca.
    codigo = rodar_cli(
        ["plano", "--infra", caminhos_completos()[0],
         "--infra", caminhos_completos()[1],
         "--infra", caminhos_completos()[2],
         "--saida", str(saida)]
    )
    checar(codigo == 1, f"o plano deveria sair com 1 antes de gerar, saiu com {codigo}")

    print(f"   {len(plano.diffs)} equipamento(s) com diff, zero bytes escritos")


def test_duas_vezes_sem_mudanca(tmp: Path) -> None:
    """Duas geracoes seguidas sao identicas, e o plano sai limpo.

    Two renders in a row are identical, and the plan comes out clean.

    Args:
        tmp: Diretorio temporario de saida.

    Raises:
        Falha: Se a segunda geracao diferir ou o plano nao ficar limpo.
    """
    print("\n2) rodar duas vezes seguidas produz 'sem mudancas'")
    saida = tmp / "saida-idem"
    ymls = caminhos_completos()

    # primeira geracao
    plano1 = planejar(ymls, saida, escrever=True)
    checar(not plano1.problemas, f"problemas de schema: {plano1.problemas}")
    caminhos1 = render.escrever(list(plano1.artefatos), saida)
    conteudo1 = {art.equipamento: art.conteudo for art in plano1.artefatos}

    # segunda geracao, sem mudar nada
    plano2 = planejar(ymls, saida, escrever=True)
    checar(not plano2.problemas, f"problemas de schema: {plano2.problemas}")
    conteudo2 = {art.equipamento: art.conteudo for art in plano2.artefatos}

    checar(
        conteudo1 == conteudo2,
        "a segunda geracao produziu texto diferente da primeira; "
        "ha algo nao deterministico no caminho",
    )
    render.escrever(list(plano2.artefatos), saida)

    # plano depois das duas geracoes tem que estar limpo
    plano3 = planejar(ymls, saida, escrever=False)
    for d in plano3.diffs:
        checar(
            d.estado == modulo_diff.SEM_MUDANCA,
            f"{d.equipamento}: estado {d.estado} depois de duas geracoes, "
            "esperado sem_mudanca",
        )
    checar(plano3.sem_mudanca, "o plano nao ficou limpo depois das duas geracoes")

    codigo = rodar_cli(
        ["plano", "--infra", ymls[0], "--infra", ymls[1], "--infra", ymls[2],
         "--saida", str(saida)]
    )
    checar(codigo == 0, f"o plano deveria sair com 0 depois de gerar, saiu com {codigo}")

    print(f"   {len(caminhos1)} arquivo(s) na 1a, identico na 2a, plano limpo")


def test_drift_manual(tmp: Path) -> None:
    """Uma edicao a mao no arquivo gerado vira drift manual.

    A hand edit of the generated file becomes manual drift.

    Args:
        tmp: Diretorio temporario de saida.

    Raises:
        Falha: Se a edicao nao for classificada como drift manual.
    """
    print("\n3) uma edicao a mao no arquivo gerado e drift manual")
    saida = tmp / "saida-drift"
    ymls = caminhos_completos()

    plano = planejar(ymls, saida, escrever=True)
    render.escrever(list(plano.artefatos), saida)

    # Alguem edita um arquivo gerado, como faria com um equipamento real.
    alvo = saida / render.SUBDIR / f"{render.nome_de('SW-LAB-01')}{render.EXT_NORMALIZADO}"
    original = alvo.read_text(encoding="utf-8")
    alvo.write_text(
        original.replace("hostname SW-LAB-01", "hostname SW-EDITADO-NA-MAO"),
        encoding="utf-8",
        newline="\n",
    )

    d = planejar(ymls, saida, escrever=False)
    sw = next(x for x in d.diffs if x.hostname == "SW-LAB-01")
    checar(
        sw.estado == modulo_diff.DRIFT_MANUAL,
        f"edicao a mao classificada como {sw.estado}, esperado drift_manual",
    )
    checar(len(sw.diferencas) == 2, f"esperava 2 diferencas (1 add + 1 rem), veio {len(sw.diferencas)}")
    print(f"   SW-LAB-01: {sw.estado}, {len(sw.diferencas)} diferenca(s)")


def test_mudanca_gerenciada(tmp: Path) -> None:
    """Mudar o YAML e classificado como mudanca gerenciada.

    Changing the YAML is classified as a managed change.

    Args:
        tmp: Diretorio temporario de saida.

    Raises:
        Falha: Se a mudanca do YAML nao for classificada como gerenciada.
    """
    print("\n4) mudar o YAML e mudanca gerenciada")
    saida = tmp / "saida-gerenciada"
    ymls = caminhos_completos()

    plano = planejar(ymls, saida, escrever=True)
    render.escrever(list(plano.artefatos), saida)

    # Alguem mexe so no YAML: o arquivo gerado fica para tras.
    caminho_rede = RAIZ / YAML_REDE
    original = caminho_rede.read_text(encoding="utf-8")
    caminho_rede.write_text(
        original.replace("prioridade_bridge: 32768", "prioridade_bridge: 4096"),
        encoding="utf-8",
        newline="\n",
    )
    try:
        d = planejar(ymls, saida, escrever=False)
        sw = next(x for x in d.diffs if x.hostname == "SW-LAB-01")
        checar(
            sw.estado == modulo_diff.MUDANCA_GERENCIADA,
            f"mudanca no YAML classificada como {sw.estado}, "
            "esperado mudanca_gerenciada",
        )
        print(f"   SW-LAB-01: {sw.estado}, {len(sw.diferencas)} diferenca(s)")
    finally:
        caminho_rede.write_text(original, encoding="utf-8", newline="\n")


def principal() -> int:
    """Roda a prova de aceite.

    Run the acceptance proof.

    Returns:
        0 se as metades passarem, 1 se alguma falhar.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        try:
            test_dry_run_nao_escreve(tmp)
            test_duas_vezes_sem_mudanca(tmp)
            test_drift_manual(tmp)
            test_mudanca_gerenciada(tmp)
        except Falha as erro:
            print("\nACEITE FALHOU:")
            print(f"  - {erro}")
            return 1

    print("\nok: dry-run sem escrita, duas geracoes identicas, e as tres "
          "classificacoes do diff corretas")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())