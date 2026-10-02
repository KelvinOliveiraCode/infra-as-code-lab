"""Gerador de configuracao de firewall.

Firewall configuration generator.

Traduz a declaracao de um firewall em sintaxe Cisco-like ficticia:
identidade, zonas, regras e NAT.

O switch e o gerador de referencia; este segue a mesma forma: validacoes
que o schema nao faz, ordem fixa das secoes, e uso de `juntar()`.
"""

from __future__ import annotations

from typing import Any

from ..modelo import Equipamento, Infraestrutura
from .base import GeradorBase, juntar


ACOES_VALIDAS = ("permitir", "negar")


class GeradorFirewall(GeradorBase):
    """Configuracao de firewall a partir da declaracao.

    Firewall configuration from the declaration.
    """

    tipo = "firewall"

    def validar(self, infra: Infraestrutura) -> list[str]:
        """Checa zonas, regras e NAT.

        Check zones, rules and NAT.

        Args:
            infra: A infraestrutura inteira.

        Returns:
            Uma mensagem por problema encontrado.
        """
        problemas: list[str] = []

        for equipamento in infra.por_tipo(self.tipo):
            identidade = equipamento.identidade
            campos = equipamento.campos

            # --- zonas ---
            zonas = campos.get("zonas") or []
            if not isinstance(zonas, list):
                problemas.append(f"{identidade}.zonas: esperado uma lista")
                continue

            nomes_zonas: set[str] = set()
            for indice, zona in enumerate(zonas):
                onde = f"{identidade}.zonas[{indice}]"
                if not isinstance(zona, dict):
                    problemas.append(f"{onde}: esperado um mapa")
                    continue

                nome = str(zona.get("nome", "")).strip()
                if not nome:
                    problemas.append(f"{onde}.nome: obrigatorio")
                elif nome in nomes_zonas:
                    problemas.append(f"{onde}.nome: {nome} repetida")
                else:
                    nomes_zonas.add(nome)

                interfaces = zona.get("interfaces")
                if not isinstance(interfaces, list) or not interfaces:
                    problemas.append(f"{onde}.interfaces: lista obrigatoria e nao vazia")

            # --- regras ---
            regras = campos.get("regras") or []
            if not isinstance(regras, list):
                problemas.append(f"{identidade}.regras: esperado uma lista")
            else:
                for indice, regra in enumerate(regras):
                    onde = f"{identidade}.regras[{indice}]"
                    if not isinstance(regra, dict):
                        problemas.append(f"{onde}: esperado um mapa")
                        continue

                    origem = str(regra.get("origem", "")).strip()
                    destino = str(regra.get("destino", "")).strip()
                    acao = str(regra.get("acao", "")).strip()

                    if not origem:
                        problemas.append(f"{onde}.origem: obrigatorio")
                    elif origem not in nomes_zonas:
                        problemas.append(
                            f"{onde}.origem: {origem!r} nao e uma zona declarada neste firewall"
                        )

                    if not destino:
                        problemas.append(f"{onde}.destino: obrigatorio")
                    elif destino not in nomes_zonas:
                        problemas.append(
                            f"{onde}.destino: {destino!r} nao e uma zona declarada neste firewall"
                        )

                    if not acao:
                        problemas.append(f"{onde}.acao: obrigatorio")
                    elif acao not in ACOES_VALIDAS:
                        problemas.append(
                            f"{onde}.acao: {acao!r} invalida; aceitas: {', '.join(ACOES_VALIDAS)}"
                        )

            # --- nat ---
            nat_list = campos.get("nat") or []
            if not isinstance(nat_list, list):
                problemas.append(f"{identidade}.nat: esperado uma lista")
            else:
                for indice, nat in enumerate(nat_list):
                    onde = f"{identidade}.nat[{indice}]"
                    if not isinstance(nat, dict):
                        problemas.append(f"{onde}: esperado um mapa")
                        continue
                    nome_nat = str(nat.get("nome", "")).strip()
                    if not nome_nat:
                        problemas.append(f"{onde}.nome: obrigatorio")

        return problemas

    def linhas(self, equipamento: Equipamento, infra: Infraestrutura) -> list[str]:
        """As linhas de configuracao do firewall.

        The firewall configuration lines.

        A ordem e: identidade, zonas, regras, nat.

        Args:
            equipamento: O firewall a traduzir.
            infra: A infraestrutura inteira.

        Returns:
            As linhas, sem cabecalho.
        """
        campos = equipamento.campos

        blocos: list[list[str]] = [self._bloco_identidade(equipamento)]
        blocos.append(self._bloco_zonas(campos, infra))
        blocos.append(self._bloco_regras(campos))
        blocos.append(self._bloco_nat(campos))
        return juntar(blocos)

    # ---------------------------------------------------------------- blocos

    def _bloco_identidade(self, equipamento: Equipamento) -> list[str]:
        """Hostname e modelo.

        Hostname and model.

        Args:
            equipamento: O firewall.

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

    def _bloco_zonas(self, campos: dict[str, Any], infra: Infraestrutura) -> list[str]:
        """As zonas do firewall.

        The firewall zones.

        Args:
            campos: Os campos do equipamento.
            infra: A infraestrutura inteira.

        Returns:
            As linhas de zona.
        """
        bloco = self._secao("zonas")
        for zona in campos.get("zonas") or []:
            if not isinstance(zona, dict):
                continue
            nome = str(zona.get("nome", ""))
            if not nome:
                continue
            bloco.append(f"firewall-zone name {nome}")
            for iface in zona.get("interfaces") or []:
                bloco.append(f" interface {iface}")
            vlan = zona.get("vlan")
            if vlan is not None:
                rotulo = self._vlan(infra, vlan)
                bloco.append(f" ! {rotulo}")
            bloco.append(" exit")
        return bloco

    def _bloco_regras(self, campos: dict[str, Any]) -> list[str]:
        """As regras de firewall.

        The firewall rules.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de regra.
        """
        bloco = self._secao("regras")
        for regra in campos.get("regras") or []:
            if not isinstance(regra, dict):
                continue
            origem = str(regra.get("origem", ""))
            destino = str(regra.get("destino", ""))
            acao = str(regra.get("acao", ""))
            porta = regra.get("porta", 0)
            descricao = regra.get("descricao")
            if not (origem and destino and acao):
                continue
            bloco.append(
                f"firewall-rule from {origem} to {destino} action {acao} port {porta}"
            )
            if descricao:
                bloco.append(f" description {self._comentario(descricao)}")
        return bloco

    def _bloco_nat(self, campos: dict[str, Any]) -> list[str]:
        """A secao de NAT.

        The NAT section.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de NAT.
        """
        bloco = self._secao("nat")
        for nat in campos.get("nat") or []:
            if not isinstance(nat, dict):
                continue
            nome = str(nat.get("nome", ""))
            if not nome:
                continue
            bloco.append(f"nat rule {nome}")
            tipo = nat.get("tipo")
            if tipo:
                bloco.append(f" type {tipo}")
            zona_origem = nat.get("zona_origem")
            if zona_origem:
                bloco.append(f" source-zone {zona_origem}")
            iface_destino = nat.get("interface_destino")
            if iface_destino:
                bloco.append(f" destination-interface {iface_destino}")
            descricao = nat.get("descricao")
            if descricao:
                bloco.append(f" description {self._comentario(descricao)}")
            bloco.append(" exit")
        return bloco