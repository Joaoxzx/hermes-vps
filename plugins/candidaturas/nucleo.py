"""Controle de candidaturas, sem IA.

Guarda num SQLite cada candidatura e cada mudança de status. O agente registra e
atualiza pela ferramenta; o usuário lista e muda pelo comando /candidaturas; um
cron diário (lembrete.py) avisa no Discord quando vale pedir retorno.

Não existe ação de apagar: uma candidatura encerrada fica como recusada ou desisti.
"""

import os
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BANCO = Path(os.path.expanduser("~/candidaturas/candidaturas.db"))

ABERTOS = ("enviada", "teste", "entrevista", "proposta")
ENCERRADOS = ("recusada", "desisti")
STATUS = ABERTOS + ENCERRADOS
ONDE = ("gupy", "linkedin", "email", "site", "indicacao", "outro")
DIAS_LEMBRETE = 7  # um aviso aos 7 dias sem novidade, outro aos 14, e para
MAX_LEMBRETES = 2
LIMITE_LISTA = 30


def _sql_lista(valores):
    """Lista SQL de constantes deste arquivo (nunca de entrada do usuário)."""
    return ", ".join(f"'{v}'" for v in valores)


ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS candidaturas (
    id            INTEGER PRIMARY KEY,
    empresa       TEXT NOT NULL CHECK (length(empresa) BETWEEN 1 AND 80),
    cargo         TEXT NOT NULL CHECK (length(cargo) BETWEEN 1 AND 120),
    chave         TEXT NOT NULL,  -- empresa e cargo normalizados, para achar a repetida
    onde          TEXT NOT NULL CHECK (onde IN ({_sql_lista(ONDE)})),
    url           TEXT CHECK (url IS NULL OR length(url) <= 500),
    status        TEXT NOT NULL CHECK (status IN ({_sql_lista(STATUS)})),
    enviada_em    TEXT NOT NULL,  -- data local (America/Sao_Paulo), AAAA-MM-DD
    atualizada_em TEXT NOT NULL,  -- data local da última mudança de status
    lembretes     INTEGER NOT NULL DEFAULT 0,  -- avisos já mandados no status atual
    notas         TEXT CHECK (notas IS NULL OR length(notas) <= 500)
);

-- No máximo uma candidatura aberta por empresa e cargo. A aplicação já confere antes
-- de gravar; o índice é a última proteção, mesmo com o gateway e o cron escrevendo juntos.
CREATE UNIQUE INDEX IF NOT EXISTS uma_aberta_por_vaga ON candidaturas (chave)
    WHERE status IN ({_sql_lista(ABERTOS)});

