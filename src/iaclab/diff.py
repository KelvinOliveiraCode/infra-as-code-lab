"""Compara o estado desejado com o estado atual.

Compare desired state with current state.

O estado atual de um equipamento ficticio e o arquivo de configuracao que o
`render.py` escreveu da ultima vez. Nao ha consulta a equipamento nenhum: o
"estado atual" e o ultimo estado gerado, guardado no disco. E assim que um
laboratorio de IaC funciona sem laboratorio.

A distincao que o modulo carrega e a que separa isto de um diff de texto:

- **drift manual**: o arquivo gerado foi editado na mao depois de gerado. O
  diff aponta a linha, e o proximo render sobrescreve a mao.
- **mudanca gerenciada**: o YAML mudou, e o arquivo gerado esta atrasado. O
  diff aponta a linha, e o proximo render conserta.
- **sem mudanca**: os dois lados iguais.

Do ponto de vista do arquivo, os dois primeiros casos produzem o mesmo diff. O
que os separa e de onde veio a diferenca: no primeiro, alguem escreveu no
arquivo; no segundo, o YAML mudou e o arquivo nao acompanhou. Por isso o
resultado carrega a classificacao, e nao so o texto.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

# Estado do arquivo gerado em relacao ao desejado.
SEM_MUDANCA = "sem_mudanca"
DRIFT_MANUAL = "drift_manual"
MUDANCA_GERENCIADA = "mudanca_gerenciada"

ROTULO_ESTADO = {
    SEM_MUDANCA: "sem mudanca",
    DRIFT_MANUAL: "drift manual",
    MUDANCA_GERENCIADA: "mudanca gerenciada",
}


class ErroDeDiff(Exception):
    """Nao deu para comparar.

    Could not compare.

    So levanta quando os dois lados nao falam a mesma lingua: o arquivo gerado
    de um equipamento que nao esta mais no YAML, ou o YAML pedindo um
    equipamento cujo arquivo nao existe. Nao e um diff com diferencas, e uma
    inability de comparar, e a CLI trata as duas coisas de forma diferente.
    """


@dataclass(frozen=True)
class Diferenca:
    """Uma diferenca de linha.

    A line difference.

    Attributes:
        tipo: 'adicionada' ou 'removida'.
        linha: Numero da linha no arquivo novo (1-based).
        texto: O conteudo da linha.
    """

    tipo: str
    linha: int
    texto: str

    def resumo(self) -> str:
        """A diferenca em uma linha.

        The difference on one line.

        Returns:
            ``+ texto`` ou ``- texto``.
        """
        marca = "+" if self.tipo == "adicionada" else "-"
        return f"{marca} {self.texto}"


@dataclass(frozen=True)
class Diff:
    """A comparacao de um equipamento.

    The comparison of one device.

    Attributes:
        equipamento: A identidade ``tipo:hostname``.
        tipo: O tipo do equipamento.
        hostname: O hostname.
        estado: Um de `SEM_MUDANCA`, `DRIFT_MANUAL`, `MUDANCA_GERENCIADA`.
        diferencas: As diferencas linha a linha.
        novo: O conteudo desejado.
        atual: O conteudo atual, ou `None` se o arquivo nao existe.
    """

    equipamento: str
    tipo: str
    hostname: str
    estado: str
    diferencas: tuple[Diferenca, ...] = ()
    novo: str = ""
    atual: str | None = None

    @property
    def alerta(self) -> bool:
        """A diferenca exige atencao.

        Whether the difference demands attention.

        Todos os estados com diferenca exigem. A distincao nao e entre
        'precisa de atencao' e 'nao precisa'; e entre *quem deve agir* - quem
        editou o arquivo a mao, ou quem precisa rodar o render.
        """
        return self.estado != SEM_MUDANCA

    @property
    def adicionadas(self) -> tuple[Diferenca, ...]:
        """So as linhas que entraram.

        Only the lines that appeared.
        """
        return tuple(d for d in self.diferencas if d.tipo == "adicionada")

    @property
    def removidas(self) -> tuple[Diferenca, ...]:
        """So as linhas que sairam.

        Only the lines that disappeared.
        """
        return tuple(d for d in self.diferencas if d.tipo == "removida")

    def texto(self, contexto: int = 3) -> str:
        """O diff no formato unificado, pronto para o terminal.

        The diff in unified format, ready for the terminal.

        Args:
            contexto: Linhas de contexto em volta de cada diferenca.

        Returns:
            O diff. Vazio quando nao ha diferenca.
        """
        if not self.diferencas:
            return ""

        antes = (self.atual or "").splitlines(keepends=True)
        depois = self.novo.splitlines(keepends=True)
        linhas = difflib.unified_diff(
            antes,
            depois,
            fromfile=f"{self.equipamento} (atual)",
            tofile=f"{self.equipamento} (desejado)",
            n=contexto,
            lineterm="\n",
        )
        return "".join(linhas)

    def resumo(self) -> str:
        """Uma linha sobre a comparacao.

        One line about the comparison.

        Returns:
            ``tipo:hostname: estado, N adicionada(s), M removida(s)``.
        """
        return (
            f"{self.equipamento}: {ROTULO_ESTADO[self.estado]}, "
            f"{len(self.adicionadas)} adicionada(s), {len(self.removidas)} removida(s)"
        )


def _classifica(
    atual: str | None,
    desejado: str,
    ultimo_gerado: str | None,
) -> str:
    """Diz em que situacao a diferenca esta.

    Say which situation the difference is in.

    A decisao se apoia no manifesto - o que foi gerado da ultima vez - e nao
    em palpite sobre o estado atual. Sem ele, as duas situacoes produzem a
    mesma comparacao e nao ha como separa-las:

    - o YAML mudou e o arquivo ficou para tras;
    - alguem editou o arquivo depois de gerado.

    Args:
        atual: O conteudo do arquivo em disco, ou `None` se nao existe.
        desejado: O conteudo gerado agora.
        ultimo_gerado: O conteudo da ultima geracao, ou `None` se nunca houve.

    Returns:
        Um dos tres estados.
    """
    if atual is None:
        # Equipamento novo: nao ha estado anterior contra o qual comparar.
        return DRIFT_MANUAL

    if atual == desejado:
        return SEM_MUDANCA

    if ultimo_gerado is None:
        # O arquivo existe e nao ha registro do que foi gerado. Nao da para
        # dizer de quem e a diferenca, e a suspeita cai em edicao manual: um
        # arquivo aqui sem manifesto veio de fora do gerador.
        return DRIFT_MANUAL

    if atual != ultimo_gerado:
        # O que esta em disco ja nao e o que o gerador produziu. Alguem
        # escreveu no arquivo. Isso e drift manual por definicao.
        return DRIFT_MANUAL

    # O que esta em disco e exatamente o que o gerador produziu da ultima
    # vez, e nao e o que ele produz agora: o YAML mudou.
    return MUDANCA_GERENCIADA


def comparar_texto(
    equipamento: str,
    tipo: str,
    hostname: str,
    desejado: str,
    atual: str | None,
    ultimo_gerado: str | None = None,
) -> Diff:
    """Compara um conteudo desejado com um atual.

    Compare a desired content with a current one.

    Args:
        equipamento: A identidade ``tipo:hostname``.
        tipo: O tipo do equipamento.
        hostname: O hostname.
        desejado: O texto gerado agora.
        atual: O texto do arquivo em disco, ou `None` se nao existe.
        ultimo_gerado: O texto da ultima geracao registrada no manifesto, ou
            `None` se nunca houve. E o que separa YAML que mudou de arquivo
            editado a mao.

    Returns:
        O diff pronto.
    """
    estado = _classifica(atual, desejado, ultimo_gerado)

    if atual is None:
        # Equipamento novo: tudo e 'adicionada'.
        diferencas = tuple(
            Diferenca("adicionada", i + 1, linha)
            for i, linha in enumerate(desejado.splitlines())
        )
    elif atual == desejado:
        diferencas = ()
    else:
        diferencas = tuple(_linhas_diff(atual, desejado))

    return Diff(
        equipamento=equipamento,
        tipo=tipo,
        hostname=hostname,
        estado=estado,
        diferencas=diferencas,
        novo=desejado,
        atual=atual,
    )


def _linhas_diff(antes: str, depois: str) -> Iterable[Diferenca]:
    """As diferencas linha a linha entre dois textos.

    The line-by-line differences between two texts.

    Args:
        antes: O texto atual.
        depois: O texto desejado.

    Yields:
        Uma `Diferenca` por linha que mudou.
    """
    a = antes.splitlines()
    b = depois.splitlines()
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("replace", "delete"):
            for k in range(i1, i2):
                yield Diferenca("removida", k + 1, a[k])
        if tag in ("replace", "insert"):
            for k in range(j1, j2):
                yield Diferenca("adicionada", k + 1, b[k])