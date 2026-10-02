"""O pacote iaclab.

The iaclab package.

Infraestrutura declarada em YAML e gerada em arquivo de configuracao, sem
aplicar em equipamento nenhum. O principio esta no `plano.py`: `--dry-run` e o
padrao e nao uma opcao, porque o custo de uma aplicacao errada e maior que o
custo de um diff a mais para ler.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]