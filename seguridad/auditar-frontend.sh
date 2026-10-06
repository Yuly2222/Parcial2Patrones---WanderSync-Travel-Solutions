#!/bin/sh
# Auditoría de la cadena de suministro del FRONTEND (npm audit), complemento de auditar.sh (pip-audit).
# Revisa TODAS las dependencias (directas y transitivas) fijadas en frontend/package-lock.json
# contra la base de avisos de seguridad de GitHub/npm.
#
# Se ejecuta en un contenedor de Node, así no hace falta tener Node instalado:
#   docker run --rm -v "$PWD:/w" -w /w node:22-alpine sh seguridad/auditar-frontend.sh
#
# Resultado: seguridad/auditoria-frontend.md (evidencia formal para el informe).
set -u
OUT=seguridad/auditoria-frontend.md
cd frontend
npm audit > /tmp/audit.txt 2>&1
codigo=$?
total=$(npm ls --all --parseable 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')
cd ..
{
  echo "# Auditoría de dependencias del frontend (npm audit)"
  echo
  echo "- Fecha: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Herramienta: npm $(npm --version) (\`npm audit\`)"
  echo "- Fuente de vulnerabilidades: GitHub Advisory Database (registro de npm)"
  echo "- Alcance: \`frontend/package-lock.json\` — $total paquetes (directos y transitivos)"
  echo "- La imagen Docker instala con \`npm ci\`, es decir, exactamente estas versiones auditadas."
  echo
  echo '```'
  cat /tmp/audit.txt
  echo "(código de salida de npm audit: $codigo -> 0 = sin vulnerabilidades conocidas, 1 = hay vulnerabilidades)"
  echo '```'
} > "$OUT"
echo "Listo: $OUT"
