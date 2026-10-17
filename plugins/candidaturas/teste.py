"""Teste sem IA, num banco temporário: o banco de verdade não é tocado.

    python3 teste.py
"""

import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nucleo  # noqa: E402
import lembrete  # noqa: E402

falhas = 0


def confere(nome, condicao, detalhe=""):
    global falhas
    falhas += not condicao
    print("PASSOU" if condicao else "FALHOU", "|", nome, "" if condicao else f"-> {detalhe}")


def erro(funcao, args, banco):
    try:
        funcao(args, banco)
    except nucleo.ErroCandidatura as e:
        return str(e)
    return ""


def main():
    with tempfile.TemporaryDirectory() as pasta:
        banco = Path(pasta) / "candidaturas.db"
        hoje = nucleo.hoje()

        r = nucleo.registrar({"empresa": "Zenvia", "cargo": "Desenvolvedor(a) Operações Júnior", "onde": "Gupy"}, banco)
        confere("registra", r["ok"] and not r["ja_existia"] and r["candidatura"]["status"] == "enviada", r)
        zenvia = r["candidatura"]["id"]

        r = nucleo.registrar({"empresa": "zenvia", "cargo": "Desenvolvedor(a) Operacoes Junior", "onde": "linkedin"}, banco)
        confere("repetida aberta não duplica (acento e maiúscula)", r["ja_existia"] and r["candidatura"]["id"] == zenvia, r)

        confere("onde inválido", "'onde'" in erro(nucleo.registrar, {"empresa": "X", "cargo": "Y", "onde": "jornal"}, banco))
        confere("url sem http", "'url'" in erro(nucleo.registrar, {"empresa": "X", "cargo": "Y", "onde": "site", "url": "javascript:alert(1)"}, banco))
        confere("data no futuro", "'enviada_em'" in erro(nucleo.registrar, {"empresa": "X", "cargo": "Y", "onde": "site",
                                                                           "enviada_em": (hoje + timedelta(days=1)).isoformat()}, banco))
        confere("empresa vazia", "'empresa'" in erro(nucleo.registrar, {"empresa": " ", "cargo": "Y", "onde": "site"}, banco))

        antiga = nucleo.registrar({"empresa": "ACME", "cargo": "Back-end Jr", "onde": "e-mail",
                                   "enviada_em": (hoje - timedelta(days=8)).isoformat()}, banco)["candidatura"]
        confere("e-mail vira email e data antiga vale", antiga["onde"] == "email" and antiga["dias_sem_novidade"] == 8, antiga)

        pend = nucleo.pendentes_de_lembrete(banco=banco)
        confere("8 dias sem novidade pede lembrete", [c["id"] for c in pend] == [antiga["id"]], pend)
        nucleo.marcar_lembretes(pend, banco=banco)
        confere("depois do aviso dos 7 dias, nada no mesmo dia", nucleo.pendentes_de_lembrete(banco=banco) == [])
        dia15 = hoje + timedelta(days=7)  # a ACME faz 15 dias; a Zenvia, 7
        pend = nucleo.pendentes_de_lembrete(dia15, banco)
        confere("aos 15 dias, o segundo aviso (e o primeiro da Zenvia)",
                sorted((c["id"], c["lembretes"]) for c in pend) == sorted([(antiga["id"], 1), (zenvia, 0)]), pend)
        nucleo.marcar_lembretes(pend, banco=banco)
        confere("depois do segundo, para",
                antiga["id"] not in [c["id"] for c in nucleo.pendentes_de_lembrete(hoje + timedelta(days=60), banco)])

        r = nucleo.atualizar({"id": antiga["id"], "status": "entrevista", "nota": "dia 20 às 14h"}, banco)
        confere("atualiza e zera lembretes", r["candidatura"]["status"] == "entrevista" and r["candidatura"]["lembretes"] == 0, r)
        confere("status igual é recusado", "já está" in erro(nucleo.atualizar, {"id": antiga["id"], "status": "entrevista"}, banco))
        confere("status inválido", "'status'" in erro(nucleo.atualizar, {"id": antiga["id"], "status": "aprovado"}, banco))
        confere("id que não existe", "Não existe" in erro(nucleo.atualizar, {"id": 999, "status": "teste"}, banco))
        confere("id texto", "'id'" in erro(nucleo.atualizar, {"id": "1", "status": "teste"}, banco))

        pend = nucleo.pendentes_de_lembrete(hoje + timedelta(days=7), banco)
        nucleo.atualizar({"id": antiga["id"], "status": "teste"}, banco)
        nucleo.marcar_lembretes(pend, banco=banco)
        linha = [c for c in nucleo.listar({}, banco)["candidaturas"] if c["id"] == antiga["id"]][0]
        confere("aviso não conta se o status mudou no meio", linha["lembretes"] == 0, linha)

        nucleo.atualizar({"id": zenvia, "status": "recusada"}, banco)
        confere("encerrada sai das abertas", zenvia not in [c["id"] for c in nucleo.listar({}, banco)["candidaturas"]])
        confere("todas inclui a encerrada", zenvia in [c["id"] for c in nucleo.listar({"filtro": "todas"}, banco)["candidaturas"]])
        nova = nucleo.registrar({"empresa": "Zenvia", "cargo": "Desenvolvedor(a) Operações Júnior", "onde": "gupy"}, banco)
        confere("depois de recusada, pode se candidatar de novo", not nova["ja_existia"], nova)
        confere("reabrir a antiga com outra aberta igual é barrado",
                "outra candidatura aberta" in erro(nucleo.atualizar, {"id": zenvia, "status": "enviada"}, banco))

        texto = nucleo.comando_candidaturas("", banco)
        confere("/candidaturas lista as abertas", texto.startswith("Candidaturas abertas (2)") and "ACME" in texto, texto)
        texto = nucleo.comando_candidaturas(f"{antiga['id']} proposta salário a combinar", banco)
        confere("/candidaturas <n> <status> atualiza", texto.startswith("Atualizada") and "proposta" in texto, texto)
        confere("/candidaturas com status errado", "'status'" in nucleo.comando_candidaturas(f"{antiga['id']} contratado", banco))
        confere("/candidaturas sem status mostra ajuda", "Para mudar" in nucleo.comando_candidaturas("3", banco))

        msg = lembrete.montar([{"id": 7, "empresa": "@everyone Empresa", "cargo": "Dev", "onde": "gupy",
                                "status": "enviada", "dias_sem_novidade": 7}])
        confere("aviso do Discord montado", msg.startswith("**Vale pedir retorno**") and "#7" in msg, msg)

        with closing(sqlite3.connect(banco)) as con:  # o "with" da conexão só confirma; quem fecha é o closing
            hist = con.execute("SELECT COUNT(*) FROM historico").fetchone()[0]
        # 2 da Zenvia, 1 da ACME, entrevista, teste, recusada e proposta; o que foi barrado não entra
        confere("histórico guarda cada mudança", hist == 7, hist)

    print("FALHAS:", falhas)
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
