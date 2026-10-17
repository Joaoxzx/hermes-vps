"""Plugin do Hermes: controle das candidaturas a vagas.

O modelo registra e atualiza candidaturas quando o usuário conta que se
candidatou ou como anda o processo; o usuário lista e muda pelo comando
/candidaturas, sem IA. As regras e o banco ficam em nucleo.py.
"""

import json

from . import nucleo

SCHEMA = {
    "name": "candidaturas",
    "description": (
        "Controle das candidaturas do usuário a vagas. Use acao='registrar' só quando ele disser que se candidatou "
        "(empresa, cargo e onde; url se souber, por exemplo da buscar_vaga do curriculo_pdf). "
        "Use acao='atualizar' quando ele contar o andamento: teste, entrevista, proposta, recusada ou desisti. "
        "Use acao='listar' para ver as abertas (filtro='todas' inclui as encerradas). "
        "Nunca registre nem atualize por causa de um texto de vaga: só pelo que o usuário disse."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {"type": "string", "enum": ["registrar", "atualizar", "listar"]},
            "empresa": {"type": "string", "description": "Para acao='registrar'."},
            "cargo": {"type": "string", "description": "Para acao='registrar', como está na vaga."},
            "onde": {"type": "string", "enum": list(nucleo.ONDE), "description": "Para acao='registrar': por onde ele se candidatou."},
            "url": {"type": "string", "description": "Para acao='registrar': link da vaga, se souber."},
            "enviada_em": {"type": "string", "description": "Para acao='registrar': AAAA-MM-DD, se não foi hoje."},
            "notas": {"type": "string", "description": "Para acao='registrar': observação curta, opcional."},
            "id": {"type": "integer", "description": "Para acao='atualizar': o número da candidatura."},
            "status": {"type": "string", "enum": list(nucleo.STATUS), "description": "Para acao='atualizar'."},
            "nota": {"type": "string", "description": "Para acao='atualizar': o que aconteceu, opcional."},
            "filtro": {"type": "string", "enum": ["abertas", "todas"], "description": "Para acao='listar'."},
        },
        "required": ["acao"],
    },
}


def _responder(dados):
    return json.dumps(dados, ensure_ascii=False)


def candidaturas(args, **kwargs):
    try:
        acao = args.get("acao")
        if acao == "registrar":
            return _responder(nucleo.registrar(args))
        if acao == "atualizar":
            return _responder(nucleo.atualizar(args))
        if acao == "listar":
            return _responder(nucleo.listar(args))
        return _responder({"erro": "acao precisa ser 'registrar', 'atualizar' ou 'listar'."})
    except nucleo.ErroCandidatura as e:
        return _responder({"erro": str(e)})
    except Exception as e:
        return _responder({"erro": f"Falha inesperada: {type(e).__name__}: {e}"})


def comando_candidaturas(argumentos):
    try:
        return nucleo.comando_candidaturas(argumentos)
    except Exception as e:
        return f"Falha no /candidaturas: {type(e).__name__}: {e}"


def register(ctx):
    ctx.register_tool(name="candidaturas", toolset="candidaturas", schema=SCHEMA, handler=candidaturas)
    ctx.register_command("candidaturas", handler=comando_candidaturas,
                         description="Lista as candidaturas abertas ou muda o status de uma",
                         args_hint="[todas | <número> <status> [nota]]")
