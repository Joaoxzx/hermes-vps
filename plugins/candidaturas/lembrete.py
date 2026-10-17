"""Lembrete diário de pedir retorno, sem IA. Roda no cron do usuário hermes.

    python3 lembrete.py            manda o aviso no #candidaturas, se houver o que avisar
    python3 lembrete.py --mostrar  só mostra o que mandaria, sem mandar nem contar o aviso
    python3 lembrete.py --testar   manda uma mensagem de teste, para conferir o webhook
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nucleo  # noqa: E402

WEBHOOK = Path.home() / "avisos" / "webhook_candidaturas"
LIMITE_DISCORD = 1900  # o Discord aceita até 2000 caracteres por mensagem


def montar(pendentes):
    linhas = ["**Vale pedir retorno**"]
    linhas += [f"#{c['id']} {c['empresa']} — {c['cargo']} ({c['onde']}): {c['status']}, "
               f"{c['dias_sem_novidade']} dias sem novidade" for c in pendentes]
    linhas.append("Atualize no Telegram com /candidaturas <número> <status>.")
    return "\n".join(linhas)[:LIMITE_DISCORD]


def enviar(texto):
    corpo = json.dumps({
        "content": texto,
        # Empresa e cargo podem ter vindo de texto de vaga: nada de @everyone nem menção.
        "allowed_mentions": {"parse": []},
    }).encode("utf-8")
    pedido = urllib.request.Request(WEBHOOK.read_text().strip(), data=corpo, headers={
        "Content-Type": "application/json", "User-Agent": "hermes-candidaturas"})
    with urllib.request.urlopen(pedido, timeout=15):
        pass


def main():
    if "--testar" in sys.argv:
        enviar("Teste do lembrete de candidaturas: o webhook funciona.")
        print("Mensagem de teste enviada.")
        return
    mostrar = "--mostrar" in sys.argv
    pendentes = nucleo.pendentes_de_lembrete()
    if not pendentes:
        if mostrar:
            print("Nada para avisar hoje.")
        return
    texto = montar(pendentes)
    if mostrar:
        print(texto)
        return
    enviar(texto)  # se falhar, levanta erro e o aviso não é contado: amanhã tenta de novo
    nucleo.marcar_lembretes(pendentes)


if __name__ == "__main__":
    main()
