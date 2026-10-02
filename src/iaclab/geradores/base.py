"""A base comum dos geradores.

The common base of the generators.

Cada gerador traduz um `Equipamento` do schema em texto de configuracao. Eles
nao escrevem arquivo: devolvem texto. Quem escreve e o `render.py`, e quem
decide se escreve e o `plano.py`.

Essa separacao e o que torna o dry-run honesto. Um gerador que abrisse arquivo
teria o poder de escrever antes de alguem pedir o plano, e o `--dry-run` seria
uma promessa em vez de uma garantia.

## O cabecalho

Todo arquivo gerado comeca com o mesmo cabecalho, e ele nao e decoracao. Ele
carrega tres informacoes que respondem a pergunta que surge na hora do
incidente: de onde veio este arquivo, com qual schema, e que ele e ficticio.

O carimbo de tempo fica de fora de proposito. Uma data de geracao em cada
arquivo faria toda execucao produzir um diff, e o criterio de aceite - rodar
duas vezes e ver "sem mudancas" - seria impossivel de satisfazer.

## A ordem das linhas

Todo gerador ordena o que escreve. Ordem de dict do Python e ordem de YAML sao
estaveis, mas nao sao a ordem que o equipamento espera, e um arquivo de saida
que embaralha linhas entre execucoes e diff inutil.

A regra pratica: secao por secao, na ordem do schema, e dentro de cada secao
na ordem de declaracao do YAML. O ultimo item - declaracao - e o que o
gerador respeita, porque quem escreve o YAML ja pensou na ordem.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from ..modelo import Equipamento, Infraestrutura

# Versao do schema. Aparece no cabecalho de todo arquivo gerado, para que um
# arquivo antigo nao seja lido como atual depois de uma mudanca de schema.
VERSAO_SCHEMA = "1.0"

# Cabecalho comum. Fixo, sem data: ver a docstring do modulo.
CABECALHO = """!
! Arquivo GERADO por iaclab. Nao editar na mao.
!
! fonte     : {fonte}
! tipo      : {tipo}
! schema    : {versao}
!
! CONTEUDO FICTICIO. Nenhum equipamento real e nenhum endereco publico.
! Para mudar este arquivo, mude o YAML de origem e rode o plano de novo.
!
"""


class GeradorBase:
    """O que todo gerador sabe fazer.

    What every generator can do.

    Uma subclasse implementa `linhas()` e, se quiser, valida o equipamento
    antes. O resto - cabecalho, secao, juncao - e igual para todos, e
    reinventar por gerador e a forma garantida de o `plano.py` tratar um
    arquivo de outra maneira.
    """

    #: O tipo de equipamento que esta classe atende.
    tipo: str = ""

    def validar(self, infra: Infraestrutura) -> list[str]:
        """Checa o que o schema nao checa.

        Check what the schema does not check.

        Args:
            infra: A infraestrutura inteira, para olhar VLANs e outros
                equipamentos.

        Returns:
            Uma mensagem por problema. Vazio significa que pode gerar.
        """
        return []

    def linhas(self, equipamento: Equipamento, infra: Infraestrutura) -> list[str]:
        """As linhas de configuracao do equipamento.

        The configuration lines of the device.

        Args:
            equipamento: O equipamento a traduzir.
            infra: A infraestrutura inteira.

        Returns:
            As linhas, sem cabecalho e sem linha final vazia. A ordem e a
            ordem final do arquivo.

        Raises:
            NotImplementedError: Sempre, na base.
        """
        raise NotImplementedError(
            f"{type(self).__name__} precisa implementar linhas()"
        )

    def gerar(self, equipamento: Equipamento, infra: Infraestrutura) -> str:
        """O arquivo completo, pronto para ser escrito.

        The complete file, ready to be written.

        Args:
            equipamento: O equipamento a traduzir.
            infra: A infraestrutura inteira.

        Returns:
            O texto do arquivo, terminando em quebra de linha.
        """
        corpo = self.linhas(equipamento, infra)
        cabecalho = CABECALHO.format(
            fonte=equipamento.origem or "(memoria)",
            tipo=equipamento.tipo,
            versao=VERSAO_SCHEMA,
        )
        linhas = [cabecalho, *corpo, ""]
        return "\n".join(linhas)

    # ------------------------------------------------------------- ajudantes

    def _secao(self, titulo: str) -> list[str]:
        """Uma linha de titulo de secao.

        A section title line.

        Args:
            titulo: O texto da secao.

        Returns:
            Uma unica linha, ja formatada.
        """
        return [f"! {titulo}"]

    def _vlan(self, infra: Infraestrutura, identificador: object) -> str:
        """O texto de uma VLAN, para usar em comentario.

        The text of a VLAN, for use in a comment.

        Quando a VLAN nao existe, devolve o identificador cru em vez de
        estourar. O gerador nao e o lugar de recusar referencia quebrada: o
        `plano.py` ja Listingou o problema, e um gerador que quebra aqui
        impediria o relatorio de mostrar os outros problemas.

        Args:
            infra: A infraestrutura inteira.
            identificador: Id, nome ou faixa da VLAN.

        Returns:
            ``VLAN <id> <nome>`` ou ``VLAN <identificador>?``.
        """
        vlan = infra.vlan(identificador)
        if vlan is None:
            return f"VLAN {identificador}?"
        return f"VLAN {vlan.id} {vlan.nome}"

    def _comentario(self, texto: object) -> str:
        """Normaliza um comentario em uma linha.

        Normalize a comment into one line.

        Uma quebra de linha num valor do YAML viraria um comentario de duas
        linhas no arquivo gerado, que na sintaxe do equipamento comeca um
        comando novo. Trocar por espaco e silencioso; o conteudo continua o
        mesmo e o arquivo continua valido.

        Args:
            texto: O valor bruto do YAML.

        Returns:
            O texto em uma linha, sem quebra.
        """
        return " ".join(str(texto).split())


def juntar(blocos: Iterable[Sequence[str]]) -> list[str]:
    """Junta blocos de linhas pulando os vazios no meio.

    Join line blocks, dropping empty ones in the middle.

    Um bloco vazio no meio de um arquivo de configuracao nao e erro de
    sintaxe, mas faz o diff mostrar uma linha a mais ou a menos e o arquivo
    fica mais dificil de ler. Entre blocos, o vazio some; a ultima linha do
    arquivo e garantida por quem chama.

    Args:
        blocos: Os blocos, na ordem.

    Returns:
        As linhas de todos os blocos, sem linha vazia entre eles.
    """
    resultado: list[str] = []
    for bloco in blocos:
        for linha in bloco:
            if linha.strip():
                resultado.append(linha)
    return resultado