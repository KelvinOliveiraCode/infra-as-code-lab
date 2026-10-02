"""Verifica que nenhum arquivo de texto do repositorio saiu corrompido.

Check that no text file in the repository came out corrupted.

Neste host ja surgiram ideogramas CJK em arquivo que deveria ter acentos
portugueses: um `o` virou um caractere com til, um `a` virou um com trema.
Nao e erro de logica - e corrupcao de encoding, que muda o conteudo e passa
despercebida numa revisao com pressa. Falhar aqui e mais barato do que achar
isso num README publicado.

Tres criterios:

1. **Sem U+FFFD.** E o caractere de substituicao: onde ele aparece, algo foi
   decodificado errado antes. E sempre erro.
2. **Sem CJK.** Nenhum ideograma, kana ou hangul. Um arquivo em portugues ou
   ingles nao tem motivo para ter, e sua presenca significa que a leitura
   usou a codificacao errada em algum ponto.
3. **Codigo e dados sao ASCII.** Comentario pode ter acento; codigo executavel
   e dado de configuracao nao. Isso mantem o arquivo diffavel entre maquinas
   e evita que o acento entre no lugar de um caractere especial.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Diretorios que nao sao codigo nem dado do projeto.
IGNORAR_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    "gerado",
    "saida",
}

# Arquivos que existem na pasta mas nao sao fonte do projeto: cobertura
# compilada, saida de subagent, temporarios. Nao tem texto para conferir, e
# um deles ja era binario e travava a leitura de todo o script.
IGNORAR_ARQUIVOS = {
    ".coverage",
    "coverage.xml",
    "Thumbs.db",
    "Desktop.ini",
}

# Prefixos de arquivos temporarios, gerados por mim e pelos subagents.
PREFIXOS_TEMPORARIOS = ("out-", "tmp_")

# Extensoes de texto que o projeto produz. Os geradores escrevem .cfg e
# .normalizado, entao eles entram.
EXTENSOES = {
    ".py", ".yaml", ".yml", ".md", ".txt", ".cfg", ".normalizado",
    ".toml", ".json", ".ini", ".cfg", ".example",
}

# Faixas de ideogramas: CJK unify, kana, hangul, e os blocos de compatibilidade.
INICIO_CJK = 0x2E80
FIM_CJK = 0x9FFF
INICIO_CJK_EXT = 0xAC00
FIM_CJK_EXT = 0xD7AF
INICIO_COMPAT = 0xF900
FIM_COMPAT = 0xFAFF
INICIO_HALFWIDTH = 0xFF00
FIM_HALFWIDTH = 0xFFEF


def _tem_cjk(caractere: str) -> bool:
    """Se o caractere esta em alguma faixa CJK.

    Whether the character is in a CJK range.

    Args:
        caractere: Um caractere.

    Returns:
        Verdadeiro se for ideograma, kana ou hangul.
    """
    ponto = ord(caractere)
    return (
        INICIO_CJK <= ponto <= FIM_CJK
        or INICIO_CJK_EXT <= ponto <= FIM_CJK_EXT
        or INICIO_COMPAT <= ponto <= FIM_COMPAT
        or INICIO_HALFWIDTH <= ponto <= FIM_HALFWIDTH
    )


def arquivos() -> list[Path]:
    """Os arquivos de texto do projeto.

    The project's text files.

    Returns:
        Todos os arquivos com extensao conhecida, exceto os ignorados.
    """
    encontrados: list[Path] = []
    for caminho in RAIZ.rglob("*"):
        if not caminho.is_file():
            continue
        if any(parte in IGNORAR_DIRS for parte in caminho.parts):
            continue
        if caminho.name in IGNORAR_ARQUIVOS:
            continue
        if caminho.name.startswith(PREFIXOS_TEMPORARIOS):
            continue
        if caminho.suffix.lower() in EXTENSOES or caminho.name.startswith("."):
            encontrados.append(caminho)
    return sorted(encontrados)


def confere(caminho: Path) -> list[str]:
    """Confere um arquivo.

    Check one file.

    Args:
        caminho: O arquivo.

    Returns:
        Uma mensagem por problema. Vazio significa ok.
    """
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError as erro:
        return [f"{caminho}: nao decodifica como UTF-8 ({erro.reason})"]

    problemas: list[str] = []
    relativo = caminho.relative_to(RAIZ)

    for numero, linha in enumerate(texto.splitlines(), start=1):
        if "\ufffd" in linha:
            problemas.append(f"{relativo}:{numero}: U+FFFD (caractere de substituicao)")

        for caractere in linha:
            if _tem_cjk(caractere):
                problemas.append(
                    f"{relativo}:{numero}: caractere CJK "
                    f"{caractere!r} U+{ord(caractere):04X}"
                )
                break

    # Codigo e dado precisam ser ASCII puro. Markdown pode ter acento.
    if caminho.suffix.lower() in {".py", ".yaml", ".yml", ".cfg", ".normalizado"}:
        for numero, linha in enumerate(texto.splitlines(), start=1):
            for caractere in linha:
                if ord(caractere) > 127:
                    problemas.append(
                        f"{relativo}:{numero}: caractere nao-ASCII "
                        f"{caractere!r} U+{ord(caractere):04X} em codigo"
                    )
                    break

    return problemas


def principal() -> int:
    """Roda a conferencia em todos os arquivos.

    Run the check over all files.

    Returns:
        0 se nenhum problema, 1 se algum.
    """
    problemas: list[str] = []
    lista = arquivos()
    for caminho in lista:
        problemas.extend(confere(caminho))

    if problemas:
        print("encoding FALHOU:")
        for problema in problemas:
            print("  ", problema)
        return 1

    print(f"encoding ok: {len(lista)} arquivo(s), nenhum U+FFFD, nenhum CJK, "
          "nenhum caractere nao-ASCII em codigo ou dado")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())