"""Plugin do Hermes: currículo em PDF ajustado para uma vaga.

O modelo escolhe o perfil e escolhe/ordena tópicos e tecnologias do currículo
mestre. O texto e o visual são fixos (nucleo.py), então o modelo não consegue
inventar experiência nem mudar o layout. Mudanças no mestre o modelo só propõe;
quem aplica é o usuário, com o comando /mestre.
"""

import json

from . import nucleo

SCHEMA = {
    "name": "curriculo_pdf",
    "description": (
        "Gera o currículo do usuário em PDF ajustado para uma vaga. Todo o texto vem do currículo mestre: "
        "você só escolhe o perfil e escolhe/ordena tópicos e tecnologias, nunca escreve texto novo. "
        "Se o usuário citar a vaga pelo nome, comece com acao='buscar_vaga' (vagas dos últimos dias). "
        "Depois acao='opcoes' (IDs e regras) e acao='gerar'. "
        "Se der certo, ponha na resposta a linha MEDIA do resultado para o PDF ir junto. "
        f"Quando o usuário contar algo novo para o currículo (projeto, tópico, tecnologia), leia {nucleo.MESTRE} "
        "e use acao='propor_mestre' com o texto inteiro já mudado; só ele aplica, com /mestre."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {"type": "string", "enum": ["buscar_vaga", "opcoes", "gerar", "propor_mestre"]},
            "busca": {"type": "string", "description": "Empresa ou cargo, para acao='buscar_vaga'."},
            "vaga": {"type": "string", "description": "Empresa e cargo, para nomear a pasta. Ex.: 'ISA Saúde - Back-end Jr'."},
            "perfil": {"type": "string", "enum": ["backend", "fullstack"]},
            "topicos": {"type": "array", "items": {"type": "string"},
                        "description": "IDs dos tópicos na ordem em que devem aparecer (ex.: e1.4, e1.3, e2.1)."},
            "linguagens": {"type": "array", "items": {"type": "string"},
                           "description": "Linguagens do mestre, na ordem de destaque."},
            "tecnologias": {"type": "array", "items": {"type": "string"},
                            "description": "Tecnologias do mestre, na ordem de destaque."},
            "texto": {"type": "string",
                      "description": "Para acao='propor_mestre': o currículo mestre inteiro, já com a mudança."},
        },
        "required": ["acao"],
    },
}


def _responder(dados):
    return json.dumps(dados, ensure_ascii=False)


def curriculo_pdf(args, **kwargs):
    try:
        acao = args.get("acao")
        if acao == "buscar_vaga":
            return _responder(nucleo.buscar_vaga(args.get("busca")))
        if acao == "opcoes":
            return _responder(nucleo.opcoes())
        if acao == "gerar":
            return _responder(nucleo.gerar(args))
        if acao == "propor_mestre":
            return _responder(nucleo.propor_mestre(args.get("texto")))
        return _responder({"erro": "acao precisa ser 'buscar_vaga', 'opcoes', 'gerar' ou 'propor_mestre'."})
    except nucleo.ErroCurriculo as e:
        return _responder({"erro": str(e)})
    except Exception as e:
        return _responder({"erro": f"Falha inesperada: {type(e).__name__}: {e}"})


def comando_mestre(argumentos):
    try:
        return nucleo.comando_mestre(argumentos)
    except Exception as e:
        return f"Falha no /mestre: {type(e).__name__}: {e}"


def register(ctx):
    ctx.register_tool(name="curriculo_pdf", toolset="curriculo", schema=SCHEMA, handler=curriculo_pdf)
    ctx.register_command("mestre", handler=comando_mestre,
                         description="Ver, aplicar ou descartar a mudança proposta no currículo mestre",
                         args_hint="[aplicar <código> | descartar]")
