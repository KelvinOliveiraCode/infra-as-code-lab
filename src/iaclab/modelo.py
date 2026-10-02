"""O schema declarativo do iaclab.

The declarative schema of iaclab.

Toda a infraestrutura do portfolio e descrita em YAML, nunca em arquivo de
configuracao de equipamento. Este modulo define o que um YAML pode dizer e o
que ele nao pode.

A distincao que organiza o modulo: **o que e** (`Infraestrutura`) e **o que
esta errado** (`ErroDeSchema`). Separar as duas coisas e o que permite que o
`cli.py` possa rodar o `diff` mesmo sobre um arquivo invalido - o diff mostra
as diferencas que da para ver e o plano lista o que impediu o resto.

A validacao e feita na carga, nao na geracao. Um YAML invalido que so falha
quando o gerador roda produz um erro no lugar menos util possivel: a meio de
um arquivo de saida, com tres equipamentos ja escritos e o quarto quebrado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

# Nomes de tipo aceitos em `tipo:`. A lista e fechada de proposito: um
# gerador novo entra aqui, junto com a funcao que o atende, e nao como um
# `getattr` que aceita qualquer nome e so quebra depois.
TIPOS_CONHECIDOS = ("switch", "firewall", "ap", "servidor")

# Nomes de chave aceitos em cada tipo. Tambem fechados, pelo mesmo motivo:
# um campo nao previsto aqui e quase sempre erro de digitacao, e um erro de
# digitacao que o gerador ignora em silencio vira um equipamento no arquivo
# de saida sem uma VLAN, discovered no dia da mudanca.
#
# `descricao` e comum a todos porque todo equipamento tem motivo de existir e
# o motivo vai para o arquivo gerado.
CAMPOS_POR_TIPO: dict[str, tuple[str, ...]] = {
    "switch": (
        "hostname", "modelo", "vlan", "portas", "stp", "semente", "descricao",
    ),
    "firewall": (
        "hostname", "modelo", "vlan", "zonas", "regras", "nat", "descricao",
    ),
    "ap": (
        "hostname", "modelo", "vlan", "ssid", "canal", "sinal", "descricao",
    ),
    "servidor": (
        "hostname", "sistema", "grupos", "usuarios", "permissoes", "descricao",
    ),
}

_CAMPOS_COMUNS = ("hostname",)


class ErroDeSchema(Exception):
    """O YAML descreve algo que o schema nao aceita.

    The YAML describes something the schema does not accept.

    Carrega a lista de problemas em vez de estourar no primeiro: quem escreve
    o arquivo quer todos os erros de uma vez, nao uma ida por vez.
    """

    def __init__(self, problemas: Sequence[str], origem: str = "") -> None:
        self.problemas = tuple(problemas)
        self.origem = origem
        detalhe = "; ".join(self.problemas)
        sufixo = f" em {origem}" if origem else ""
        super().__init__(f"schema invalido{sufixo}: {detalhe}")


@dataclass(frozen=True)
class Vlan:
    """Uma VLAN declarada.

    A declared VLAN.

    Attributes:
        id: Numero da VLAN.
        nome: Nome logico, o que aparece no relatorio.
        faixa: Prefixo CIDR da rede.
        gateway: Primeiro endereco utilizavel da faixa, ou `None`.
        descricao: Para que a VLAN serve.
    """

    id: int
    nome: str
    faixa: str
    gateway: str | None = None
    descricao: str = ""

    def validar(self, problemas: list[str], onde: str) -> None:
        """Acumula os problemas deste objeto.

        Collect this object's problems.

        Args:
            problemas: Lista onde os problemas sao acumulados.
            onde: Prefixo de caminho, para o erro apontar o lugar.
        """
        if not 1 <= self.id <= 4094:
            problemas.append(f"{onde}.id: {self.id} fora de 1..4094")
        if not self.nome.strip():
            problemas.append(f"{onde}.nome: vazio")
        if not self.faixa or "/" not in self.faixa:
            problemas.append(f"{onde}.faixa: {self.faixa!r} nao e CIDR")
        if self.gateway is not None and "/" in self.gateway:
            problemas.append(f"{onde}.gateway: {self.gateway!r} e um endereco, nao uma faixa")


@dataclass(frozen=True)
class Equipamento:
    """Um equipamento declarado, ainda sem gerar nada.

    A declared device, before anything is generated.

    O `bruto` guarda o mapa original. Nao e decoracao: sem ele, a ordem das
    chaves se perde na ida e na volta, e um diff entre duas versoes do YAML
    acusaria reordenacao como mudanca de configuracao.

    Attributes:
        tipo: Um de `TIPOS_CONHECIDOS`.
        campos: Conteudo especifico do tipo, ja validado como mapa.
        bruto: O mapa como veio do YAML.
        origem: Caminho do arquivo de onde veio.
    """

    tipo: str
    campos: dict[str, Any] = field(default_factory=dict)
    bruto: dict[str, Any] = field(default_factory=dict)
    origem: str = ""

    @property
    def hostname(self) -> str:
        """O identificador do equipamento.

        The device identifier.
        """
        return str(self.campos.get("hostname", "desconhecido"))

    @property
    def identidade(self) -> str:
        """A chave unica de um equipamento no plano.

        The unique key of a device in the plan.

        Inclui o tipo porque dois equipamentos de tipos diferentes podem
        plausivelmente ter o mesmo hostname em inventarios mantidos a mao.
        """
        return f"{self.tipo}:{self.hostname}"


@dataclass(frozen=True)
class Infraestrutura:
    """Tudo que um ou mais YAMLs descrevem.

    Everything one or more YAMLs describe.

    Attributes:
        vlans: VLANs declaradas, em ordem de declaracao.
        equipamentos: Equipamentos declarados.
        acessos: Regras de acesso a servidores, se o arquivo as trouxe.
        origem: Caminho do arquivo principal.
    """

    vlans: tuple[Vlan, ...] = ()
    equipamentos: tuple[Equipamento, ...] = ()
    acessos: tuple[dict[str, Any], ...] = ()
    origem: str = ""

    def por_tipo(self, tipo: str) -> tuple[Equipamento, ...]:
        """Os equipamentos de um tipo, na ordem de declaracao.

        Devices of one type, in declaration order.

        Args:
            tipo: Um de `TIPOS_CONHECIDOS`.

        Returns:
            Tupla dos equipamentos pedidos.
        """
        return tuple(e for e in self.equipamentos if e.tipo == tipo)

    def vlan(self, identificador: Any) -> Vlan | None:
        """Ache uma VLAN por id, nome ou faixa.

        Find a VLAN by id, name or subnet.

        A acceptacao de tres criterios e deliberada. Quem escreve o YAML
        lembra o numero; quem revisa o diff lembra o nome. Obrigar um unico
        criterio faria a mesma rede aparecer de duas formas no repositorio.

        Args:
            identificador: Id, nome ou faixa a procurar.

        Returns:
            A VLAN, ou `None` se nenhuma casar.
        """
        alvo = str(identificador)
        for v in self.vlans:
            if alvo in (str(v.id), v.nome, v.faixa):
                return v
        return None


def _exige(
    item: dict[str, Any],
    tipo: str,
    problemas: list[str],
    onde: str,
) -> None:
    """Checa os campos obrigatorios de um equipamento.

    Check the required fields of a device.

    Args:
        item: O mapa do equipamento.
        tipo: O tipo declarado.
        problemas: Lista onde os problemas sao acumulados.
        onde: Prefixo de caminho.
    """
    for chave in _CAMPOS_COMUNS:
        if not str(item.get(chave, "")).strip():
            problemas.append(f"{onde}.{chave}: obrigatorio")

    conhecidos = set(CAMPOS_POR_TIPO[tipo])
    for chave in item:
        if chave not in conhecidos:
            problemas.append(
                f"{onde}.{chave}: campo desconhecido para tipo {tipo!r}; "
                f"aceitos: {', '.join(sorted(conhecidos))}"
            )


def validar_vlans(bruto: Any, problemas: list[str]) -> tuple[Vlan, ...]:
    """Valida a secao de VLANs de um YAML.

    Validate the VLAN section of a YAML.

    Args:
        bruto: O valor cru da chave `vlans`.
        problemas: Lista onde os problemas sao acumulados.

    Returns:
        As VLANs validas, na ordem de declaracao.

    Raises:
        ErroDeSchema: Se `problemas` nao estiver vazio ao final.
    """
    if bruto is None:
        return ()

    if not isinstance(bruto, list):
        problemas.append("vlans: esperado uma lista")
        raise ErroDeSchema(problemas)

    vlans: list[Vlan] = []
    vistos: set[int] = set()
    for indice, item in enumerate(bruto):
        onde = f"vlans[{indice}]"
        if not isinstance(item, dict):
            problemas.append(f"{onde}: esperado um mapa")
            continue
        try:
            vlan = Vlan(
                id=int(item.get("id", -1)),
                nome=str(item.get("nome", "")),
                faixa=str(item.get("faixa", "")),
                gateway=(
                    str(item["gateway"]) if item.get("gateway") else None
                ),
                descricao=str(item.get("descricao", "")),
            )
        except (TypeError, ValueError):
            problemas.append(f"{onde}.id: {item.get('id')!r} nao e inteiro")
            continue
        if vlan.id in vistos:
            problemas.append(f"{onde}.id: VLAN {vlan.id} declarada duas vezes")
        vistos.add(vlan.id)
        vlan.validar(problemas, onde)
        vlans.append(vlan)

    return tuple(vlans)


def validar_equipamentos(
    bruto: Any,
    problemas: list[str],
    origem: str = "",
) -> tuple[Equipamento, ...]:
    """Valida a secao de equipamentos de um YAML.

    Validate the equipment section of a YAML.

    Args:
        bruto: O valor cru da chave `equipamentos`.
        problemas: Lista onde os problemas sao acumulados.
        origem: Caminho do arquivo, usado no erro.

    Returns:
        Os equipamentos validos, na ordem de declaracao.

    Raises:
        ErroDeSchema: Se `problemas` nao estiver vazio ao final.
    """
    if bruto is None:
        return ()

    if not isinstance(bruto, list):
        problemas.append("equipamentos: esperado uma lista")
        raise ErroDeSchema(problemas)

    equipamentos: list[Equipamento] = []
    identidades: set[str] = set()
    for indice, item in enumerate(bruto):
        onde = f"equipamentos[{indice}]"
        if not isinstance(item, dict):
            problemas.append(f"{onde}: esperado um mapa")
            continue

        tipo = str(item.get("tipo", "")).strip()
        if tipo not in TIPOS_CONHECIDOS:
            problemas.append(
                f"{onde}.tipo: {tipo!r} desconhecido; "
                f"aceitos: {', '.join(TIPOS_CONHECIDOS)}"
            )
            continue

        campos = {k: v for k, v in item.items() if k != "tipo"}
        _exige(campos, tipo, problemas, onde)

        equipamento = Equipamento(
            tipo=tipo,
            campos=campos,
            bruto=dict(item),
            origem=origem,
        )
        if equipamento.identidade in identidades:
            problemas.append(
                f"{onde}: {equipamento.identidade} declarado duas vezes"
            )
        identidades.add(equipamento.identidade)
        equipamentos.append(equipamento)

    return tuple(equipamentos)


def validar_acessos(bruto: Any, problemas: list[str]) -> tuple[dict[str, Any], ...]:
    """Valida a secao de acessos de um YAML.

    Validate the access section of a YAML.

    Args:
        bruto: O valor cru da chave `acessos`.
        problemas: Lista onde os problemas sao acumulados.

    Returns:
        As regras de acesso, na ordem de declaracao.

    Raises:
        ErroDeSchema: Se `problemas` nao estiver vazio ao final.
    """
    if bruto is None:
        return ()

    if not isinstance(bruto, list):
        problemas.append("acessos: esperado uma lista")
        raise ErroDeSchema(problemas)

    acessos: list[dict[str, Any]] = []
    for indice, item in enumerate(bruto):
        onde = f"acessos[{indice}]"
        if not isinstance(item, dict):
            problemas.append(f"{onde}: esperado um mapa")
            continue
        for chave in ("servidor", "grupo", "permissao"):
            if not str(item.get(chave, "")).strip():
                problemas.append(f"{onde}.{chave}: obrigatorio")
        acessos.append(dict(item))

    return tuple(acessos)


def unir(infra: Infraestrutura, outra: Infraestrutura) -> Infraestrutura:
    """Junta duas infraestruturas carregadas de arquivos diferentes.

    Merge two infrastructures loaded from different files.

    Args:
        infra: A primeira.
        outra: A segunda.

    Returns:
        A uniao, com a ordem de declaracao preservada de cada lado.

    Raises:
        ErroDeSchema: Se as duas lado declararem a mesma identidade ou o
            mesmo id de VLAN. A ordem de declaracao e preservada para que
            saida gerada seja identica entre execucoes.
    """
    problemas: list[str] = []

    identidades: set[str] = set()
    for equipamento in infra.equipamentos + outra.equipamentos:
        if equipamento.identidade in identidades:
            problemas.append(
                f"{equipamento.identidade}: declarado em {infra.origem or outra.origem} "
                "e tambem no outro arquivo"
            )
        identidades.add(equipamento.identidade)

    ids: set[int] = set()
    for vlan in infra.vlans + outra.vlans:
        if vlan.id in ids:
            problemas.append(f"VLAN {vlan.id} declarada nos dois arquivos")
        ids.add(vlan.id)

    if problemas:
        raise ErroDeSchema(problemas)

    return Infraestrutura(
        vlans=infra.vlans + outra.vlans,
        equipamentos=infra.equipamentos + outra.equipamentos,
        acessos=infra.acessos + outra.acessos,
        origem=infra.origem or outra.origem,
    )


def de_documento(
    documento: dict[str, Any],
    origem: str = "",
) -> Infraestrutura:
    """Constroi uma `Infraestrutura` a partir de um documento ja lido.

    Build an `Infraestrutura` from an already-read document.

    Args:
        documento: O mapa do YAML, ja convertido.
        origem: Caminho do arquivo, usado nos erros.

    Returns:
        A infraestrutura validada.

    Raises:
        ErroDeSchema: Se o documento nao passar na validacao.
    """
    problemas: list[str] = []
    vlans = validar_vlans(documento.get("vlans"), problemas)
    equipamentos = validar_equipamentos(documento.get("equipamentos"), problemas, origem)
    acessos = validar_acessos(documento.get("acessos"), problemas)

    if problemas:
        raise ErroDeSchema(problemas, origem)

    return Infraestrutura(
        vlans=vlans,
        equipamentos=equipamentos,
        acessos=acessos,
        origem=origem,
    )


def iterar_tipos() -> Iterator[str]:
    """Os tipos na ordem em que o plano processa.

    The types in the order the plan processes them.

    A ordem e fixa e e a mesma do dicionario de campos. Um plano que
    processa equipamentos em ordem de hash muda de ordem entre execucoes, e
    o diff passa a acusar reordenacao.

    Yields:
        Cada tipo conhecido, uma vez.
    """
    yield from CAMPOS_POR_TIPO


def campos_de(tipo: str) -> tuple[str, ...]:
    """Os campos aceitos por um tipo.

    The fields accepted by a type.

    Args:
        tipo: Um de `TIPOS_CONHECIDOS`.

    Returns:
        Os nomes de campo, na ordem do schema.

    Raises:
        KeyError: Se o tipo nao existir. E proposito: um tipo desconhecido
            aqui e um gerador que ninguem escreveu.
    """
    return CAMPOS_POR_TIPO[tipo]


def referencias_quebradas(infra: Infraestrutura) -> list[str]:
    """Acha referencias a VLANs que nao existem.

    Find references to VLANs that do not exist.

    Chamado depois da validacao, e separado dela de proposito: um equipamento
    que cita `vlan: 99` e um YAML bem formado com um erro de inventario. A
    forma de corrigir e diferente - corrigir o YAML nao o schema.

    Args:
        infra: A infraestrutura ja validada.

    Returns:
        Uma mensagem por referencia quebrada, na ordem de declaracao.
    """
    problemas: list[str] = []
    for equipamento in infra.equipamentos:
        if "vlan" not in equipamento.campos:
            continue
        declarado = equipamento.campos["vlan"]
        if infra.vlan(declarado) is None:
            problemas.append(
                f"{equipamento.identidade}: vlan {declarado!r} nao declarada"
            )
    return problemas
