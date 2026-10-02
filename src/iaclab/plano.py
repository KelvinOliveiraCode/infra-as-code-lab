"""Monta e imprime o plano, sem aplicar nada.

Build and print the plan, applying nothing.

Este e o modulo que da sentido ao projeto. A regra e uma: **o plano nao escreve
em equipamento nenhum**, e o unico lugar que escreve em disco e o `render.py`,
chamado aqui apenas quando o modo dry-run esta desligado.

## Por que o dry-run e o padrao

Um plano mostra o que *ia* acontecer. Aplicar e um passo separado, e nenhum
comando deste pacote faz isso. Isso nao e limitacao, e a tese: IaC cujo passo
unico e "aplicar" reproduz, em escala, o problema que ele promete resolver -
ninguem ve o diff antes de derrubar o trunk.

O que o plano faz, e o suficiente para o trabalho de verdade:

- **detectar erro de schema** antes de gerar, para o diff comeca limpo;
- **gerar** o texto desejado de cada equipamento;
- **comparar** com o ultimo estado gerado e classificar a diferenca
  (drift manual, mudanca gerenciada, sem mudanca);
- **imprimir** o diff completo;
- **escrever** os arquivos, so se o modo deixar.

## O criterio de aceite

Duas execucoes seguidas tem de dar "sem mudancas". Isso e garantido por tres
decisoes, e vale a pena listar porque sao as que quebram a idempotencia se
mudar:

1. **Sem timestamp** no texto gerado. Uma data por arquivo faria toda execucao
   diferir da anterior.
2. **Ordem fixa** dos equipamentos e das secoes, sem depender de hash.
3. **Comparacao do normalizado**, sem o cabecalho da geracao, que carrega a
   origem do YAML e muda se o caminho mudar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import diff as modulo_diff
from . import render
from .cargador import carregar
from .geradores import por_tipo
from .modelo import ErroDeSchema, Infraestrutura, referencias_quebradas


@dataclass(frozen=True)
class Plano:
    """O resultado de planejar uma mudanca.

    The result of planning a change.

    Attributes:
        diffs: Um diff por equipamento, na ordem de declaracao.
        artefatos: Os artefatos que seriam escritos.
        problemas: Os erros de schema e de referencia que impediram parte do
            plano. Um plano com problemas mostra o que deu para calcular e
            lista o que faltou.
        dry_run: Se este plano nao vai escrever nada.
    """

    diffs: tuple[modulo_diff.Diff, ...] = ()
    artefatos: tuple[render.Artefato, ...] = ()
    problemas: tuple[str, ...] = ()
    dry_run: bool = True

    @property
    def com_alerta(self) -> tuple[modulo_diff.Diff, ...]:
        """Os diffs que acusam diferenca.

        The diffs that report a difference.
        """
        return tuple(d for d in self.diffs if d.alerta)

    @property
    def sem_mudanca(self) -> bool:
        """Se o plano inteiro esta limpo.

        Whether the whole plan is clean.

        Verdadeiro so quando nenhum equipamento acusou e nenhum erro de
        schema impediu parte do calculo. Um plano com erro de schema nao e um
        plano "sem mudancas": e um plano incompleto, e a diferenca importa
        porque "completo e vazio" e o unico estado em que da para dizer que a
        infraestrutura esta como o YAML diz.
        """
        return not self.com_alerta and not self.problemas

    def aplicar(self, diretorio: str | Path) -> list[Path]:
        """Escreve os artefatos, se este plano permitir.

        Write the artifacts, if this plan allows it.

        Args:
            diretorio: O diretorio de saida.

        Returns:
            Os caminhos escritos. Vazio em dry-run.

        Raises:
            PermissaoNegada: Se o plano for dry-run.
        """
        if self.dry_run:
            raise PermissaoNegada(
                "plano em dry-run nao escreve nada; "
                "rode com --escrever para gerar os arquivos"
            )
        return render.escrever(list(self.artefatos), diretorio)


class PermissaoNegada(Exception):
    """Acao proibida pelo modo do plano.

    An action forbidden by the plan's mode.
    """


def _coleta_validacao(infra: Infraestrutura) -> list[str]:
    """Roda a validacao de todos os geradores sobre a infraestrutura.

    Run every generator's validation over the infrastructure.

    A ordem e a de `modelo.iterar_tipos`, para que dois equipamentos com o
    mesmo tipo de erro aparecam sempre na mesma ordem no plano.

    Args:
        infra: A infraestrutura carregada.

    Returns:
        Todas as mensagens, na ordem dos tipos.
    """
    problemas: list[str] = []
    problemas.extend(referencias_quebradas(infra))
    for tipo in ("switch", "firewall", "ap", "servidor"):
        gerador = por_tipo(tipo)
        problemas.extend(gerador.validar(infra))
    return problemas


def planejar(
    caminhos: list[str | Path],
    saida: str | Path,
    escrever: bool = False,
) -> Plano:
    """Le o YAML, gera, compara e monta o plano.

    Read the YAML, generate, compare and build the plan.

    Args:
        caminhos: Os arquivos YAML, em ordem de precedencia.
        saida: O diretorio de saida, onde o estado atual mora.
        escrever: Se `True`, o plano podera escrever. `False` (o padrao) e
            dry-run: nada e escrito em lugar nenhum.

    Returns:
        O plano pronto.

    Raises:
        ErroDeSchema: Se o YAML nao carregar. Um YAML que nao carrega nao tem
            plano - nao faz sentido mostrar um plano parcial de um arquivo que
            o usuario nem consegue abrir.
    """
    infra = carregar(caminhos)
    problemas = _coleta_validacao(infra)

    artefatos: list[render.Artefato] = []
    diffs: list[modulo_diff.Diff] = []
    manifesto = render.manifesto(saida)

    for equipamento in infra.equipamentos:
        gerador = por_tipo(equipamento.tipo)
        bruto = gerador.gerar(equipamento, infra)
        artefato = render.artefato(
            equipamento.identidade, equipamento.hostname, bruto
        )
        artefatos.append(artefato)

        atual = render.ler_normalizado(saida, artefato.nome)
        diffs.append(
            modulo_diff.comparar_texto(
                equipamento.identidade,
                equipamento.tipo,
                equipamento.hostname,
                artefato.conteudo,
                atual,
                ultimo_gerado=manifesto.get(equipamento.identidade),
            )
        )

    return Plano(
        diffs=tuple(diffs),
        artefatos=tuple(artefatos),
        problemas=tuple(problemas),
        dry_run=not escrever,
    )