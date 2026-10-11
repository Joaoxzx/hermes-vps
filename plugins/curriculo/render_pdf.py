"""Converte o HTML da entrada padrão em PDF e imprime o número de páginas.

Roda com o Python do sistema (onde está o pacote weasyprint do apt), fora do
processo do Hermes. Não busca nada fora: fontes vêm do sistema e qualquer URL
no HTML é recusada.
"""

import sys

from weasyprint import HTML


def sem_rede(url, *args, **kwargs):
    raise ValueError(f"acesso externo bloqueado: {url}")


def main():
    destino = sys.argv[1]
    documento = HTML(string=sys.stdin.buffer.read().decode("utf-8"), url_fetcher=sem_rede).render()
    documento.write_pdf(destino)
    print(len(documento.pages))


if __name__ == "__main__":
    main()
