"""Gerador de configuracao de switch.

Switch configuration generator.

Traduz a declaracao de um switch em sintaxe Cisco-like ficticia: VLANs,
portas de acesso, trunks e spanning-tree.

O switch e o gerador de referencia do projeto. Os outros tres seguem a mesma
forma, e ele existe para ser o exemplo concreto de como escrever um: as
validacoes que o schema nao faz, a ordem das secoes, e o uso de `juntar()`.
"""

from __future__ import annotations

from typing import Any

from ..modelo import Equipamento, Infraestrutura
from .base import GeradorBase, juntar

# Modos de porta aceitos. Uma porta em trunk tem lista de VLANs; uma em access
# tem uma VLAN so. A distincao e do schema de equipamento, nao do Cisco, e
# por isso mora aqui.
MODO_ACCESS = "access"
MODO_TRUNK = "trunk"
MODOS_PORTA = (MODO_ACCESS, MODO_TRUNK)


class GeradorSwitch(GeradorBase):
    """Configuracao de switch a partir da declaracao.

    Switch configuration from the declaration.
    """

    tipo = "switch"

    def validar(self, infra: Infraestrutura) -> list[str]:
        """Checa portas, trunks e spanning-tree.

        Check ports, trunks and spanning-tree.

        Args:
            infra: A infraestrutura inteira.

        Returns:
            Uma mensagem por problema encontrado.
        """
        problemas: list[str] = []

        for equipamento in infra.por_tipo(self.tipo):
            identidade = equipamento.identidade
            portas = equipamento.campos.get("portas") or []

            if not isinstance(portas, list):
                problemas.append(f"{identidade}.portas: esperado uma lista")
                continue

            nomes: set[str] = set()
            for indice, porta in enumerate(portas):
                onde = f"{identidade}.portas[{indice}]"
                if not isinstance(porta, dict):
                    problemas.append(f"{onde}: esperado um mapa")
                    continue

                nome = str(porta.get("nome", "")).strip()
                if not nome:
                    problemas.append(f"{onde}.nome: obrigatorio")
                elif nome in nomes:
                    problemas.append(f"{onde}.nome: {nome} repetida")
                else:
                    nomes.add(nome)

                modo = str(porta.get("modo", MODO_ACCESS))
                if modo not in MODOS_PORTA:
                    problemas.append(
                        f"{onde}.modo: {modo!r} desconhecido; "
                        f"aceitos: {', '.join(MODOS_PORTA)}"
                    )

                if modo == MODO_ACCESS:
                    if infra.vlan(porta.get("vlan")) is None:
                        problemas.append(
                            f"{onde}.vlan: {porta.get('vlan')!r} nao declarada"
                        )
                else:
                    trunks = porta.get("trunks")
                    if not isinstance(trunks, list) or not trunks:
                        problemas.append(
                            f"{onde}.trunks: porta trunk sem lista de VLANs"
                        )
                    else:
                        for vlan in trunks:
                            if infra.vlan(vlan) is None:
                                problemas.append(
                                    f"{onde}.trunks: vlan {vlan!r} nao declarada"
                                )

            problemas.extend(self._valida_stp(equipamento, nomes, infra))

        return problemas

    def _valida_stp(
        self,
        equipamento: Equipamento,
        nomes: set[str],
        infra: Infraestrutura,
    ) -> list[str]:
        """Checa o bloco de spanning-tree.

        Check the spanning-tree block.

        Args:
            equipamento: O switch.
            nomes: Os nomes de porta ja vistos.
            infra: A infraestrutura inteira.

        Returns:
            Uma mensagem por problema.
        """
        problemas: list[str] = []
        stp = equipamento.campos.get("stp")
        if stp is None:
            return problemas

        identidade = equipamento.identidade
        if not isinstance(stp, dict):
            return [f"{identidade}.stp: esperado um mapa"]

        for chave in ("portfast", "bpdu_guard"):
            portas = stp.get(chave) or []
            if not isinstance(portas, list):
                problemas.append(f"{identidade}.stp.{chave}: esperado uma lista")
                continue
            for porta in portas:
                if porta not in nomes:
                    problemas.append(
                        f"{identidade}.stp.{chave}: porta {porta!r} nao declarada"
                    )

        return problemas

    def linhas(self, equipamento: Equipamento, infra: Infraestrutura) -> list[str]:
        """As linhas de configuracao do switch.

        The switch configuration lines.

        A ordem e: identidade, VLANs, portas, spanning-tree. E a ordem em que
        quem le o arquivo espera encontrar cada coisa.

        Args:
            equipamento: O switch a traduzir.
            infra: A infraestrutura inteira.

        Returns:
            As linhas, sem cabecalho.
        """
        campos = equipamento.campos

        blocos: list[list[str]] = [self._bloco_identidade(equipamento)]
        blocos.append(self._bloco_vlans(campos))
        blocos.append(self._bloco_portas(campos, infra))
        blocos.append(self._bloco_stp(campos, infra))
        return juntar(blocos)

    # ---------------------------------------------------------------- blocos

    def _bloco_identidade(self, equipamento: Equipamento) -> list[str]:
        """Hostname e modelo.

        Hostname and model.

        Args:
            equipamento: O switch.

        Returns:
            As linhas de identificacao.
        """
        campos = equipamento.campos
        linhas = [
            f"hostname {campos.get('hostname', 'desconhecido')}",
        ]
        modelo = campos.get("modelo")
        if modelo:
            linhas.append(f"! modelo {modelo}")
        return linhas

    def _bloco_vlans(self, campos: dict[str, Any]) -> list[str]:
        """As VLANs de gerenciamento do switch.

        The management VLANs of the switch.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de VLAN.
        """
        bloco = self._secao("VLAN de gerenciamento")
        vlan = campos.get("vlan")
        if vlan is None:
            return bloco
        return [f"interface Vlan{vlan}", f" description {self._comentario(vlan)}", " exit"]

    def _bloco_portas(
        self,
        campos: dict[str, Any],
        infra: Infraestrutura,
    ) -> list[str]:
        """Uma `interface` por porta.

        One `interface` per port.

        Args:
            campos: Os campos do equipamento.
            infra: A infraestrutura inteira.

        Returns:
            As linhas de porta.
        """
        bloco = self._secao("portas")
        for porta in campos.get("portas") or []:
            if not isinstance(porta, dict):
                continue
            bloco.extend(self._linhas_porta(porta, infra))
        return bloco

    def _linhas_porta(self, porta: dict[str, Any], infra: Infraestrutura) -> list[str]:
        """As linhas de uma porta.

        The lines of one port.

        Args:
            porta: A declaracao da porta.
            infra: A infraestrutura inteira.

        Returns:
            As linhas da porta, com `exit` no fim.
        """
        modo = str(porta.get("modo", MODO_ACCESS))
        linhas = [f"interface {porta.get('nome', '?')}"]

        descricao = porta.get("descricao")
        if descricao:
            linhas.append(f" description {self._comentario(descricao)}")

        if modo == MODO_TRUNK:
            trunks = ", ".join(str(v) for v in (porta.get("trunks") or []))
            linhas.append(" switchport mode trunk")
            linhas.append(f" switchport trunk allowed vlan {trunks}")
            # O VLAN nativo vai por ultimo de proposito: quando um trunk
            # aceita lista, o equipamento assume o primeiro como nativo, e
            # essa suposicao silenciosa e o tipo de coisa que derruba uma
            # rede num dia comum.
            nativo = porta.get("vlan")
            if nativo is not None:
                linhas.append(f" switchport trunk native vlan {nativo}")
        else:
            vlan = porta.get("vlan")
            rotulo = self._vlan(infra, vlan) if vlan is not None else "VLAN ?"
            linhas.append(" switchport mode access")
            linhas.append(f" switchport access vlan {vlan}")
            linhas.append(f" ! {rotulo}")

        linhas.append(" exit")
        return linhas

    def _bloco_stp(
        self,
        campos: dict[str, Any],
        infra: Infraestrutura,
    ) -> list[str]:
        """As linhas de spanning-tree.

        The spanning-tree lines.

        Args:
            campos: Os campos do equipamento.
            infra: A infraestrutura inteira.

        Returns:
            As linhas de STP.
        """
        stp = campos.get("stp")
        if not isinstance(stp, dict):
            return []

        bloco = self._secao("spanning-tree")
        modo = stp.get("modo")
        if modo:
            bloco.append(f" spanning-tree mode {modo}")

        prioridade = stp.get("prioridade_bridge")
        if prioridade is not None:
            bloco.append(f" spanning-tree vlan 1-4094 priority {prioridade}")

        for porta in stp.get("portfast") or []:
            bloco.append(f" spanning-tree portfast {porta}")

        for porta in stp.get("bpdu_guard") or []:
            bloco.append(f" spanning-tree bpduguard enable {porta}")

        return bloco