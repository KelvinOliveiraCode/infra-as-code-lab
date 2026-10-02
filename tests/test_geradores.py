"""Testes dos quatro geradores.

Tests for the four generators.

Estes testes existem para o gerador produzir a **mesma coisa** nas duas
direcoes: um YAML valido vira configuracao com o conteudo certo, e um campo
malposto vira erro de schema em vez de arquivo gerado silenciosamente errado.

O padrao de cada teste e o mesmo: gera a partir de uma infraestrutura minima
construida na mao, e compara linhas exatas. Nenhum teste le o YAML do projeto,
porque um gerador que so funciona com o arquivo real nao tem schema - tem
exemplo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from iaclab.geradores import (
    GeradorBase,
    GeradorNaoConhecido,
    juntar,
    por_tipo,
    todos,
)
from iaclab.geradores.ap import GeradorAP
from iaclab.geradores.firewall import GeradorFirewall
from iaclab.geradores.servidor import GeradorServidor
from iaclab.geradores.switch import GeradorSwitch
from iaclab.modelo import Equipamento, ErroDeSchema, Infraestrutura, Vlan

VLANS = (
    Vlan(id=10, nome="CORP", faixa="10.0.10.0/24"),
    Vlan(id=20, nome="SRV", faixa="10.0.20.0/24"),
)


def equipamento(tipo: str, **campos: Any) -> Equipamento:
    """Um equipamento de teste.

    A test device.

    Args:
        tipo: O tipo.
        **campos: Os campos especificos do tipo.

    Returns:
        O equipamento, com `hostname` ja garantido.
    """
    dados = {"hostname": "EQ-TESTE", **campos}
    return Equipamento(tipo=tipo, campos=dados, bruto={"tipo": tipo, **dados})


class TestRegistro:
    """O registro de geradores."""

    def test_todos_os_tipos_tem_gerador(self) -> None:
        # Um tipo aceito pelo schema e sem gerador escrito e falha de
        # desenvolvimento: o plano so descobre isso na hora de rodar.
        registro = todos()
        for tipo in ("switch", "firewall", "ap", "servidor"):
            assert tipo in registro, f"{tipo} nao tem gerador"

    def test_tipo_sem_gerador_nao_quebra_na_construcao(self) -> None:
        gerador = por_tipo("roteador")
        assert isinstance(gerador, GeradorNaoConhecido)

    def test_gerador_sem_gerador_fala_na_hora_de_gerar(self) -> None:
        gerador = por_tipo("roteador")
        with pytest.raises(ErroDeSchema):
            gerador.gerar(equipamento("roteador"), Infraestrutura(vlans=VLANS))


class TestBase:
    """A classe base."""

    def test_base_exige_linhas(self) -> None:
        class Vazio(GeradorBase):
            tipo = "vazio"

        with pytest.raises(NotImplementedError):
            Vazio().linhas(equipamento("vazio"), Infraestrutura())

    def test_cabecalho_carrega_a_origem_e_avisa_que_e_ficticio(self) -> None:
        eq = Equipamento(
            tipo="switch",
            campos={"hostname": "SW-1"},
            bruto={},
            origem="infra/rede.yaml",
        )
        texto = por_tipo("switch").gerar(eq, Infraestrutura(vlans=VLANS))
        assert "infra/rede.yaml" in texto
        assert "FICTICIO" in texto
        assert "schema" in texto

    def test_cabecalho_nao_tem_data(self) -> None:
        # Uma data no cabecalho faria toda geracao diferir da anterior, e o
        # criterio de aceite - duas execucoes identicas - viraria impossivel.
        eq = equipamento("switch")
        texto = por_tipo("switch").gerar(eq, Infraestrutura(vlans=VLANS))
        assert "20" not in texto.splitlines()[0]

    def test_comentario_normaliza_quebra_de_linha(self) -> None:
        # Uma quebra num valor do YAML viraria um comentario de duas linhas
        # no arquivo gerado, e a segunda viraria comando.
        bloco = {"descricao": "linha um\nlinha dois"}
        eq = Equipamento(tipo="switch", campos={"hostname": "S", "portas": [bloco]}, bruto={})
        texto = por_tipo("switch").gerar(eq, Infraestrutura(vlans=VLANS))
        assert "linha um linha dois" in texto
        assert "linha dois" not in texto.split("linha um linha dois")[1].splitlines()[0]

    def test_juntar_tira_vazios_do_meio(self) -> None:
        assert juntar([["a", ""], ["", "b"]]) == ["a", "b"]

    def test_juntar_lista_vazia(self) -> None:
        assert juntar([]) == []


class TestSwitch:
    """O gerador de switch."""

    def _eq(self, **extra: Any) -> Equipamento:
        return equipamento(
            "switch",
            modelo="CAT-FICT",
            portas=[
                {
                    "nome": "Gi0/1",
                    "modo": "access",
                    "vlan": 10,
                    "descricao": "estacao",
                }
            ],
            **extra,
        )

    def test_access_port(self) -> None:
        eq = self._eq()
        linhas = por_tipo("switch").linhas(eq, Infraestrutura(vlans=VLANS))
        texto = "\n".join(linhas)
        assert "interface Gi0/1" in texto
        assert "switchport mode access" in texto
        assert "switchport access vlan 10" in texto
        # A VLAN e citada pelo nome no comentario, para quem le nao ter que
        # abrir o YAML para saber o que e a 10.
        assert "VLAN 10 CORP" in texto

    def test_trunk_declara_o_nativo(self) -> None:
        eq = equipamento(
            "switch",
            portas=[{"nome": "Gi0/3", "modo": "trunk", "vlan": 30, "trunks": ["10", "20"]}],
        )
        texto = "\n".join(por_tipo("switch").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "switchport trunk allowed vlan 10, 20" in texto
        assert "switchport trunk native vlan 30" in texto

    def test_stp(self) -> None:
        eq = self._eq(
            stp={
                "modo": "rapid-pvst",
                "prioridade_bridge": 32768,
                "portfast": ["Gi0/1"],
                "bpdu_guard": ["Gi0/1"],
            }
        )
        texto = "\n".join(por_tipo("switch").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "spanning-tree mode rapid-pvst" in texto
        assert "spanning-tree portfast Gi0/1" in texto
        assert "spanning-tree bpduguard enable Gi0/1" in texto

    def test_modo_invalido(self) -> None:
        eq = equipamento("switch", portas=[{"nome": "Gi0/1", "modo": "bridge"}])
        problemas = por_tipo("switch").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("modo" in p for p in problemas)

    def test_porta_repetida(self) -> None:
        eq = equipamento(
            "switch",
            portas=[
                {"nome": "Gi0/1", "modo": "access", "vlan": 10},
                {"nome": "Gi0/1", "modo": "access", "vlan": 10},
            ],
        )
        problemas = por_tipo("switch").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("repetida" in p for p in problemas)

    def test_trunk_sem_lista_de_vlans(self) -> None:
        eq = equipamento("switch", portas=[{"nome": "Gi0/1", "modo": "trunk"}])
        problemas = por_tipo("switch").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("trunks" in p for p in problemas)

    def test_portfast_em_porta_inexistente(self) -> None:
        eq = self._eq(stp={"portfast": ["Gi0/99"]})
        problemas = por_tipo("switch").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("Gi0/99" in p for p in problemas)

    def test_equipamento_valido_nao_acusa(self) -> None:
        eq = self._eq()
        assert por_tipo("switch").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,))) == []


class TestFirewall:
    """O gerador de firewall."""

    def _eq(self, **extra: Any) -> Equipamento:
        return equipamento(
            "firewall",
            modelo="PF-FICT",
            zonas=[{"nome": "TRUST", "interfaces": ["Gi0/1"], "vlan": 10}],
            **extra,
        )

    def test_zona(self) -> None:
        eq = self._eq()
        texto = "\n".join(por_tipo("firewall").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "firewall-zone name TRUST" in texto
        assert " interface Gi0/1" in texto

    def test_regra(self) -> None:
        eq = self._eq(
            regras=[{"nome": "r1", "origem": "TRUST", "destino": "UNTRUST", "acao": "negar", "porta": 0}]
        )
        infra = Infraestrutura(
            vlans=VLANS,
            equipamentos=(
                eq,
            ),
        )
        texto = "\n".join(por_tipo("firewall").linhas(eq, infra))
        assert "firewall-rule" in texto
        assert "negar" in texto

    def test_regra_com_zona_inexistente(self) -> None:
        eq = self._eq(
            regras=[{"nome": "r", "origem": "FANTASMA", "destino": "TRUST", "acao": "negar", "porta": 0}]
        )
        problemas = por_tipo("firewall").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("FANTASMA" in p for p in problemas)

    def test_zona_sem_interface(self) -> None:
        eq = equipamento("firewall", zonas=[{"nome": "VAZIA", "interfaces": []}])
        problemas = por_tipo("firewall").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("interfaces" in p for p in problemas)

    def test_nat(self) -> None:
        eq = self._eq(
            nat=[{"nome": "SAIDA", "tipo": "dinamica", "zona_origem": "TRUST", "interface_destino": "Gi0/9"}]
        )
        texto = "\n".join(por_tipo("firewall").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "nat rule SAIDA" in texto


class TestAP:
    """O gerador de ponto de acesso."""

    def test_ssid_wpa2_tem_chave_ficticia_e_aviso(self) -> None:
        eq = equipamento(
            "ap",
            ssid=[{"nome": "LAB", "vlan": 10, "seguranca": "wpa2"}],
            canal=6,
        )
        texto = "\n".join(por_tipo("ap").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "interface LAB" in texto
        assert "wpa-psk" in texto
        assert "cofre" in texto

    def test_ssid_aberta_nao_tem_chave(self) -> None:
        eq = equipamento("ap", ssid=[{"nome": "VISIT", "vlan": 20, "seguranca": "aberta"}])
        texto = "\n".join(por_tipo("ap").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "wpa-psk" not in texto
        assert "security aberta" in texto

    def test_oculta_avisa_que_nao_e_seguranca(self) -> None:
        eq = equipamento(
            "ap", ssid=[{"nome": "H", "vlan": 10, "seguranca": "aberta", "oculta": True}]
        )
        texto = "\n".join(por_tipo("ap").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "hidden" in texto
        assert "beacon" in texto

    def test_canal_fora_da_faixa(self) -> None:
        eq = equipamento("ap", canal=99)
        problemas = por_tipo("ap").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("canal" in p for p in problemas)

    def test_sinal_fora_da_faixa(self) -> None:
        eq = equipamento("ap", sinal=500)
        problemas = por_tipo("ap").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("sinal" in p for p in problemas)

    def test_seguranca_desconhecida(self) -> None:
        eq = equipamento("ap", ssid=[{"nome": "X", "vlan": 10, "seguranca": "wpa1"}])
        problemas = por_tipo("ap").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("seguranca" in p for p in problemas)

    def test_ssid_repetido(self) -> None:
        eq = equipamento(
            "ap",
            ssid=[
                {"nome": "X", "vlan": 10, "seguranca": "aberta"},
                {"nome": "X", "vlan": 10, "seguranca": "aberta"},
            ],
        )
        problemas = por_tipo("ap").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("repetido" in p for p in problemas)

    def test_vlan_inexistente(self) -> None:
        eq = equipamento("ap", ssid=[{"nome": "X", "vlan": 99, "seguranca": "aberta"}])
        problemas = por_tipo("ap").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("99" in p for p in problemas)


class TestServidor:
    """O gerador de servidor."""

    def _eq(self, **extra: Any) -> Equipamento:
        return equipamento(
            "servidor",
            sistema="linux-ficticio",
            grupos=[{"nome": "devs"}],
            usuarios=[{"nome": "ana", "grupos": ["devs"], "shell": "/bin/sh"}],
            **extra,
        )

    def test_usuario_tem_grupo_e_nenhuma_senha(self) -> None:
        eq = self._eq()
        texto = "\n".join(por_tipo("servidor").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "usuario ana" in texto
        assert "grupos devs" in texto
        # A palavra senha nao pode aparecer em nenhuma forma: este projeto
        # nao guarda segredo e o arquivo gerado tambem nao pode.
        for proibida in ("senha", "password", "passwd", "secret"):
            assert proibida not in texto.lower(), f"o arquivo gerado tem {proibida}"

    def test_permissao(self) -> None:
        eq = self._eq(
            permissoes=[{"caminho": "/srv", "grupo": "devs", "modo": "0750", "tipo": "diretorio"}]
        )
        texto = "\n".join(por_tipo("servidor").linhas(eq, Infraestrutura(vlans=VLANS)))
        assert "permisao /srv" in texto
        assert "modo 0750" in texto

    def test_grupo_inexistente(self) -> None:
        eq = equipamento(
            "servidor", grupos=[{"nome": "devs"}], usuarios=[{"nome": "x", "grupos": ["fantasma"]}]
        )
        problemas = por_tipo("servidor").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("fantasma" in p for p in problemas)

    def test_modo_invalido(self) -> None:
        eq = self._eq(permissoes=[{"caminho": "/srv", "grupo": "devs", "modo": "rwx"}])
        problemas = por_tipo("servidor").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("modo" in p for p in problemas)

    def test_usuario_repetido(self) -> None:
        eq = equipamento(
            "servidor",
            grupos=[{"nome": "devs"}],
            usuarios=[
                {"nome": "ana", "grupos": ["devs"]},
                {"nome": "ana", "grupos": ["devs"]},
            ],
        )
        problemas = por_tipo("servidor").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("repetido" in p for p in problemas)

    def test_caminho_repetido(self) -> None:
        eq = self._eq(
            permissoes=[
                {"caminho": "/srv", "grupo": "devs", "modo": "0750"},
                {"caminho": "/srv", "grupo": "devs", "modo": "0700"},
            ]
        )
        problemas = por_tipo("servidor").validar(Infraestrutura(vlans=VLANS, equipamentos=(eq,)))
        assert any("repetido" in p for p in problemas)


class TestSemSegredoEmLugarNenhum:
    """A garantia de que o pacote inteiro nao guarda segredo."""

    def test_geradores_nao_tem_senha_nem_chave_de_verdade(self) -> None:
        # Um valor literal de senha em qualquer gerador acabaria no git. O
        # que pode existir e um marcador obviamente ficticio.
        from iaclab.geradores import ap, firewall, servidor, switch

        for modulo in (ap, firewall, servidor, switch):
            texto = Path(modulo.__file__).read_text(encoding="utf-8")
            for segredo in ("password=", "senha=", "PSK ", "pre-shared-key real"):
                assert segredo not in texto, f"{modulo.__name__} contem {segredo!r}"