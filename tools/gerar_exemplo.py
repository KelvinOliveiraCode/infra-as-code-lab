"""Gera o exemplo de plano, de forma deterministica.

Generate the plan example, deterministically.

O exemplo vai para o repositorio para ser lido sem instalar nada, e por isso
precisa ser reproduzivel: se duas execucoes produzissem textos diferentes, o
`git diff --exit-code` do CI acusaria uma mudanca a cada build e o arquivo
deixaria de servir como documentacao.

A saida e deterministica porque nada aqui depende de:

- **relogio**: nao ha timestamp, nem na saida nem nos arquivos gerados;
- **ordem de hash**: os equipamentos seguem a ordem de declaracao do YAML;
- **semente do simulador**: nao ha simulador; o YAML ja e o estado desejado.

## O que o exemplo mostra

Tres momentos em um, porque os tres juntos explicam a ferramenta melhor do
que tres exemplos separados:

1. o **plano inicial**, que acusa todos os equipamentos porque nada foi
   gerado ainda;
2. o **plano depois de gerar**, que sai limpo - o criterio de aceite;
3. um **drift manual**, com uma linha editada a mao no arquivo gerado.

O terceiro e o que a suite nao prova sozinha: ele depende do manifesto em
disco, e um manifesto escrito errado faz a classificacao errada em silencio.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from iaclab import render  # noqa: E402
from iaclab.cli import DATA_FIXA  # noqa: E402
from iaclab.cli import main as cli_main  # noqa: E402
from iaclab.plano import planejar  # noqa: E402

YAML = [
    str(RAIZ / "infra" / "rede.yaml"),
    str(RAIZ / "infra" / "servidores.yaml"),
    str(RAIZ / "infra" / "acessos.yaml"),
]

DESTINO = RAIZ / "exemplos" / "plano-execucao.txt"

# A linha que o exemplo edita a mao para mostrar o drift.
LINHA_EDITADA = "hostname SW-LAB-01"
SUBSTITUICAO = "hostname SW-LAB-EDITADO-NO-MOMENTO"


def _roda_cli(argv: list[str]) -> str:
    """Roda a CLI e devolve a saida, sem o cabecalho do argparse.

    Run the CLI and return the output, without the argparse header.

    Args:
        argv: Os argumentos.

    Returns:
        A saida em texto.
    """
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        codigo = cli_main(argv)
    return f"[codigo de saida: {codigo}]\n" + buffer.getvalue()


def principal() -> int:
    """Regera o exemplo e grava no destino.

    Regenerate the example and write it to the destination.

    Returns:
        Sempre 0.
    """
    partes: list[str] = [
        "# Exemplo de plano do iaclab.",
        "#",
        "# Este arquivo e GERADO por tools/gerar_exemplo.py. Nao editar a mao.",
        "#",
        "# A saida e deterministica de proposito: nao ha timestamp em nenhum",
        "# lugar, para que o `git diff --exit-code` do CI possa conferir se o",
        "# exemplo ainda corresponde ao que o codigo faz.",
        "#",
        "# Comando correspondente ao bloco abaixo:",
        "#",
        "#   python -m iaclab plano --infra infra/rede.yaml \\",
        "#       --infra infra/servidores.yaml --infra infra/acessos.yaml",
        "",
        "=" * 72,
        "1) PLANO INICIAL - antes de gerar qualquer arquivo",
        "=" * 72,
        "",
        "Todo equipamento acusa diferenca, porque nenhum arquivo foi gerado",
        "ainda. E o estado esperado de um repositorio novo: nao ha contra o que",
        "comparar.",
        "",
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        saida = Path(tmpdir) / "saida"
        argv_plano = ["plano"]
        for caminho in YAML:
            argv_plano += ["--infra", caminho]
        argv_plano += ["--saida", str(saida)]

        partes.append(_roda_cli(argv_plano))

        # --- depois de gerar ---
        partes += [
            "",
            "=" * 72,
            "2) PLANO DEPOIS DE GERAR - o criterio de aceite",
            "=" * 72,
            "",
            "O mesmo plano, depois de rodar `gerar` duas vezes sem mudar nada",
            "no YAML. E aqui que a idempotencia aparece: a segunda geracao",
            "produz arquivo identico e o plano sai limpo.",
            "",
        ]

        argv_gerar = ["gerar"]
        for caminho in YAML:
            argv_gerar += ["--infra", caminho]
        argv_gerar += ["--saida", str(saida)]

        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            cli_main(argv_gerar)
        with contextlib.redirect_stdout(io.StringIO()):
            cli_main(argv_gerar)

        partes.append(_roda_cli(argv_plano))

        # --- drift manual ---
        partes += [
            "",
            "=" * 72,
            "3) DRIFT MANUAL - alguem editou o arquivo gerado",
            "=" * 72,
            "",
            "Uma linha do arquivo gerado foi alterada fora do processo, como",
            "acontece quando alguem entra no equipamento e mexe direto. O plano",
            "distingue isso da mudanca gerenciada, e a distincao muda a resposta",
            "do time: uma e trabalho scheduled, a outra e incidente.",
            "",
        ]

        alvo = saida / render.SUBDIR / f"{render.nome_de('SW-LAB-01')}{render.EXT_NORMALIZADO}"
        conteudo = alvo.read_text(encoding="utf-8")
        alvo.write_text(
            conteudo.replace(LINHA_EDITADA, SUBSTITUICAO),
            encoding="utf-8",
            newline="\n",
        )

        partes.append(_roda_cli(argv_plano))

    partes += [
        "",
        "=" * 72,
        "O QUE ESTE EXEMPLO NAO MOSTRA",
        "=" * 72,
        "",
        "- O projeto nao aplica mudanca em equipamento nenhum. Nao existe",
        "  comando que aplique: `plano` mostra e `gerar` escreve arquivo local,",
        "  e nada mais.",
        "- O YAML deste laboratorio e ficticio. As faixas sao RFC 1918 e nao ha",
        "  nenhum equipamento real por tras.",
        "- O plano nao valida conectividade, nao testa rota e nao fala com",
        "  nenhum host. Ele compara texto.",
        "",
    ]

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text("\n".join(partes), encoding="utf-8", newline="\n")
    print(f"exemplo gravado em {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())