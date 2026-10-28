#!/usr/bin/env bash
# Protege la rama main del repo del curso con un «ruleset» de GitHub (lo corre el profesor
# una vez, con su `gh` de admin, después de publicar el repo):
#
#   sistema/herramientas/proteger_main.sh [dueño/repo]
#
# Reglas sobre main:
# - Todo cambio entra por pull request, con 1 aprobación de un code owner (CODEOWNERS).
#   Sin esa aprobación, un PR podría editar revisar-pr.yml y dejar pasar su propio check.
# - El check «revisar-entrega» (revisar-pr.yml, de GitHub Actions) debe pasar.
# - Nada de force push ni de borrar la rama.
# Además, ruleset «proteger-publicacion» para las ramas «oficial» y «ensayo» (las escribe
# la liga): sin force push ni borrado.
# Los admins del repo (el profesor y el equipo docente) se saltan las reglas: pueden
# cambiar cualquier cosa directo. Si un ruleset ya existe, se actualiza.
set -euo pipefail

REPO="${1:-raya-lucaria/ia_o26_torneo_adversarial}"
ID_GITHUB_ACTIONS=15368 # el check debe venir de GitHub Actions, no de otra app
ROL_ADMIN=5             # rol de repositorio «admin» en bypass_actors

command -v gh >/dev/null || { echo "✗ Falta gh (https://cli.github.com)." >&2; exit 2; }

reglas="$(
    cat <<JSON
{
  "name": "proteger-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
  "bypass_actors": [
    {"actor_id": $ROL_ADMIN, "actor_type": "RepositoryRole", "bypass_mode": "always"}
  ],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 1,
      "require_code_owner_review": true,
      "dismiss_stale_reviews_on_push": true,
      "require_last_push_approval": false,
      "required_review_thread_resolution": false
    }},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": false,
      "required_status_checks": [
        {"context": "revisar-entrega", "integration_id": $ID_GITHUB_ACTIONS}
      ]
    }}
  ]
}
JSON
)"

publicacion="$(
    cat <<JSON
{
  "name": "proteger-publicacion",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/heads/oficial", "refs/heads/ensayo"], "exclude": []}},
  "bypass_actors": [
    {"actor_id": $ROL_ADMIN, "actor_type": "RepositoryRole", "bypass_mode": "always"}
  ],
  "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}]
}
JSON
)"

aplicar() { # <nombre> <json>
    local nombre="$1" json="$2" existente
    existente="$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$nombre\") | .id" | head -n 1)"
    if [[ -n "$existente" ]]; then
        echo "Actualizando el ruleset $nombre (id $existente) de $REPO..."
        gh api --method PUT "repos/$REPO/rulesets/$existente" --input - <<<"$json" >/dev/null
    else
        echo "Creando el ruleset $nombre en $REPO..."
        gh api --method POST "repos/$REPO/rulesets" --input - <<<"$json" >/dev/null
    fi
}

aplicar proteger-main "$reglas"
aplicar proteger-publicacion "$publicacion"
gh api "repos/$REPO/rulesets" --jq '.[] | "\(.id)\t\(.name)\t\(.enforcement)"'
echo "✓ main, oficial y ensayo protegidas. Revisa en Settings → Rules → Rulesets."
