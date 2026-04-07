app_name        = "job_auto_match"
app_title       = "RecrutIA"
app_publisher   = "AMOAMAN"
app_description = "Automatisation du recrutement avec scoring IA (Gemini) et intégration Testlify"
app_email       = "fkone@amoaman.com"
app_license     = "mit"
app_version     = "1.0.0"

required_apps = ["hrms"]

# ── JS par doctype ──────────────────────────────────────────────────────────
doctype_js = {"Job Applicant": "public/js/job_applicant.js"}

# ── Hooks document ──────────────────────────────────────────────────────────
doc_events = {
    "Job Applicant": {
        "before_insert": "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.validate_unique_application",
        "after_insert":  [
            "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.enqueue_matching",
            "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.ensure_resume_file_linked",
        ],
        "on_update":     "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.ensure_resume_file_linked",
        "validate":      "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.sync_workflow_state",
    }
}

# ── Fixtures ────────────────────────────────────────────────────────────────
# Exported with: bench --site <site> export-fixtures --app job_auto_match
# Imported with: bench --site <site> migrate  (or bench import-fixtures)

_JOB_DOCTYPES = ["Job Opening", "Job Applicant"]

_WORKFLOW_STATES = [
    "Open", "Vivrier", "Top Profil",
    "Rejecté", "En Cours de qualification", "Accepté",
]

fixtures = [
    # Permissions personnalisées sur Job Applicant
    {
        "doctype": "Custom DocPerm",
        "filters": [["parent", "=", "Job Applicant"]],
    },
    # Champs personnalisés sur Job Opening et Job Applicant
    {
        "doctype": "Custom Field",
        "filters": [["dt", "in", _JOB_DOCTYPES]],
    },
    # Actions de workflow (obligatoires dans Workflow Action Master)
    {
        "doctype": "Workflow Action Master",
        "filters": [["workflow_action_name", "in", _WORKFLOW_STATES]],
    },
    # États du workflow recrutement
    {
        "doctype": "Workflow State",
        "filters": [["workflow_state_name", "in", _WORKFLOW_STATES]],
    },
    # Workflow Job Applicant (non restrictif — toutes transitions autorisées)
    {
        "doctype": "Workflow",
        "filters": [["document_type", "=", "Job Applicant"]],
    },
    # Formulaire web candidat
    {
        "doctype": "Web Form",
        "filters": [["name", "=", "job-applicant"]],
    },
]
