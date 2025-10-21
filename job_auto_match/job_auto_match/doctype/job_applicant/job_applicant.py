import frappe
from frappe import enqueue
from frappe.utils import now_datetime, add_to_date
from datetime import timedelta
from urllib.parse import urlparse
import pathlib



# --------------------------------------
# Enqueue async pour traitement matching
# --------------------------------------
def enqueue_matching(doc, method=None):
    try:
        frappe.logger().info(f"[MATCHING] Enqueue pour candidat : {doc.name}")
        enqueue(
            "job_auto_match.job_auto_match.utils.matching.process_job_applicant_matching",
            applicant_name=doc.name,
            queue="long",
            timeout=300,  # 5 min
            now=False
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "[MATCHING] Échec enqueue")
        raise


# --------------------------------------
# Helpers internes
# --------------------------------------
def _norm(s):
    return (s or "").strip().lower()


def _dbg(msg, data=None):
    try:
        line = f"[UNIQ_APPLY] {msg}"
        if data is not None:
            try:
                line += f" | {frappe.as_json(data)}"
            except Exception:
                line += f" | {data}"
        print(line)
        frappe.logger().info(line)
    except Exception:
        pass


# --------------------------------------
# Validation : éviter candidatures en double + CV PDF/Word
# --------------------------------------
def validate_unique_application(doc, method=None):
    _dbg("Vérification unicité démarrée", {"docname": doc.name})

    # --- Vérification CV : obligatoire et format PDF/Word ---
    resume_url = (getattr(doc, "resume_attachment", "") or "").strip()
    if not resume_url:
        frappe.throw(
            frappe._("Veuillez joindre votre CV au format PDF ou Word (.pdf, .doc, .docx) avant de soumettre la candidature."),
            title=frappe._("CV manquant")
        )

    # Vérification par extension (rapide)
    allowed_ext = {".pdf", ".doc", ".docx"}
    try:
        path_part = urlparse(resume_url).path  # ex: /files/cv_marie_dupont.pdf
        ext = pathlib.Path(path_part).suffix.lower()
    except Exception:
        ext = ""

    if ext not in allowed_ext:
        frappe.throw(
            frappe._("Le CV doit être au format PDF ou Word (.pdf, .doc, .docx). Fichier fourni : {0}")
                   .format(resume_url),
            title=frappe._("Format de CV non supporté")
        )

    # Vérification (optionnelle) via le doctype File → MIME type
    try:
        file_rec = frappe.get_all(
            "File",
            filters={"file_url": resume_url},
            fields=["file_url", "file_name", "mime_type"],
            limit=1,
            ignore_permissions=True,
        )
        if not file_rec and path_part:
            # fallback par file_name si nécessaire
            file_rec = frappe.get_all(
                "File",
                filters={"file_name": pathlib.Path(path_part).name},
                fields=["file_url", "file_name", "mime_type"],
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
                    frappe._("Le CV doit être au format PDF ou Word. Type détecté : {0}")
                           .format(mime),
                    title=frappe._("Type de fichier non supporté")
                )
    except Exception as e:
        _dbg("Lookup File/mime ignoré (non bloquant)", {"error": str(e)})

    # --- Unicité candidature (email + offre OU email + job title) ---
    email = _norm(getattr(doc, "email_id", ""))
    job_opening = getattr(doc, "job_opening", None)
    job_title = (getattr(doc, "job_title", "") or "").strip()

    _dbg("Champs d'entrée normalisés", {
        "email": email,
        "job_opening": job_opening,
        "job_title": job_title
    })

    if not email:
        _dbg("Email manquant — aucune validation unicité faite")
        return

    # 👉 Message quand job_title est vide
    if not job_title:
        if job_opening:
            frappe.msgprint(
                frappe._("L'intitulé du poste (Job Title) n'est pas renseigné. "
                         "La vérification de doublon se fera sur l'offre (Job Opening) : {0}.")
                .format(job_opening),
                alert=True, indicator='orange'
            )
        else:
            frappe.throw(
                frappe._("Veuillez sélectionner une offre (Job Opening) ou renseigner l'intitulé du poste (Job Title) avant de soumettre la candidature."),
                title=frappe._("Offre non définie")
            )

    filters = {"email_id": email, "docstatus": ["!=", 2]}
    if job_opening:
        filters["job_opening"] = job_opening
        _dbg("Filtrage par job_opening", filters)
    else:
        filters["job_title"] = job_title
        _dbg("Filtrage par job_title", filters)

    try:
        existing = frappe.get_all(
            "Job Applicant",
            filters=filters,
            limit=1,
            pluck="name",
            ignore_permissions=True
        )
        _dbg("Résultat recherche de doublons", existing)
    except Exception as e:
        _dbg("Erreur frappe.get_all", {"error": str(e)})
        raise

    if existing:
        existing_docname = existing[0]
        msg = frappe._("Vous avez déjà postulé à cette offre. Référence : {0}").format(existing_docname)
        frappe.throw(
            msg,
            title=frappe._("Candidature déjà enregistrée"),
            exc=frappe.ValidationError
        )

    _dbg("Aucun doublon détecté, validation OK")




def sync_job_applicant_status(doc, method=None):
    """
    Centralise la synchronisation entre custom_status_x et workflow_state.
    Comme on est dans 'on_update' (après save), il faut persister la MAJ explicitement.
    """
    status = (getattr(doc, "custom_status_x", None) or "").strip()
    if not status:
        return

    # Vérifie que l'état de workflow cible existe
    if not frappe.db.exists("Workflow State", status):
        frappe.throw(f"Workflow State introuvable : {status}")

    current = (getattr(doc, "workflow_state", None) or "").strip()
    if current == status:
        # Rien à faire
        return

    # IMPORTANT : 'on_update' est post-save → il faut forcer l'écriture
    # Utiliser frappe.db.set_value pour éviter une boucle d'événements
    frappe.db.set_value(doc.doctype, doc.name, "workflow_state", status, update_modified=False)

    # Met à jour l'instance en mémoire (utile pour les logs, autres hooks, etc.)
    doc.workflow_state = status

    frappe.logger().info(f"[SYNC] workflow_state mis à jour → {status} (via on_update)")
    



RETRY_COOLDOWN_MIN = 5  # anti-spam : 5 minutes entre relances
def _can_retry(doc, force=False):
    """Anti-spam + prérequis (CV)."""
    if not getattr(doc, "resume_attachment", None):
        frappe.throw("Aucun CV n'est attaché (resume_attachment).")
    if force:
        return True
    last = getattr(doc, "custom_last_retry_at", None)
    if last:
        # si dernier retry < RETRY_COOLDOWN_MIN minutes → bloque
        if (now_datetime() - last).total_seconds() < RETRY_COOLDOWN_MIN * 60:
            frappe.throw(f"Vous avez déjà relancé récemment. Réessayez dans {RETRY_COOLDOWN_MIN} minutes.")
    return True

@frappe.whitelist()
def retry_matching(applicant_name: str, force: int = 0):
    """Relance le job de matching pour un candidat."""
    force = int(force or 0)
    doc = frappe.get_doc("Job Applicant", applicant_name)

    _can_retry(doc, force=bool(force))


    # Enqueue le traitement long
    enqueue(
        "job_auto_match.job_auto_match.utils.matching.process_job_applicant_matching",
        applicant_name=doc.name,
        queue="long",
        timeout=300,
        now=False
    )

    return {
        "ok": True,
        "queued": True,
        "message": f"Relance planifiée pour {doc.name}."
    }
