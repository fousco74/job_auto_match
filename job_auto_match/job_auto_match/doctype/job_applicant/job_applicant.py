import frappe
from frappe import enqueue
from urllib.parse import urlparse
import pathlib

RETRY_COOLDOWN_MIN = 5


# ── Helpers ──────────────────────────────────────────────────────────────────
def _norm(s):
    return (s or "").strip().lower()


def _enqueue_matching(applicant_name: str):
    enqueue(
        "job_auto_match.job_auto_match.utils.matching.process_job_applicant_matching",
        applicant_name=applicant_name,
        queue="long",
        timeout=300,
        now=False,
    )


# ── Hooks document ────────────────────────────────────────────────────────────
def enqueue_matching(doc, method=None):
    try:
        frappe.logger().info(f"[MATCHING] Enqueue pour candidat : {doc.name}")
        _enqueue_matching(doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[MATCHING] Échec enqueue")
        raise


def validate_unique_application(doc, method=None):
    _validate_cv(doc)
    _validate_no_duplicate(doc)


# ── Validation CV ─────────────────────────────────────────────────────────────
def _validate_cv(doc):
    resume_url = (getattr(doc, "resume_attachment", "") or "").strip()
    if not resume_url:
        frappe.throw(
            frappe._("Veuillez joindre votre CV (PDF ou Word) avant de soumettre."),
            title=frappe._("CV manquant"),
        )

    allowed_ext = {".pdf", ".doc", ".docx"}
    try:
        ext = pathlib.Path(urlparse(resume_url).path).suffix.lower()
    except Exception:
        ext = ""

    if ext not in allowed_ext:
        frappe.throw(
            frappe._("Format CV non supporté : {0}. Utilisez PDF, DOC ou DOCX.").format(ext or resume_url),
            title=frappe._("Format non supporté"),
        )

    # Vérification MIME via le doctype File (non bloquant)
    try:
        file_rec = frappe.get_all(
            "File",
            filters={"file_url": resume_url},
            fields=["mime_type"],
            limit=1,
            ignore_permissions=True,
        )
        if file_rec:
            mime = (file_rec[0].get("mime_type") or "").lower()
            allowed_mime = {
                "application/pdf",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
            if mime and mime not in allowed_mime:
                frappe.throw(
                    frappe._("Type MIME non supporté : {0}.").format(mime),
                    title=frappe._("Format non supporté"),
                )
    except frappe.ValidationError:
        raise
    except Exception:
        pass  # non bloquant


# ── Dédoublonnage ─────────────────────────────────────────────────────────────
def _validate_no_duplicate(doc):
    email       = _norm(getattr(doc, "email_id", ""))
    job_opening = getattr(doc, "job_opening", None)
    job_title   = (getattr(doc, "job_title", "") or "").strip()

    if not email:
        return

    if not job_title and not job_opening:
        frappe.throw(
            frappe._("Sélectionnez une offre (Job Opening) ou renseignez le poste."),
            title=frappe._("Offre non définie"),
        )

    filters = {"email_id": email, "docstatus": ["!=", 2]}
    if job_opening:
        filters["job_opening"] = job_opening
    else:
        filters["job_title"] = job_title

    existing = frappe.get_all(
        "Job Applicant",
        filters=filters,
        limit=1,
        pluck="name",
        ignore_permissions=True,
    )
    if existing:
        frappe.throw(
            frappe._("Candidature déjà enregistrée pour cette offre. Référence : {0}").format(existing[0]),
            title=frappe._("Doublon"),
            exc=frappe.ValidationError,
        )


# ── Liaison fichier CV ────────────────────────────────────────────────────────
def ensure_resume_file_linked(doc, method=None):
    """
    Garantit que le fichier CV (resume_attachment) est bien rattaché à ce Job
    Applicant dans le document File.  Appelé sur after_insert et on_update pour
    couvrir les uploads manuels (Administrator) et via web form (Guest).
    """
    resume_url = (getattr(doc, "resume_attachment", "") or "").strip()
    if not resume_url:
        return

    orphan_files = frappe.db.get_all(
        "File",
        filters={
            "file_url": resume_url,
            "attached_to_doctype": ("is", "not set"),
        },
        fields=["name"],
    )
    for file_record in orphan_files:
        frappe.db.set_value(
            "File",
            file_record.name,
            {
                "attached_to_doctype": "Job Applicant",
                "attached_to_name": doc.name,
                "attached_to_field": "resume_attachment",
            },
            update_modified=False,
        )


# ── Synchronisation custom_status ↔ workflow_state ──────────────────────────
def sync_workflow_state(doc, method=None):
    """Maintient workflow_state aligné sur custom_status à chaque sauvegarde."""
    statut = getattr(doc, "custom_status", None)
    if statut and getattr(doc, "workflow_state", None) != statut:
        doc.workflow_state = statut


# ── Retry (appelé aussi depuis api.py) ───────────────────────────────────────
@frappe.whitelist()
def retry_matching(applicant_name: str, force: int = 0):
    """Relance le job de matching avec cooldown anti-spam."""
    from frappe.utils import now_datetime

    doc = frappe.get_doc("Job Applicant", applicant_name)

    if not getattr(doc, "resume_attachment", None):
        frappe.throw("Aucun CV attaché.")

    if not int(force or 0):
        last = getattr(doc, "custom_last_retry_at", None)
        if last:
            from frappe.utils import get_datetime
            elapsed = (now_datetime() - get_datetime(last)).total_seconds()
            if elapsed < RETRY_COOLDOWN_MIN * 60:
                frappe.throw(
                    f"Réessayez dans {RETRY_COOLDOWN_MIN} minutes."
                )

    doc.custom_last_retry_at = now_datetime()
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    _enqueue_matching(doc.name)
    return {"ok": True, "queued": True, "message": f"Relance planifiée pour {doc.name}."}
