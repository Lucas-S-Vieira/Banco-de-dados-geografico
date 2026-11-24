#!/usr/bin/env bash
# Importa a base em um banco novo. Uso: ./scripts/importar.sh nome_do_banco  (da raiz do repo)
set -euo pipefail
BANCO="${1:?informe o nome do banco}"
createdb "$BANCO"
psql -d "$BANCO" -v ON_ERROR_STOP=1 -q -f sql/schema.sql
psql -d "$BANCO" -v ON_ERROR_STOP=1 -f sql/carga.sql
psql -d "$BANCO" -v ON_ERROR_STOP=1 -f sql/pos_carga.sql
echo "Base importada em '$BANCO'. Exemplos: psql -d $BANCO -f sql/consultas.sql"
