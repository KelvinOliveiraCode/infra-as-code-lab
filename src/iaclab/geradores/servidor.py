"""Gerador de configuracao de servidor.

Servidor configuration generator.

Translates the declaration of a servidor into fictitious configuration syntax
without Cisco style: groups, users without password, and permissions.
"""

from __future__ import annotations

from typing import Any

from ..modelo import Equipamento, Infraestrutura
from .base import GeradorBase, juntar


class GeradorServidor(GeradorBase):
    """Configuracao de servidor a partir da declaracao.

    Servidor configuration from the declaration.
    """

    tipo = "servidor"

    def validar(self, infra: Infraestrutura) -> list[str]:
        """Checa grupos, usuarios e permissoes.

        Check groups, users and permissions.

        Args:
            infra: A infraestrutura inteira.

        Returns:
            Uma mensagem por problema encontrado.
        """
        problemas: list[str] = []

        for equipamento in infra.por_tipo(self.tipo):
            identidade = equipamento.identidade
            grupos = equipamento.campos.get("grupos") or []
            usuarios = equipamento.campos.get("usuarios") or []
            permissoes = equipamento.campos.get("permissoes") or []

            if not isinstance(grupos, list):
                problemas.append(f"{identidade}.grupos: esperado uma lista")
                continue

            nomes_grupos: set[str] = set()
            for indice, grupo in enumerate(grupos):
                onde = f"{identidade}.grupos[{indice}]"
                if not isinstance(grupo, dict):
                    problemas.append(f"{onde}: esperado um mapa")
                    continue

                nome = str(grupo.get("nome", "")).strip()
                if not nome:
                    problemas.append(f"{onde}.nome: obrigatorio")
                elif nome in nomes_grupos:
                    problemas.append(f"{onde}.nome: {nome} repetido")
                else:
                    nomes_grupos.add(nome)

            if not isinstance(usuarios, list):
                problemas.append(f"{identidade}.usuarios: esperado uma lista")
                continue

            nomes_usuarios: set[str] = set()
            for indice, usuario in enumerate(usuarios):
                onde = f"{identidade}.usuarios[{indice}]"
                if not isinstance(usuario, dict):
                    problemas.append(f"{onde}: esperado um mapa")
                    continue

                nome = str(usuario.get("nome", "")).strip()
                if not nome:
                    problemas.append(f"{onde}.nome: obrigatorio")
                else:
                    if nome in nomes_usuarios:
                        # Dois usuarios com o mesmo nome no mesmo servidor: o
                        # segundo subscreve o primeiro, e o YAML sugere dois
                        # usuarios onde existe um.
                        problemas.append(f"{onde}.nome: {nome} repetido")
                    else:
                        nomes_usuarios.add(nome)

                    grupos_referenciados = usuario.get("grupos") or []
                    if not isinstance(grupos_referenciados, list):
                        problemas.append(f"{onde}.grupos: esperado uma lista")
                    else:
                        for g in grupos_referenciados:
                            if g not in nomes_grupos:
                                problemas.append(
                                    f"{onde}.grupos: grupo {g} nao declarado"
                                )

            if not isinstance(permissoes, list):
                problemas.append(f"{identidade}.permissoes: esperado uma lista")
                continue

            nomes_caminhos: set[str] = set()
            for indice, permissao in enumerate(permissoes):
                onde = f"{identidade}.permissoes[{indice}]"
                if not isinstance(permissao, dict):
                    problemas.append(f"{onde}: esperado um mapa")
                    continue

                caminho = str(permissao.get("caminho", "")).strip()
                if not caminho:
                    problemas.append(f"{onde}.caminho: obrigatorio")
                elif caminho in nomes_caminhos:
                    # Duas permissoes com o mesmo caminhouberizam: o
                    # equipamento recebe o ultimo modo, e o YAML sugere duas
                    # regras que nunca coexistiram.
                    problemas.append(f"{onde}.caminho: {caminho} repetido")
                else:
                    nomes_caminhos.add(caminho)

                grupo = str(permissao.get("grupo", "")).strip()
                if not grupo:
                    problemas.append(f"{onde}.grupo: obrigatorio")
                elif grupo not in nomes_grupos:
                    problemas.append(f"{onde}.grupo: grupo {grupo} nao declarado")

                modo = str(permissao.get("modo", "")).strip()
                if not modo:
                    problemas.append(f"{onde}.modo: obrigatorio")
                else:
                    if not (modo.isdigit() and 3 <= len(modo) <= 4):
                        problemas.append(f"{onde}.modo: {modo} invalido, deve ser string octal de 3 a 4 digitos")

        return problemas

    def linhas(self, equipamento: Equipamento, infra: Infraestrutura) -> list[str]:
        """As linhas de configuracao do servidor.

        The server configuration lines.

        A ordem e: identidade, grupos, usuarios, permissoes. E a ordem em que
        quem le o arquivo espera encontrar cada coisa.

        Args:
            equipamento: O servidor a traduzir.
            infra: A infraestrutura inteira.

        Returns:
            As linhas, sem cabecalho.
        """
        campos = equipamento.campos

        blocos: list[list[str]] = []
        blocos.append(self._bloco_identidade(campos))
        blocos.append(self._bloco_grupos(campos))
        blocos.append(self._bloco_usuarios(campos))
        blocos.append(self._bloco_permissoes(campos))
        return juntar(blocos)

    # ---------------------------------------------------------------- blocos

    def _bloco_identidade(self, campos: dict[str, Any]) -> list[str]:
        """Hostname e sistema.

        Hostname and system.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de identificacao.
        """
        linhas = [
            f"hostname {campos.get('hostname', 'desconhecido')}",
            f"sistema {campos.get('sistema', 'desconhecido')}",
        ]
        return linhas

    def _bloco_grupos(self, campos: dict[str, Any]) -> list[str]:
        """Os grupos do servidor.

        The server groups.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de grupo.
        """
        bloco = self._secao("grupos")
        for grupo in campos.get("grupos") or []:
            if not isinstance(grupo, dict):
                continue
            nome = grupo.get("nome", "")
            descricao = grupo.get("descricao", "")
            if descricao:
                bloco.append(f"grupo {nome} {self._comentario(descricao)}")
            else:
                bloco.append(f"grupo {nome}")
        return bloco

    def _bloco_usuarios(self, campos: dict[str, Any]) -> list[str]:
        """Os usuarios do servidor.

        The server users.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de usuario.
        """
        bloco = self._secao("usuarios")
        for usuario in campos.get("usuarios") or []:
            if not isinstance(usuario, dict):
                continue
            nome = usuario.get("nome", "")
            shell = usuario.get("shell", "")
            comentario = usuario.get("comentario", "")
            grupos = usuario.get("grupos") or []
            bloco.append(f"usuario {nome} shell {shell}")
            # A pertenca de grupo vai no arquivo, e sem senha nenhuma: quem
            # le este arquivo precisa saber a qual grupo o usuario pertence
            # para auditar acesso, e nao precisa de nenhum segredo.
            if grupos:
                bloco.append(f" grupos {', '.join(str(g) for g in grupos)}")
            if comentario:
                bloco.append(f"  comentario {self._comentario(comentario)}")
        return bloco

    def _bloco_permissoes(self, campos: dict[str, Any]) -> list[str]:
        """As permissoes do servidor.

        The server permissions.

        Args:
            campos: Os campos do equipamento.

        Returns:
            As linhas de permissao.
        """
        bloco = self._secao("permissoes")
        for permissao in campos.get("permissoes") or []:
            if not isinstance(permissao, dict):
                continue
            caminho = permissao.get("caminho", "")
            grupo = permissao.get("grupo", "")
            modo = permissao.get("modo", "")
            tipo = permissao.get("tipo", "")
            linha = f"permisao {caminho} grupo {grupo} modo {modo} tipo {tipo}"
            bloco.append(linha)
        return bloco