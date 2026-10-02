import pytest
import tempfile
import os
from pathlib import Path
from src.iaclab import render
from src.iaclab.render import (
    Artefato,
    EXT_BRUTO,
    EXT_NORMALIZADO,
    SUBDIR,
    NOME_MANIFESTO,
    normalizar,
    artefato,
    escrever,
    ler_normalizado,
    manifesto,
    escrever_manifesto,
    houve_render,
    nome_de,
)


def test_normalizar_removes_generation_header():
    """Test that normalizar() removes the generation header."""
    bruto_com_cabecalho = """! source: /path/to/config.yaml
! type: switch
! hostname: core
! config: ficticio

config internal comment
vlan 10
interface GigabitEthernet0/0
  ip address 192.168.1.1 255.255.255.0"""

    bruto_sem_cabecalho = normalizar(bruto_com_cabecalho)
    assert not bruto_sem_cabecalho.startswith("!")
    assert "config internal comment" in bruto_sem_cabecalho
    assert "vlan 10" in bruto_sem_cabecalho


def test_artefato_creates_correct_artifact():
    """Test that artefato() creates an Artefato with correct properties."""
    bruto = """! source: /path/to/config.yaml
! type: switch
! hostname: core
! config: ficticio

vlan 10
interface GigabitEthernet0/0
  ip address 192.168.1.1 255.255.255.0"""

    artefato_obj = artefato("switch:core", "core", bruto)
    assert isinstance(artefato_obj, Artefato)
    assert artefato_obj.equipamento == "switch:core"
    assert artefato_obj.nome == ".core"
    assert artefato_obj.bruto == bruto
    assert "vlan 10" in artefato_obj.normalizado
    assert not artefato_obj.normalizado.startswith("!")


def test_escrever(tmp_path):
    """Test that escrever() writes files and manifest."""
    artefatos = [
        artefato("switch:core", "core", "bruto1\nline2\n"),
        artefato("switch:firewall", "fw01", "! header\nconteudo\n"),
    ]
    
    caminhos = escrever(artefatos, tmp_path)
    assert len(caminhos) == 5  # 2 artifacts * 2 files + 1 manifesto
    
    # Check raw files exist
    raw1_path = tmp_path / SUBDIR / ".core.cfg"
    raw2_path = tmp_path / SUBDIR / ".fw01.cfg"
    norm1_path = tmp_path / SUBDIR / ".core.normalizado"
    norm2_path = tmp_path / SUBDIR / ".fw01.normalizado"
    
    assert raw1_path.exists()
    assert raw2_path.exists()
    assert norm1_path.exists()
    assert norm2_path.exists()


def test_ler_normalizado_arquivo_nao_existe(tmp_path):
    """Test that ler_normalizado() returns None when file doesn't exist."""
    assert ler_normalizado(tmp_path, ".core") is None


def test_manifesto_vazio_sem_render(tmp_path):
    """Test that manifesto() returns {} when no render exists."""
    assert manifesto(tmp_path) == {}


def test_houve_render_antes_de_escrever(tmp_path):
    """Test that houve_render() returns False before writing."""
    assert not houve_render(tmp_path)


def test_houve_render_depois_de_escrever(tmp_path):
    """Test that houve_render() returns True after writing."""
    artefatos = [artefato("switch:core", "core", "content\n")]
    
    # Before writing
    assert not houve_render(tmp_path)
    
    # Write artifacts
    escrever(artefatos, tmp_path)
    
    # After writing
    assert houve_render(tmp_path)


def test_nome_de():
    """Test that nome_de() creates correct filename."""
    assert nome_de("core") == ".core"
    assert nome_de("fw01") == ".fw01"


def test_ler_normalizado_normaliza_crlf(tmp_path):
    """Test that ler_normalizado() normalizes CRLF to LF."""
    arquivo = tmp_path / SUBDIR / ".core.normalizado"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    
    # Write file with CRLF using bytes (actual line endings)
    with open(arquivo, 'wb') as f:
        f.write(b'line1\r\nline2\r\n')
    
    conteudo = ler_normalizado(tmp_path, ".core")
    # The function should normalize CRLF to LF
    assert "\r\n" not in conteudo
    # Check that we get LF line endings and correct number of lines
    assert conteudo == "line1\nline2\n"


def test_escrever_manifesto(tmp_path):
    """Test that escrever_manifesto() writes manifest correctly."""
    artefatos = [
        artefato("switch:core", "core", "! header\ncontent1\n"),
        artefato("switch:firewall", "fw01", "! header2\ncontent2\n"),
    ]
    
    caminho = escrever_manifesto(artefatos, tmp_path)
    assert caminho.exists()
    
    import json
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert "switch:core" in dados
    assert "switch:firewall" in dados
    # Manifesto stores the normalized content (conteudo property), not raw bruto
    assert "content1\n" in dados["switch:core"]
    assert "content2\n" in dados["switch:firewall"]


def test_manifesto_contra_escrever_manifesto(tmp_path):
    """Test that manifesto() matches what escrever_manifesto() wrote."""
    artefatos = [artefato("switch:core", "core", "! header\ncontent\n")]
    
    # Write manifest
    escrever_manifesto(artefatos, tmp_path)
    
    # Read it back
    manifest_data = manifesto(tmp_path)
    
    # They should match
    assert len(manifest_data) == 1
    assert "switch:core" in manifest_data
    # Manifesto stores conteudo (normalized with trailing newline), not raw bruto
    assert manifest_data["switch:core"] == "content\n"