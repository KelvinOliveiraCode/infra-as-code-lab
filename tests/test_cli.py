"""Testes da linha de comando.

CLI tests.

A CLI e a superficie que o portfolio mostra primeiro, entao os testes aqui
nao verificam so o codigo de saida: verificam que a **saida em texto** e a
que o README promete, e que o dry-run de verdade nao escreve.

O teste do dry-run e o mais importante do arquivo. Um dry-run que escreve em
algum lugar - nem que seja um arquivo de cache - nao e dry-run, e o criterio
de aceite inteiro depende dessa garantia.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iaclab.cli import SAIDA_ALERTA, SAIDA_ERRO, SAIDA_OK, main

RAIZ = Path(__file__).resolve().parent.parent
YAML = [
    str(RAIZ / "infra" / "rede.yaml"),
    str(RAIZ / "infra" / "servidores.yaml"),
    str(RAIZ / "infra" / "acessos.yaml"),
]


def _plano(saida: Path) -> list[str]:
    """Os argumentos do comando `plano` contra um diretorio.

    The `plano` command arguments against a directory.

    Args:
        saida: O diretorio de saida.

    Returns:
        A lista de argumentos.
    """
    argv = ["plano"]
    for caminho in YAML:
        argv += ["--infra", caminho]
    argv += ["--saida", str(saida)]
    return argv


class TestPlano:
    """O comando `plano`."""

    def test_antes_de_gerar_acusa_tudo(self, tmp_path: Path, capsys) -> None:
        codigo = main(_plano(tmp_path))
        assert codigo == SAIDA_ALERTA
        saida = capsys.readouterr().out
        assert "drift manual" in saida
        assert "ALERTA" not in saida.upper() or "RESUMO" in saida

    def test_dry_run_nao_escreve_nada(self, tmp_path: Path) -> None:
        main(_plano(tmp_path))
        # Nem a pasta de saida, nem qualquer arquivo dentro dela.
        assert not (tmp_path / "gerado").exists()
        assert list(tmp_path.rglob("*")) == []

    def test_apos_gerar_diz_sem_mudancas(self, tmp_path: Path, capsys) -> None:
        codigo_gerar = main(
            ["gerar"] + [p for caminho in YAML for p in ("--infra", caminho)]
            + ["--saida", str(tmp_path)]
        )
        assert codigo_gerar == SAIDA_OK
        capsys.readouterr()

        codigo = main(_plano(tmp_path))
        assert codigo == SAIDA_OK
        assert "sem mudancas" in capsys.readouterr().out

    def test_dry_run_repetido_e_idempotente(
        self, tmp_path: Path, capsys
    ) -> None:
        main(_plano(tmp_path))
        primeira = capsys.readouterr().out
        main(_plano(tmp_path))
        segunda = capsys.readouterr().out
        # A saida do dry-run nao pode depender de quantas vezes ele rodou.
        assert primeira == segunda

    def test_dry_run_flag_e_ignorado(self, tmp_path: Path) -> None:
        argv = _plano(tmp_path) + ["--dry-run"]
        assert main(argv) == SAIDA_ALERTA
        assert not (tmp_path / "gerado").exists()

    def test_diff_aparece_no_texto(self, tmp_path: Path, capsys) -> None:
        main(_plano(tmp_path))
        saida = capsys.readouterr().out
        # O diff completo, em formato unificado.
        assert "--- switch:SW-LAB-01 (atual)" in saida
        assert "+++ switch:SW-LAB-01 (desejado)" in saida
        assert "+hostname SW-LAB-01" in saida

    def test_edicao_a_mao_e_acusada(self, tmp_path: Path, capsys) -> None:
        main(
            ["gerar"] + [p for caminho in YAML for p in ("--infra", caminho)]
            + ["--saida", str(tmp_path)]
        )
        capsys.readouterr()

        alvo = tmp_path / "gerado" / ".SW-LAB-01.normalizado"
        alvo.write_text(
            alvo.read_text(encoding="utf-8").replace("SW-LAB-01", "EDITADO"),
            encoding="utf-8",
            newline="\n",
        )

        codigo = main(_plano(tmp_path))
        assert codigo == SAIDA_ALERTA
        assert "drift manual" in capsys.readouterr().out

    def test_yaml_inexistente(self, tmp_path: Path, capsys) -> None:
        codigo = main(["plano", "--infra", str(tmp_path / "nao-existe.yaml")])
        assert codigo == SAIDA_ERRO
        assert "erro de schema" in capsys.readouterr().err.lower()

    def test_schema_invalido_lista_os_problemas(
        self, tmp_path: Path, capsys
    ) -> None:
        # Um tipo desconhecido e recusado na CARGA e vai para o stderr; o
        # bloco PROBLEMAS e para o que o gerador acha depois, e e o caminho
        # que interessa aqui: YAML bem formado com inventario quebrado.
        ruim = tmp_path / "ruim.yaml"
        ruim.write_text(
            "vlans:\n"
            "  - id: 10\n"
            "    nome: CORP\n"
            "    faixa: 10.0.10.0/24\n"
            "equipamentos:\n"
            "  - tipo: switch\n"
            "    hostname: SW-1\n"
            "    portas:\n"
            "      - nome: Gi0/1\n"
            "        modo: access\n"
            "        vlan: 99\n",
            encoding="utf-8",
        )
        codigo = main(["plano", "--infra", str(ruim), "--saida", str(tmp_path / "s")])
        assert codigo == SAIDA_ERRO
        saida = capsys.readouterr().out
        assert "PROBLEMAS DE SCHEMA" in saida
        assert "99" in saida

    def test_tipo_desconhecido_vai_para_o_stderr(
        self, tmp_path: Path, capsys
    ) -> None:
        # Um YAML que nao carrega nao tem plano: nao faz sentido mostrar um
        # plano parcial de um arquivo que o usuario nem consegue abrir.
        ruim = tmp_path / "ruim.yaml"
        ruim.write_text(
            "equipamentos:\n  - tipo: roteador\n    hostname: R1\n",
            encoding="utf-8",
        )
        codigo = main(["plano", "--infra", str(ruim), "--saida", str(tmp_path / "s")])
        assert codigo == SAIDA_ERRO
        assert "erro de schema" in capsys.readouterr().err.lower()


class TestGerar:
    """O comando `gerar`."""

    def _argv(self, saida: Path) -> list[str]:
        argv = ["gerar"]
        for caminho in YAML:
            argv += ["--infra", caminho]
        return argv + ["--saida", str(saida)]

    def test_escreve_os_dois_arquivos_e_o_manifesto(
        self, tmp_path: Path, capsys
    ) -> None:
        codigo = main(self._argv(tmp_path))
        assert codigo == SAIDA_OK
        gerado = tmp_path / "gerado"
        brutos = list(gerado.glob("*.cfg"))
        normalizados = list(gerado.glob("*.normalizado"))
        assert len(brutos) == 7
        assert len(normalizados) == 7
        assert (gerado / ".manifesto.json").exists()
        assert "escritos" in capsys.readouterr().out

    def test_arquivos_terminam_com_uma_quebra(self, tmp_path: Path) -> None:
        main(self._argv(tmp_path))
        for arquivo in tmp_path.glob("gerado/*.normalizado"):
            texto = arquivo.read_text(encoding="utf-8")
            assert texto.endswith("\n")
            assert not texto.endswith("\n\n")

    def test_gerar_e_idempotente(self, tmp_path: Path) -> None:
        main(self._argv(tmp_path))
        primeiro = {
            p.name: p.read_bytes() for p in tmp_path.glob("gerado/*")
        }
        main(self._argv(tmp_path))
        segundo = {
            p.name: p.read_bytes() for p in tmp_path.glob("gerado/*")
        }
        assert primeiro == segundo

    def test_dry_run_no_gerar_nao_escreve(self, tmp_path: Path, capsys) -> None:
        # Saida 1 e o correto: num diretorio novo todo equipamento e drift.
        # O que se verifica aqui e que o --dry-run segurou a escrita.
        codigo = main(self._argv(tmp_path) + ["--dry-run"])
        assert codigo == SAIDA_ALERTA
        assert not (tmp_path / "gerado").exists()
        assert "dry-run" in capsys.readouterr().out

    def test_arquivo_gerado_avisa_que_e_ficticio(self, tmp_path: Path) -> None:
        main(self._argv(tmp_path))
        for arquivo in tmp_path.glob("gerado/*.cfg"):
            texto = arquivo.read_text(encoding="utf-8")
            assert "GERADO por iaclab" in texto
            assert "FICTICIO" in texto


class TestRegras:
    """O comando `regras`."""

    def test_lista_os_tipos(self, capsys) -> None:
        assert main(["regras"]) == SAIDA_OK
        saida = capsys.readouterr().out
        for tipo in ("switch", "firewall", "ap", "servidor"):
            assert tipo in saida

    def test_mostra_que_todos_tem_gerador(self, capsys) -> None:
        main(["regras"])
        saida = capsys.readouterr().out
        assert "NAO" not in saida, "um tipo conhecido aparece sem gerador"

    def test_lista_os_campos(self, capsys) -> None:
        main(["regras"])
        saida = capsys.readouterr().out
        assert "vlan" in saida
        assert "hostname" in saida


class TestAjuda:
    """A ajuda da CLI."""

    def test_help_do_principal(self, capsys) -> None:
        with pytest.raises(SystemExit) as erro:
            main(["--help"])
        assert erro.value.code == 0
        assert "iaclab" in capsys.readouterr().out

    @pytest.mark.parametrize("comando", ["plano", "gerar", "regras"])
    def test_help_de_cada_comando(self, comando: str, capsys) -> None:
        with pytest.raises(SystemExit) as erro:
            main([comando, "--help"])
        assert erro.value.code == 0

    def test_comando_obrigatorio(self, capsys) -> None:
        with pytest.raises(SystemExit) as erro:
            main([])
        assert erro.value.code != 0