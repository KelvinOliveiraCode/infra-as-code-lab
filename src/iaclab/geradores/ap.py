"""Gerador de configuracao de ponto de acesso.

Access point configuration generator.

Traduz a declaracao de um AP em sintaxe Cisco-like ficticia: identidade,
canal, sinal e SSIDs com VLAN e seguranca.
"""

from __future__ import annotations

from typing import Any

from ..modelo import Equipamento, Infraestrutura
from .base import GeradorBase, juntar


class GeradorAP(GeradorBase):
    """Configuracao de ponto de acesso a partir da declaracao.

    Access point configuration from the declaration.
    """

    tipo = "ap"

    # Segurancas aceitas para SSID.
    SEGURANCA_WPA2 = "wpa2"
    SEGURANCA_WPA3 = "wpa3"
    SEGURANCA_ABERTA = "aberta"
    SEGURANCAS = (SEGURANCA_WPA2, SEGURANCA_WPA3, SEGURANCA_ABERTA)

    def validar(self, infra: Infraestrutura) -> list[str]:
        """Checa SSIDs, canal, sinal e VLANs referenciadas.

        Check SSIDs, channel, signal and referenced VLANs.

        Args:
            infra: A infraestrutura inteira.

        Returns:
            Uma mensagem por problema encontrado.
        """
        problemas: list[str] = []

        for equipamento in infra.por_tipo(self.tipo):
            identidade = equipamento.identidade
            campos = equipamento.campos

            # Valida canal do AP.
            canal = campos.get("canal")
            if canal is not None:
                try:
                    canal_int = int(canal)
                    if not 1 <= canal_int <= 11:
                        problemas.append(
                            f"{identidade}.canal: {canal_int} fora de 1..11"
                        )
                except (TypeError, ValueError):
                    problemas.append(
                        f"{identidade}.canal: {canal!r} nao e inteiro"
                    )

            # Valida sinal do AP.
            sinal = campos.get("sinal")
            if sinal is not None:
                try:
                    sinal_int = int(sinal)
                    if not 0 <= sinal_int <= 100:
                        problemas.append(
                            f"{identidade}.sinal: {sinal_int} fora de 0..100"
                        )
                except (TypeError, ValueError):
                    problemas.append(
                        f"{identidade}.sinal: {sinal!r} nao e inteiro"
                    )

            # Valida cada SSID.
            ssids = campos.get("ssid") or []
            if not isinstance(ssids, list):
                problemas.append(f"{identidade}.ssid: esperado uma lista")
                continue

            nomes: set[str] = set()
            for indice, ssid in enumerate(ssids):
                onde = f"{identidade}.ssid[{indice}]"
                if not isinstance(ssid, dict):
                    problemas.append(f"{onde}: esperado um mapa")
                    continue

                nome = str(ssid.get("nome", "")).strip()
                if not nome:
                    problemas.append(f"{onde}.nome: obrigatorio")
                elif nome in nomes:
                    # Dois SSIDs com o mesmo nome no mesmo AP nao coexistem:
                    # o segundo sobrescreve o primeiro e o YAML parece ter
                    # dois quando o equipamento so tem um.
                    problemas.append(f"{onde}.nome: {nome} repetido no equipamento")
                else:
                    nomes.add(nome)

                vlan = ssid.get("vlan")
                if vlan is None:
                    problemas.append(f"{onde}.vlan: obrigatorio")
                elif infra.vlan(vlan) is None:
                    problemas.append(
                        f"{onde}.vlan: {vlan!r} nao declarada"
                    )

                seguranca = str(ssid.get("seguranca", "")).strip().lower()
                if not seguranca:
                    problemas.append(f"{onde}.seguranca: obrigatorio")
                elif seguranca not in self.SEGURANCAS:
                    problemas.append(
                        f"{onde}.seguranca: {seguranca!r} desconhecida; "
                        f"aceitas: {', '.join(self.SEGURANCAS)}"
                    )

                # Um SSID sem nome nao pode ser escondido: o nome e o
                # unico jeito de Quem conecta saber qual rede e. Declarar
                # `oculta: true` em um SSID sem nome seria um SSID que
                # ninguem consegue usar.
                oculta = ssid.get("oculta")
                if not isinstance(oculta, bool):
                    problemas.append(f"{onde}.oculta: esperado true ou false")

                nomes.add(str(ssid.get("nome", "")))

                # Valida canal do SSID, se presente.
                canal_ssid = ssid.get("canal")
                if canal_ssid is not None:
                    try:
                        canal_ssid_int = int(canal_ssid)
                        if not 1 <= canal_ssid_int <= 11:
                            problemas.append(
                                f"{onde}.canal: {canal_ssid_int} fora de 1..11"
                            )
                    except (TypeError, ValueError):
                        problemas.append(
                            f"{onde}.canal: {canal_ssid!r} nao e inteiro"
                        )

        return problemas

    def linhas(self, equipamento: Equipamento, infra: Infraestrutura) -> list[str]:
        """As linhas de configuracao do ponto de acesso.

        The access point configuration lines.

        A ordem e: identidade, canal/sinal, SSIDs. E a ordem em que quem le o
        arquivo espera encontrar cada coisa.

        Args:
            equipamento: O AP a traduzir.
            infra: A infraestrutura inteira.

        Returns:
            As linhas, sem cabecalho.
        """
        campos = equipamento.campos

        blocos: list[list[str]] = [self._bloco_identidade(equipamento)]
        blocos.append(self._bloco_canal_sinal(campos))
        blocos.append(self._bloco_ssids(campos, infra))
        return juntar(blocos)

    # ---------------------------------------------------------------- blocos

    def _bloco_identidade(self, equipamento: Equipamento) -> list[str]:
        """Hostname e modelo.

        Hostname and model.

        Args:
            equipamento: O AP.

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
        descricao = campos.get("descricao")
        if descricao:
            linhas.append(f" ! {self._comentario(descricao)}")
        return linhas

    def _bloco_canal_sinal(self, campos: dict[str, Any]) -> list[str]:
        """Canal e sinal do AP.

        The AP channel and signal.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de canal e sinal.
        """
        bloco = self._secao("canal / sinal")
        canal = campos.get("canal")
        if canal is not None:
            bloco.append(f" canal {canal}")
        sinal = campos.get("sinal")
        if sinal is not None:
            bloco.append(f" sinal {sinal}")
        return bloco

    def _bloco_ssids(
        self,
        campos: dict[str, Any],
        infra: Infraestrutura,
    ) -> list[str]:
        """Um bloco por SSID.

        One block per SSID.

        Args:
            campos: Os campos do equipamento.
            infra: A infraestrutura inteira.

        Returns:
            As linhas de SSID.
        """
        bloco = self._secao("ssid")
        for ssid in campos.get("ssid") or []:
            if not isinstance(ssid, dict):
                continue
            bloco.extend(self._linhas_ssid(ssid, infra))
        return bloco

    def _linhas_ssid(
        self,
        ssid: dict[str, Any],
        infra: Infraestrutura,
    ) -> list[str]:
        """As linhas de um SSID.

        The lines of one SSID.

        Args:
            ssid: A declaracao do SSID.
            infra: A infraestrutura inteira.

        Returns:
            As linhas do SSID, com `exit` no fim.
        """
        nome = str(ssid.get("nome", ""))
        linhas = [f"interface {nome}"]

        vlan_id = ssid.get("vlan")
        if vlan_id is not None:
            rotulo = self._vlan(infra, vlan_id)
            linhas.append(f" vlan {vlan_id}")
            linhas.append(f" ! {rotulo}")

        # Esconder o SSID nao e seguranca: o beacon continua anunciando a rede
        # para quem procura. Por isso a linha vai com o aviso, para ninguem
        # ler 'oculta' no YAML e concluir que a rede sumiu do ar.
        if ssid.get("oculta"):
            linhas.append(" hidden")
            linhas.append(" ! oculta nao e seguranca: o beacon continua anunciando")

        seguranca = str(ssid.get("seguranca", "")).strip().lower()
        linhas.append(f" security {seguranca}")

        if seguranca == self.SEGURANCA_WPA2:
            linhas.append(" wpa-psk FICTICIO-KEY-0000")
            linhas.append(
                " ! a chave real vem do cofre e nunca do YAML"
            )

        linhas.append(" exit")
        return linhas
