"""Testes do schema e do carregador.

Schema and loader tests.

O schema e o contrato do projeto: se ele deixa passar algo invalido, o
gerador gera configuracao quebrada; se ele recusa algo valido, o projeto para
de servir. Os testes aqui cobrem as duas direcoes, e em especial o detalhe que
mais importa: **um erro de inventario precisa ser recusado na carga**, e nao
descoberto no meio de um arquivo de saida com tres equipamentos ja escritos.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from iaclab.cargador import carregar, carregar_arquivo
from iaclab.modelo import (
    TIPOS_CONHECIDOS,
    Equipamento,
    ErroDeSchema,
    Infraestrutura,
    Vlan,
    de_documento,
    referencias_quebradas,
    unir,
    validar_acessos,
    validar_equipamentos,
    validar_vlans,
)

RAIZ = Path(__file__).resolve().parent.parent


class TestValidasVlan:
    """A validacao das VLANs."""

    def test_lista_valida(self) -> None:
        vlans = validar_vlans([{"id": 10, "nome": "CORP", "faixa": "10.0.10.0/24"}], [])
        assert len(vlans) == 1
        assert vlans[0].id == 10

    def test_ausente_devolve_vazio(self) -> None:
        assert validar_vlans(None, []) == ()

    def test_lista_que_nao_e_lista(self) -> None:
        with pytest.raises(ErroDeSchema):
            validar_vlans("nao-e-lista", [])

    def test_id_fora_da_faixa(self) -> None:
        problemas: list[str] = []
        validar_vlans([{"id": 9999, "nome": "X", "faixa": "10.0.0.0/24"}], problemas)
        assert any("fora de 1..4094" in p for p in problemas)

    def test_id_que_nao_e_inteiro(self) -> None:
        problemas: list[str] = []
        validar_vlans([{"id": "dez", "nome": "X", "faixa": "10.0.0.0/24"}], problemas)
        assert any("nao e inteiro" in p for p in problemas)

    def test_vlan_repetida(self) -> None:
        problemas: list[str] = []
        validar_vlans(
            [
                {"id": 10, "nome": "A", "faixa": "10.0.10.0/24"},
                {"id": 10, "nome": "B", "faixa": "10.0.20.0/24"},
            ],
            problemas,
        )
        assert any("duas vezes" in p for p in problemas)

    def test_gateway_nao_pode_ser_faixa(self) -> None:
        problemas: list[str] = []
        validar_vlans(
            [{"id": 10, "nome": "A", "faixa": "10.0.10.0/24", "gateway": "10.0.10.0/24"}],
            problemas,
        )
        assert any("e um endereco" in p for p in problemas)


class TestValidaEquipamentos:
    """A validacao dos equipamentos."""

    def _base(self, **extra) -> dict:
        return {"tipo": "switch", "hostname": "SW-1", **extra}

    def test_equipamento_valido(self) -> None:
        eqs = validar_equipamentos([self._base()], [])
        assert len(eqs) == 1
        assert eqs[0].tipo == "switch"
        assert eqs[0].hostname == "SW-1"

    def test_tipo_desconhecido(self) -> None:
        problemas: list[str] = []
        validar_equipamentos([{"tipo": "roteador", "hostname": "R1"}], problemas)
        assert any("desconhecido" in p for p in problemas)

    def test_todos_os_tipos_conhecidos_passam(self) -> None:
        for tipo in TIPOS_CONHECIDOS:
            problemas: list[str] = []
            validar_equipamentos([{"tipo": tipo, "hostname": "X"}], problemas)
            assert not problemas, f"{tipo} foi recusado: {problemas}"

    def test_campo_desconhecido(self) -> None:
        # Um campo nao previsto e quase sempre erro de digitacao, e erro de
        # digitacao ignorado vira equipamento sem configuracao no dia da
        # mudanca.
        problemas: list[str] = []
        validar_equipamentos([self._base(vlna=10)], problemas)
        assert any("campo desconhecido" in p for p in problemas)

    def test_hostname_vazio(self) -> None:
        problemas: list[str] = []
        validar_equipamentos([{"tipo": "switch", "hostname": "  "}], problemas)
        assert any("obrigatorio" in p for p in problemas)

    def test_identidade_repetida(self) -> None:
        problemas: list[str] = []
        validar_equipamentos([self._base(), self._base()], problemas)
        assert any("duas vezes" in p for p in problemas)

    def test_mesmo_hostname_diferentes_tipos(self) -> None:
        # Dois tipos com o mesmo hostname sao plausiveis em inventario
        # mantido a mao, entao nao colidem.
        problemas: list[str] = []
        eqs = validar_equipamentos(
            [{"tipo": "switch", "hostname": "N1"},
             {"tipo": "ap", "hostname": "N1"}],
            problemas,
        )
        assert not problemas
        assert eqs[0].identidade != eqs[1].identidade


class TestValidaAcessos:
    """A validacao dos acessos."""

    def test_acesso_valido(self) -> None:
        acessos = validar_acessos(
            [{"servidor": "SRV", "grupo": "g", "permissao": "leitura"}], []
        )
        assert len(acessos) == 1

    def test_campo_obrigatorio_faltando(self) -> None:
        problemas: list[str] = []
        validar_acessos([{"servidor": "SRV", "grupo": "g"}], problemas)
        assert any("permissao: obrigatorio" in p for p in problemas)


class TestInfraestrutura:
    """As consultas sobre uma infraestrutura."""

    def _infra(self) -> Infraestrutura:
        return de_documento(
            {
                "vlans": [
                    {"id": 10, "nome": "CORP", "faixa": "10.0.10.0/24"},
                    {"id": 20, "nome": "SRV", "faixa": "10.0.20.0/24"},
                ],
                "equipamentos": [
                    {"tipo": "switch", "hostname": "SW-1", "vlan": 10},
                    {"tipo": "ap", "hostname": "AP-1", "vlan": "CORP"},
                ],
            }
        )

    def test_por_tipo(self) -> None:
        infra = self._infra()
        assert len(infra.por_tipo("switch")) == 1
        assert len(infra.por_tipo("ap")) == 1
        assert infra.por_tipo("servidor") == ()

    def test_vlan_por_id_nome_e_faixa(self) -> None:
        infra = self._infra()
        assert infra.vlan(10) is not None
        assert infra.vlan("CORP") is not None
        assert infra.vlan("10.0.10.0/24") is not None
        assert infra.vlan(99) is None

    def test_referencia_quebrada(self) -> None:
        infra = de_documento(
            {
                "vlans": [{"id": 10, "nome": "A", "faixa": "10.0.10.0/24"}],
                "equipamentos": [{"tipo": "switch", "hostname": "SW-1", "vlan": 99}],
            }
        )
        problemas = referencias_quebradas(infra)
        assert len(problemas) == 1
        assert "99" in problemas[0]

    def test_referencia_valida_nao_acusa(self) -> None:
        assert referencias_quebradas(self._infra()) == []


class TestUnir:
    """A juncao de dois arquivos."""

    def test_junta_sem_conflito(self) -> None:
        a = de_documento({"equipamentos": [{"tipo": "switch", "hostname": "SW-1"}]})
        b = de_documento({"equipamentos": [{"tipo": "ap", "hostname": "AP-1"}]})
        junta = unir(a, b)
        assert len(junta.equipamentos) == 2

    def test_conflito_de_equipamento(self) -> None:
        a = de_documento({"equipamentos": [{"tipo": "switch", "hostname": "SW-1"}]})
        b = de_documento({"equipamentos": [{"tipo": "switch", "hostname": "SW-1"}]})
        with pytest.raises(ErroDeSchema):
            unir(a, b)

    def test_conflito_de_vlan(self) -> None:
        a = de_documento({"vlans": [{"id": 10, "nome": "A", "faixa": "10.0.10.0/24"}]})
        b = de_documento({"vlans": [{"id": 10, "nome": "B", "faixa": "10.0.20.0/24"}]})
        with pytest.raises(ErroDeSchema):
            unir(a, b)


class TestCargador:
    """A leitura dos arquivos de disco."""

    def test_le_os_tres_yaml_do_projeto(self) -> None:
        infra = carregar(
            [
                RAIZ / "infra" / "rede.yaml",
                RAIZ / "infra" / "servidores.yaml",
                RAIZ / "infra" / "acessos.yaml",
            ]
        )
        assert len(infra.equipamentos) == 7
        assert len(infra.vlans) == 4
        assert infra.acessos

    def test_alias_servidores(self) -> None:
        # infra/servidores.yaml tem a chave `servidores:`, nao `equipamentos:`.
        infra = carregar_arquivo(RAIZ / "infra" / "servidores.yaml")
        assert len(infra.equipamentos) == 2
        assert all(e.tipo == "servidor" for e in infra.equipamentos)

    def test_arquivo_inexistente(self) -> None:
        with pytest.raises(ErroDeSchema):
            carregar_arquivo(RAIZ / "infra" / "nao-existe.yaml")

    def test_chave_de_topo_desconhecida(self, tmp_path: Path) -> None:
        # `equipamntos` com o 'a' trocado: erro de digitacao que o gerador
        # ignoraria em silencio, e o inventario inteiro sumiria do plano.
        arquivo = tmp_path / "chave-ruim.yaml"
        arquivo.write_text("equipamntos: []\n", encoding="utf-8")
        with pytest.raises(ErroDeSchema):
            carregar_arquivo(arquivo)

    def test_yaml_invalido(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "ruim.yaml"
        arquivo.write_text("a: [1, 2\nb: :\n", encoding="utf-8")
        with pytest.raises(ErroDeSchema):
            carregar_arquivo(arquivo)

    def test_topo_nao_e_mapa(self, tmp_path: Path) -> None:
        arquivo = tmp_path / "lista.yaml"
        arquivo.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ErroDeSchema):
            carregar_arquivo(arquivo)

    def test_lista_vazia(self) -> None:
        infra = carregar([])
        assert infra.equipamentos == ()

    def test_campos_do_projeto_batem_com_o_schema(self, tmp_path: Path) -> None:
        """Todo campo usado nos YAMLs do projeto e aceito pelo schema.

        Todo campo usado in the project YAMLs is accepted by the schema.

        Este teste e o que impede a divergencia silenciosa entre o schema e
        os dados: se alguem acrescenta `modelo:` a um AP e esquece de
        acrescentar ao schema, aqui quebra.
        """
        from iaclab.modelo import CAMPOS_POR_TIPO

        for nome in ("rede.yaml", "servidores.yaml", "acessos.yaml"):
            documento = yaml.safe_load(
                (RAIZ / "infra" / nome).read_text(encoding="utf-8")
            )
            for item in documento.get("equipamentos", documento.get("servidores", [])):
                tipo = item.get("tipo")
                aceitos = set(CAMPOS_POR_TIPO[tipo])
                nao_aceitos = set(item) - aceitos - {"tipo"}
                assert not nao_aceitos, (
                    f"{nome}: {tipo} usa campo fora do schema: {nao_aceitos}"
                )