CREATE TABLE IF NOT EXISTS historico (
    id             INTEGER PRIMARY KEY,
    candidatura_id INTEGER NOT NULL REFERENCES candidaturas (id),
    status         TEXT NOT NULL,
    em             TEXT NOT NULL,  -- instante em UTC, ISO 8601
    nota           TEXT
);
CREATE INDEX IF NOT EXISTS historico_por_candidatura ON historico (candidatura_id);
"""


class ErroCandidatura(Exception):
    """Erro com mensagem para o modelo ou para o usuário."""


# ---------- utilitários ----------

def _chave(texto):
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def hoje():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except Exception:
        return date.today()


def _agora_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _texto(valor, nome, maximo, obrigatorio=True):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ErroCandidatura(f"'{nome}' é obrigatório.")
        return None
    if not isinstance(valor, str) or len(valor.strip()) > maximo:
        raise ErroCandidatura(f"'{nome}' precisa ser um texto de até {maximo} caracteres.")
    return valor.strip()


def _onde(valor):
    k = re.sub(r"[^a-z]", "", _chave(valor or ""))
    achado = next((o for o in ONDE if k.startswith(o)), None)
    if not achado:
        raise ErroCandidatura(f"'onde' precisa ser um destes: {', '.join(ONDE)}.")
    return achado


def _status(valor):
    s = _chave(valor or "") if isinstance(valor, str) else ""
    if s not in STATUS:
        raise ErroCandidatura(f"'status' precisa ser um destes: {', '.join(STATUS)}.")
    return s


def _data(valor, padrao):
    if valor is None or valor == "":
        return padrao
    try:
        d = date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ErroCandidatura("'enviada_em' precisa estar no formato AAAA-MM-DD.")
    if not padrao - timedelta(days=365) <= d <= padrao:
        raise ErroCandidatura("'enviada_em' precisa ser de hoje ou do último ano.")
    return d


# ---------- banco ----------

def _abrir(banco):
    novo = not banco.exists()
    banco.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    con = sqlite3.connect(banco, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    if novo:
        banco.chmod(0o600)
    return con


def _publica(linha, dia):
    """O que sai do banco para o modelo ou para o usuário."""
    c = dict(linha)
    c.pop("chave", None)
    c["dias_sem_novidade"] = (dia - date.fromisoformat(c["atualizada_em"])).days
    return c


# ---------- ações do agente ----------

def registrar(args, banco=BANCO):
    empresa = _texto(args.get("empresa"), "empresa", 80)
    cargo = _texto(args.get("cargo"), "cargo", 120)
    onde = _onde(args.get("onde"))
    url = _texto(args.get("url"), "url", 500, obrigatorio=False)
    if url and not re.match(r"^https?://", url):
        raise ErroCandidatura("'url' precisa começar com http:// ou https://.")
    notas = _texto(args.get("notas"), "notas", 500, obrigatorio=False)
    dia = hoje()
    enviada_em = _data(args.get("enviada_em"), dia)
    chave = f"{_chave(empresa)}|{_chave(cargo)}"

    with closing(_abrir(banco)) as con:
        existente = con.execute(
            f"SELECT * FROM candidaturas WHERE chave = ? AND status IN ({_sql_lista(ABERTOS)})", (chave,)).fetchone()
        if existente:
            return {"ok": True, "ja_existia": True, "candidatura": _publica(existente, dia),
                    "aviso": "Já havia uma candidatura aberta para essa empresa e esse cargo; nada foi criado."}
        try:
            with con:  # transação: a candidatura e a primeira linha do histórico entram juntas
                cur = con.execute(
                    "INSERT INTO candidaturas (empresa, cargo, chave, onde, url, status, enviada_em, atualizada_em, notas)"
                    " VALUES (?, ?, ?, ?, ?, 'enviada', ?, ?, ?)",
                    (empresa, cargo, chave, onde, url, enviada_em.isoformat(), enviada_em.isoformat(), notas))
                con.execute("INSERT INTO historico (candidatura_id, status, em, nota) VALUES (?, 'enviada', ?, ?)",
                            (cur.lastrowid, _agora_utc(), notas))
        except sqlite3.IntegrityError:
            raise ErroCandidatura("Outra candidatura aberta igual foi gravada agora; use acao='listar'.")
        nova = con.execute("SELECT * FROM candidaturas WHERE id = ?", (cur.lastrowid,)).fetchone()
        return {"ok": True, "ja_existia": False, "candidatura": _publica(nova, dia)}


def atualizar(args, banco=BANCO):
    ident = args.get("id")
    if isinstance(ident, bool) or not isinstance(ident, int) or ident < 1:
        raise ErroCandidatura("'id' precisa ser o número da candidatura (veja com acao='listar').")
    status = _status(args.get("status"))
    nota = _texto(args.get("nota"), "nota", 500, obrigatorio=False)
    dia = hoje()

    with closing(_abrir(banco)) as con:
        atual = con.execute("SELECT * FROM candidaturas WHERE id = ?", (ident,)).fetchone()
        if not atual:
            raise ErroCandidatura(f"Não existe candidatura número {ident}.")
        if atual["status"] == status:
            raise ErroCandidatura(f"A candidatura {ident} já está como {status}.")
        try:
            with con:
                con.execute("UPDATE candidaturas SET status = ?, atualizada_em = ?, lembretes = 0 WHERE id = ?",
                            (status, dia.isoformat(), ident))
                con.execute("INSERT INTO historico (candidatura_id, status, em, nota) VALUES (?, ?, ?, ?)",
                            (ident, status, _agora_utc(), nota))
        except sqlite3.IntegrityError:
            raise ErroCandidatura("Já existe outra candidatura aberta para essa empresa e esse cargo.")
        nova = con.execute("SELECT * FROM candidaturas WHERE id = ?", (ident,)).fetchone()
        return {"ok": True, "candidatura": _publica(nova, dia)}


def listar(args, banco=BANCO):
    todas = _chave(args.get("filtro") or "") == "todas"
    dia = hoje()
    filtro = "" if todas else f"WHERE status IN ({_sql_lista(ABERTOS)})"
    with closing(_abrir(banco)) as con:
        linhas = con.execute(f"SELECT * FROM candidaturas {filtro} ORDER BY id DESC LIMIT ?", (LIMITE_LISTA,)).fetchall()
    return {"filtro": "todas" if todas else "abertas", "candidaturas": [_publica(x, dia) for x in linhas]}


# ---------- lembrete (cron) ----------

def pendentes_de_lembrete(dia=None, banco=BANCO):
    """Abertas que completaram 7 ou 14 dias sem novidade e ainda não tiveram o aviso dessa marca."""
    dia = dia or hoje()
    with closing(_abrir(banco)) as con:
        linhas = con.execute(
            f"SELECT * FROM candidaturas WHERE status IN ({_sql_lista(ABERTOS)}) AND lembretes < ? ORDER BY id",
            (MAX_LEMBRETES,)).fetchall()
    return [_publica(x, dia) for x in linhas
            if (dia - date.fromisoformat(x["atualizada_em"])).days >= DIAS_LEMBRETE * (x["lembretes"] + 1)]


def marcar_lembretes(pendentes, banco=BANCO):
    """Conta o aviso mandado. Se o status mudou depois da leitura, a linha não casa e nada muda."""
    with closing(_abrir(banco)) as con, con:
        for c in pendentes:
            con.execute("UPDATE candidaturas SET lembretes = lembretes + 1"
                        " WHERE id = ? AND status = ? AND atualizada_em = ? AND lembretes = ?",
                        (c["id"], c["status"], c["atualizada_em"], c["lembretes"]))


# ---------- comando /candidaturas (sem IA) ----------

def _linha(c):
    enviada = date.fromisoformat(c["enviada_em"])
    return (f"#{c['id']} {c['empresa']} — {c['cargo']} ({c['onde']})\n"
            f"    {c['status']}, enviada em {enviada:%d/%m}, {c['dias_sem_novidade']} dias sem novidade")


def comando_candidaturas(argumentos, banco=BANCO):
    """/candidaturas lista as abertas; /candidaturas todas lista tudo; /candidaturas <n> <status> [nota] atualiza."""
    partes = (argumentos or "").split()
    ajuda = (f"Para mudar: /candidaturas <número> <status> [nota]\nStatus: {', '.join(STATUS)}\n"
             "Para ver as encerradas também: /candidaturas todas")
    try:
        if partes and partes[0].isdigit():
            if len(partes) < 2:
                return ajuda
            r = atualizar({"id": int(partes[0]), "status": partes[1], "nota": " ".join(partes[2:]) or None}, banco)
            return "Atualizada:\n" + _linha(r["candidatura"])
        if partes and _chave(partes[0]) not in ("todas", "abertas"):
            return ajuda
        r = listar({"filtro": partes[0] if partes else "abertas"}, banco)
    except ErroCandidatura as e:
        return str(e)
    titulo = "Todas as candidaturas" if r["filtro"] == "todas" else "Candidaturas abertas"
    if not r["candidaturas"]:
        return f"{titulo}: nenhuma.\n\n{ajuda}"
    return "\n".join([f"{titulo} ({len(r['candidaturas'])}):"] + [_linha(c) for c in r["candidaturas"]] + ["", ajuda])
