"""Le os YAMLs de infraestrutura do disco.

Read the infrastructure YAMLs from disk.

Este modulo existe separado do schema porque as duas perguntas sao
diferentes. `modelo.py` responde *o que e valido*; este responde *o que ha no
disco*. A separacao permite que os testes do schema rodem sem tocar em arquivo
nenhum, e que um YAML invalido produza erro com caminho e linha, e nao com um
`KeyError` de dicionario.

## O alias `servidores:`

`infra/servidores.yaml` tem a chave `servidores:` no topo, e
`infra/rede.yaml` tem `equipamentos:`. Os dois sao listas de equipamento do
mesmo schema, e o alias e resolved aqui em vez de duplicado no schema: um
gerador nao deveria precisar saber em qual arquivo o equipamento foi
declarado, e o schema nao deveria aceitar dois nomes para a mesma coisa.

A recusa de um terceiro nome e deliberada. Um alias que aceita qualquer
coisa que "parece com" um dos nomes aceita tambem o nome errado, e o
equipamento some do plano sem erro nenhum.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .modelo import ErroDeSchema, Infraestrutura, de_documento, unir

# Chave que o schema entende para lista de equipamentos.
CHAVE_EQUIPAMENTOS = "equipamentos"

# Alias aceito por arquivo, porque o nome do arquivo ja diz do que se trata.
ALIAS_EQUIPAMENTOS: dict[str, str] = {"servidores": CHAVE_EQUIPAMENTOS}

# Chaves de topo conhecidas. Uma chave desconhecida e quase sempre erro de
# digitacao, e uma chave ignorada em silencio e um inventario inteiro que
# alguem editou sem querer.
CHAVES_CONHECIDAS = frozenset(
    {
        "rede",
        "servidor",
        "sistema",
        "vlans",
        CHAVE_EQUIPAMENTOS,
        "acessos",
        "administradores",
        *ALIAS_EQUIPAMENTOS,
    }
)


def _normaliza_alias(documento: dict[str, Any], origem: str) -> dict[str, Any]:
    """Troca o alias de equipamentos pela chave canonica.

    Replace the equipment alias with the canonical key.

    Args:
        documento: O mapa lido do YAML, ja convertido.
        origem: Caminho do arquivo, usado nos erros.

    Returns:
        O mapa com a chave canonica presente.

    Raises:
        ErroDeSchema: Se o arquivo trouxer o alias e a chave canonica juntos.
    """
    resultado = dict(documento)
    for alias, canonica in ALIAS_EQUIPAMENTOS.items():
        if alias not in resultado:
            continue
        if canonica in resultado:
            raise ErroDeSchema(
                [
                    f"{alias} e {canonica} nao podem aparecer juntos: "
                    "o mesmo campo com dois nomes"
                ],
                origem,
            )
        resultado[canonica] = resultado.pop(alias)
    return resultado


def _confere_chaves(documento: dict[str, Any], origem: str) -> None:
    """Recusa chave de topo desconhecida.

    Reject an unknown top-level key.

    Args:
        documento: O mapa lido do YAML.
        origem: Caminho do arquivo, usado nos erros.

    Raises:
        ErroDeSchema: Se houver chave fora de `CHAVES_CONHECIDAS`.
    """
    desconhecidas = sorted(set(documento) - CHAVES_CONHECIDAS)
    if desconhecidas:
        # Uma mensagem por chave desconhecida, nao uma junta: quem tem tres
        # erros de digitacao no topo do arquivo quer corrigir os tres de uma
        # vez, e nao descobrir um por execucao.
        raise ErroDeSchema(
            [
                f"{chave}: chave de topo desconhecida; "
                f"aceitas: {', '.join(sorted(CHAVES_CONHECIDAS))}"
                for chave in desconhecidas
            ],
            origem,
        )


def carregar_arquivo(caminho: str | Path) -> Infraestrutura:
    """Le um YAML e devolve a infraestrutura validada.

    Read one YAML and return the validated infrastructure.

    Args:
        caminho: Caminho do arquivo.

    Returns:
        A infraestrutura declarada no arquivo.

    Raises:
        ErroDeSchema: Se o arquivo nao existir, nao for um mapa, ou nao passar
            na validacao.
    """
    caminho = Path(caminho)
    origem = str(caminho)

    if not caminho.exists():
        raise ErroDeSchema([f"arquivo nao encontrado: {origem}"], origem)

    try:
        documento = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as erro:
        raise ErroDeSchema([f"YAML invalido: {erro}"], origem) from None

    if not isinstance(documento, dict):
        raise ErroDeSchema(["o arquivo precisa ser um mapa no topo"], origem)

    _confere_chaves(documento, origem)
    documento = _normaliza_alias(documento, origem)
    return de_documento(documento, origem)


def carregar(caminhos: list[str | Path]) -> Infraestrutura:
    """Le varios YAMLs e junta tudo numa infraestrutura so.

    Read several YAMLs and merge them into one infrastructure.

    A juncao e feita aqui e nao no schema porque a falha que importa e
    cruzada: dois arquivos que declaram o mesmo equipamento. Isso so aparece
    quando os dois ja foram lidos.

    Args:
        caminhos: Os arquivos, em ordem de precedencia.

    Returns:
        A infraestrutura unida. Vazia se nenhum arquivo for dado.

    Raises:
        ErroDeSchema: Se algum arquivo falhar, ou se a juncao for contraditoria.
    """
    resultado: Infraestrutura | None = None

    for caminho in caminhos:
        atual = carregar_arquivo(caminho)
        resultado = atual if resultado is None else unir(resultado, atual)

    return resultado if resultado is not None else Infraestrutura()