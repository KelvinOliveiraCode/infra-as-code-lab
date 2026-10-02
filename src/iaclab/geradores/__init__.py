"""Geradores de configuracao, um por tipo de equipamento.

Configuration generators, one per device type.

Cada modulo daqui implementa `GeradorBase` e atende a um tipo. O `__init__.py`
deste pacote e o unico lugar que sabe a lista completa, porque um lugar
so e o unico que pode continuar sendo verdade quando entra um gerador novo.
"""

from __future__ import annotations

from ..modelo import TIPOS_CONHECIDOS, ErroDeSchema
from .base import CABECALHO, VERSAO_SCHEMA, GeradorBase, juntar

__all__ = [
    "CABECALHO",
    "VERSAO_SCHEMA",
    "GeradorBase",
    "GeradorNaoConhecido",
    "juntar",
    "por_tipo",
    "todos",
]


class GeradorNaoConhecido(GeradorBase):
    """Erro de leitura para um tipo sem gerador.

    A read error for a type without a generator.

    Existe como gerador para que a falha apareca com o mesmo formato das
    outras. Um tipo aceito pelo schema e sem gerador escrito e uma falha de
    desenvolvimento, nao um dado invalido: o plano tem de dizer qual tipo
    falta, nao devolver `None` e estourar tres niveis acima.
    """

    def __init__(self, tipo: str) -> None:
        self.tipo = tipo

    def linhas(self, equipamento, infra):  # type: ignore[no-untyped-def]
        """Sempre falha.

        Always fails.

        Args:
            equipamento: O equipamento sem gerador.
            infra: A infraestrutura inteira.

        Raises:
            ErroDeSchema: Sempre.
        """
        raise ErroDeSchema(
            [
                f"nenhum gerador para o tipo {self.tipo!r}; "
                "os tipos com gerador sao os de TIPOS_CONHECIDOS"
            ]
        )


def _registro() -> dict[str, type[GeradorBase]]:
    """Os geradores disponiveis, por tipo.

    Importados aqui, e nao no topo do modulo, para nao criar ciclo: os
    geradores importam de `.base`, e `base` nao importa deste modulo.

    Returns:
        Mapa ``tipo -> classe``.
    """
    from .ap import GeradorAP
    from .firewall import GeradorFirewall
    from .servidor import GeradorServidor
    from .switch import GeradorSwitch

    return {
        GeradorSwitch.tipo: GeradorSwitch,
        GeradorFirewall.tipo: GeradorFirewall,
        GeradorAP.tipo: GeradorAP,
        GeradorServidor.tipo: GeradorServidor,
    }


def todos() -> dict[str, type[GeradorBase]]:
    """Todos os geradores, por tipo.

    All generators, by type.

    Returns:
        Mapa ``tipo -> classe``.
    """
    return _registro()


def por_tipo(tipo: str) -> GeradorBase:
    """O gerador de um tipo.

    The generator of a type.

    Args:
        tipo: Um de `TIPOS_CONHECIDOS`.

    Returns:
        Uma instancia pronta para gerar.

    Raises:
        ErroDeSchema: Se o tipo nao tiver gerador.
    """
    registro = _registro()
    classe = registro.get(tipo)
    if classe is None:
        return GeradorNaoConhecido(tipo)
    return classe()