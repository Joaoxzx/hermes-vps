"""Teste sem IA, direto no terminal.

    python3 teste.py opcoes             mostra o que o modelo vê
    python3 teste.py gerar [fullstack]  gera um PDF de teste em ~/curriculos
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nucleo  # noqa: E402


def main():
    acao = sys.argv[1] if len(sys.argv) > 1 else "opcoes"
    try:
        op = nucleo.opcoes()
        if acao == "opcoes":
            resultado = op
        else:
            topicos = []
            for i, e in enumerate(op["experiencias"]):
                ids = list(e["topicos"])
                topicos += ids[:7] if i == 0 else ids[:2]
            resultado = nucleo.gerar({
                "acao": "gerar", "vaga": "teste", "perfil": sys.argv[2] if len(sys.argv) > 2 else "backend",
                "topicos": topicos, "linguagens": op["linguagens"], "tecnologias": op["tecnologias"]})
    except nucleo.ErroCurriculo as e:
        resultado = {"erro": str(e)}
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
