#!/bin/sh
# Auditoría de la cadena de suministro (supply chain): busca vulnerabilidades conocidas (CVE / PYSEC / GHSA)
# en las dependencias de CADA microservicio, consultando la base de datos pública de vulnerabilidades (OSV/PyPI).
#
# Se ejecuta dentro de un contenedor de Python, así no hace falta tener Python instalado:
#   docker run --rm -v "$PWD:/w" -w /w python:3.12-slim sh seguridad/auditar.sh
#
# Resultado: seguridad/auditoria-dependencias.md (evidencia formal para el informe).
set -u
pip install --quiet --disable-pip-version-check pip-audit
OUT=seguridad/auditoria-dependencias.md
{
  echo "# Auditoría de dependencias (pip-audit)"
  echo
  echo "- Fecha: $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo "- Herramienta: $(pip-audit --version)"
  echo "- Fuente de vulnerabilidades: base de datos de PyPI / OSV"
  echo "- Comando: \`pip-audit -r <servicio>/requirements.txt\` (resuelve e instala en un entorno aislado las versiones exactas que usaría Docker y las compara con las vulnerabilidades conocidas)"
  echo
} > "$OUT"
for req in */requirements.txt; do
  servicio=$(dirname "$req")
  echo "Auditando $servicio..."
  # Se guarda el código de salida de pip-audit ANTES de filtrar (en un pipe, $? sería el del último comando)
  pip-audit -r "$req" --desc off > /tmp/audit.txt 2>&1
  codigo=$?
  {
    echo "## $servicio"
    echo
    echo '```'
    grep -v "^WARNING: pip is being invoked" /tmp/audit.txt
    echo "(código de salida de pip-audit: $codigo -> 0 = sin vulnerabilidades conocidas, 1 = hay vulnerabilidades)"
    echo '```'
    echo
  } >> "$OUT"
done
echo "Listo: $OUT"
