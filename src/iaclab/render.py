"""Escreve os arquivos gerados, ou pelo menos devia.

Write the generated files, or should.

Este modulo tem uma unica responsabilidade: guardar o texto gerado em disco,
em `gerado/`. O plano decide se isso acontece; aqui nao ha opiniao. Um modulo
que escreve por conta propria seria o lugar onde o `--dry-run` poderia ser
contornado sem ninguem ver.

## Por que os dois arquivos

Cada equipamento gera dois arquivos: `.<host>.cfg` (o bruto) e
`.<host>.normalizado` (o bruto com o cabecalho da geracao removido). O
normalizado e o que o diff compara.

A razao e a mesma do projeto vizinho (config-backup-switches): o bruto e o
que a ferramenta produz, e o normalizado e o que se quer comparar. Se so o
normalizado fosse guardado, um erro na normalizacao seria invisivel - o
arquivo 'compara igual' justamente porque a informacao que faltava foi
removida dos dois lados. O bruto e o que permite descobrir isso.

O cabecalho removido e o bloco de linhas `!` no comeco do arquivo, que carrega
fonte, tipo, schema e um aviso de conteudo ficticio. Ele muda se o YAML
mudar de caminho, e nao e configuracao.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Extensao do arquivo bruto.
EXT_BRUTO = ".cfg"
# Extensao do arquivo normalizado, o que o diff compara.
EXT_NORMALIZADO = ".normalizado"
# Subpastao, dentro do diretorio de saida, onde os arquivos ficam.
SUBDIR = "gerado"
# O manifesto: o que foi gerado na ultima vez, por equipamento.
NOME_MANIFESTO = ".manifesto.json"


@dataclass(frozen=True)
class Artefato:
    """Um arquivo gerado, ainda nao escrito.

    A generated file, not yet written.

    Attributes:
        equipamento: A identidade ``tipo:hostname``.
        nome: O nome do arquivo, sem extensao.
        bruto: O texto gerado.
        normalizado: O texto sem o cabecalho da geracao.
        conteudo: Exatamente o que vai para o disco, e o que o diff compara.

    O `conteudo` existe para eliminar uma classe de bug que ja aconteceu
    durante o desenvolvimento: o `escrever` acrescentava uma quebra de linha
    final e o `plano` comparava o texto sem ela. O resultado era um plano
    acusando diferenca com zero linhas adicionadas e zero removidas, que e a
    forma mais confusa possivel de dizer "o estado atual e o desejado".
    """

    equipamento: str
    nome: str
    bruto: str
    normalizado: str

    @property
    def conteudo(self) -> str:
        """O texto exato do arquivo normalizado em disco.

        The exact text of the normalized file on disk.

        Returns:
            O normalizado com uma quebra de linha final, que e o que o
            `escrever` grava e o que o `ler_normalizado` devolve.
        """
        return self.normalizado.rstrip("\n") + "\n"

    def caminho_bruto(self, diretorio: str | Path) -> Path:
        """Onde o arquivo bruto vai ficar.

        Where the raw file goes.

        Args:
            diretorio: O diretorio de saida.

        Returns:
            O caminho completo do arquivo bruto.
        """
        return Path(diretorio) / SUBDIR / f"{self.nome}{EXT_BRUTO}"

    def caminho_normalizado(self, diretorio: str | Path) -> Path:
        """Onde o arquivo normalizado vai ficar.

        Where the normalized file goes.

        Args:
            diretorio: O diretorio de saida.

        Returns:
            O caminho completo do arquivo normalizado.
        """
        return Path(diretorio) / SUBDIR / f"{self.nome}{EXT_NORMALIZADO}"

    def resumo(self) -> str:
        """Uma linha sobre o artefato.

        One line about the artifact.

        Returns:
            ``equipamento: N linha(s)``.
        """
        return f"{self.equipamento}: {len(self.normalizado.splitlines())} linha(s)"


def nome_de(hostname: str) -> str:
    """O nome de arquivo de um equipamento.

    The file name of a device.

    Args:
        hostname: O hostname, como no YAML.

    Returns:
        O nome de arquivo, prefixado com ponto para o `gerado/` ficar limpo
        quando alguem abrir a pasta.
    """
    return f".{hostname}"


def normalizar(bruto: str) -> str:
    """Remove o cabecalho da geracao do texto.

    Remove the generation header from the text.

    O cabecalho e o bloco inicial de linhas que comecam com `!` e termina
    na linha em branco depois do bloco. Removemos o bloco inicial de
    comentarios de aviso, nao todos os comentarios - os comentarios que o
    gerador escreve dentro da configuracao (o nome da VLAN, o aviso da chave
    do AP) sao uteis e estavel, e nao devem sumir.

    Args:
        bruto: O texto gerado.

    Returns:
        O texto sem o cabecalho.
    """
    linhas = bruto.splitlines()
    inicio = 0
    # O cabecalho comeca com '!' e sua ultima linha tambem e de comentario,
    # seguido de uma linha vazia. Varre ate a primeira linha que nao e de
    # comentario depois do bloco inicial.
    if linhas and linhas[0].startswith("!"):
        for i, linha in enumerate(linhas):
            if i > 0 and not linha.startswith("!") and linha.strip() == "":
                return "\n".join(linhas[i + 1:]).lstrip("\n")
            if i > 0 and not linha.startswith("!") and linha.strip():
                return "\n".join(linhas[i:])
    return bruto


def artefato(equipamento: str, hostname: str, bruto: str) -> Artefato:
    """Monta um artefato a partir do texto gerado.

    Build an artifact from the generated text.

    Args:
        equipamento: A identidade ``tipo:hostname``.
        hostname: O hostname.
        bruto: O texto gerado.

    Returns:
        O artefato, com bruto e normalizado.
    """
    return Artefato(
        equipamento=equipamento,
        nome=nome_de(hostname),
        bruto=bruto,
        normalizado=normalizar(bruto),
    )


def escrever(artefatos: list[Artefato], diretorio: str | Path) -> list[Path]:
    """Escreve os artefatos em disco.

    Write the artifacts to disk.

    Este e o unico ponto do pacote que escreve arquivo. Ele so e chamado
    pelo `plano.py` quando o modo nao e dry-run.

    O manifesto tambem e escrito aqui. E ele que permite distinguir quem
    mudou o estado atual - ver `manifesto`.

    Args:
        artefatos: Os artefatos a escrever.
        diretorio: O diretorio de saida.

    Returns:
        Os caminhos escritos, na ordem dos artefatos.
    """
    base = Path(diretorio) / SUBDIR
    base.mkdir(parents=True, exist_ok=True)

    escritos: list[Path] = []
    for art in artefatos:
        bruto = art.caminho_bruto(diretorio)
        normalizado = art.caminho_normalizado(diretorio)
        bruto.write_text(art.bruto, encoding="utf-8", newline="\n")
        normalizado.write_text(art.conteudo, encoding="utf-8", newline="\n")
        escritos.extend([bruto, normalizado])

    manifesto_path = escrever_manifesto(artefatos, diretorio)
    escritos.append(manifesto_path)
    return escritos


def ler_normalizado(diretorio: str | Path, nome: str) -> str | None:
    """Le o arquivo normalizado de um equipamento.

    Read a device's normalized file.

    A quebra de linha e normalizada na leitura, e o `newline=""` e o que torna
    isso uma decisao e nao um acidente: sem ele, `read_text` traduz sozinho e
    o codigo nao diz nada sobre a garantia. Com ele, quem le sabe que a
    conversao acontece aqui e porquem.

    O projeto e Windows-first e o `git` do host costuma entregar CRLF; sem
    normalizar, uma virgula entre LF e CRLF produz um diff inteiro de
    arquivo, com dezenas de linhas "alteradas" que nao mudaram. E o pior tipo
    de alarme: o numero deixa de significar alguma coisa.

    Um CR solto tambem vira LF. Nao e comum, e normalizar tambem e o mais
    simples: a comparacao deve depender do conteudo, nunca de como alguma
    ferramenta gravou a quebra de linha.

    Args:
        diretorio: O diretorio de saida.
        nome: O nome do equipamento (o `nome_de`).

    Returns:
        O conteudo com LF, ou `None` se o arquivo nao existe.
    """
    caminho = Path(diretorio) / SUBDIR / f"{nome}{EXT_NORMALIZADO}"
    if not caminho.exists():
        return None
    # `Path.read_text(newline=...)` so existe no Python 3.13+. Ler em binario e
    # decodificar aqui funciona igual em 3.10, 3.11 e 3.14, e o CI roda 3.11.
    bruto = caminho.read_bytes().decode("utf-8")
    return bruto.replace("\r\n", "\n").replace("\r", "\n")


def manifesto(diretorio: str | Path) -> dict[str, str]:
    """O que foi gerado na ultima vez, por equipamento.

    What was generated last time, per device.

    Sem este registro, a classificacao de drift e um palpite. Comparar
    "desejado" com "atual" diz que *algo* mudou, mas nao diz *quem*: as duas
    situacoes abaixo produzem exatamente a mesma comparacao.

    - O YAML mudou e o arquivo ficou para tras: mudanca gerenciada.
    - Alguem editou o arquivo depois de gerado: drift manual.

    Guardando o que foi gerado por ultimo, a diferenca fica decidivel: se o
    que esta em disco e igual ao que foi gerado, ninguem mexeu e a diferenca
    vem do YAML. Se e diferente, alguem mexeu.

    Args:
        diretorio: O diretorio de saida.

    Returns:
        Mapa ``equipamento -> conteudo gerado da ultima vez``. Vazio se nunca
        houve render, ou se o manifesto nao existe.
    """
    caminho = Path(diretorio) / SUBDIR / NOME_MANIFESTO
    if not caminho.exists():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Um manifesto corrompido nao pode virar erro fatal: o plano ainda
        # sabe dizer o que e o desejado, ele so perde a distincao entre
        # gerenciada e manual, e diz isso.
        return {}
    if not isinstance(dados, dict):
        return {}
    return {str(k): str(v) for k, v in dados.items()}


def escrever_manifesto(artefatos: list[Artefato], diretorio: str | Path) -> Path:
    """Grava o manifesto do que acabou de ser gerado.

    Write the manifest of what was just generated.

    Args:
        artefatos: Os artefatos gerados.
        diretorio: O diretorio de saida.

    Returns:
        O caminho do manifesto.
    """
    base = Path(diretorio) / SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    caminho = base / NOME_MANIFESTO
    dados = {art.equipamento: art.conteudo for art in artefatos}
    caminho.write_text(
        json.dumps(dados, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return caminho


def houve_render(diretorio: str | Path) -> bool:
    """Se o diretorio de saida ja recebeu um render.

    Whether the output directory already received a render.

    Args:
        diretorio: O diretorio de saida.

    Returns:
        Verdadeiro se a subpastao `gerado/` existir e tiver algum arquivo.
    """
    base = Path(diretorio) / SUBDIR
    if not base.exists():
        return False
    return any(base.glob(f"*{EXT_NORMALIZADO}"))