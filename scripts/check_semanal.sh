#!/bin/bash
# Check semanal da VPS do Hermes: disco, memória e atualizações. Só script, sem IA.
export XDG_RUNTIME_DIR=/run/user/$(id -u)
WEBHOOK=$(cat ~/avisos/webhook_sistema)

USO=$(df / | awk 'NR==2 {gsub("%","",$5); print $5}')
DISCO=$(df -h / | awk 'NR==2 {print $5" usado, "$4" livres"}')
MEM=$(free -h | awk '/^Mem:/ {print $7" livres de "$2}')
SWAP=$(free -h | awk '/^Swap:/ {print $3" usados de "$2}')
ATUAL=$(apt list --upgradable 2>/dev/null | grep -c upgradable)
SEG=$(apt list --upgradable 2>/dev/null | grep -c -- '-security')
if [ -f /var/run/reboot-required ]; then REBOOT="sim"; else REBOOT="não"; fi
GATEWAY=$(systemctl --user is-active hermes-gateway 2>/dev/null)

ALERTA=""
[ "$USO" -ge 80 ] && ALERTA="⚠️ Disco acima de 80%\n"
[ "$GATEWAY" != "active" ] && ALERTA="${ALERTA}⚠️ Gateway do Hermes parado\n"

MSG="**Check semanal da VPS do Hermes**\n${ALERTA}Disco: ${DISCO}\nMemória: ${MEM}\nSwap: ${SWAP}\nAtualizações pendentes: ${ATUAL} (${SEG} de segurança)\nReinício pendente: ${REBOOT}\nGateway do Hermes: ${GATEWAY}"

curl -fsS -H "Content-Type: application/json" -d "{\"content\":\"${MSG}\"}" "$WEBHOOK" > /dev/null
