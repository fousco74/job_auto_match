import frappe
from frappe import enqueue

def enqueue_matching(doc, method):
    enqueue(
        "job_auto_match.job_auto_match.utils.matching.process_job_applicant_matching",
        applicant_name=doc.name,
        queue='long',
        timeout=300  # 5 minutes si besoin
    )



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
        try:
            frappe.logger().info(line)
        except Exception:
            pass
    except Exception:
        pass

def validate_unique_application(doc, method=None):
    _dbg("Called", {"docname": getattr(doc, "name", None)})

    email = _norm(getattr(doc, "email_id", ""))
    job_opening = getattr(doc, "job_opening", None)
    job_title = (getattr(doc, "job_title", "") or "").strip()

    _dbg("Input fields", {
        "email_normalized": email,
        "job_opening": job_opening,
        "job_title": job_title
    })

    if not email:
        _dbg("No email provided, skip uniqueness check")
        return

    filters = {"email_id": email, "docstatus": ["!=", 2]}
    if job_opening:
        filters["job_opening"] = job_opening
        _dbg("Using job_opening in filters", filters)
    else:
        filters["job_title"] = job_title
        _dbg("Using job_title in filters", filters)

    try:
        existing = frappe.get_all(
            "Job Applicant",
            filters=filters,
            limit=1,
            pluck="name",
            ignore_permissions=True
        )
        _dbg("frappe.get_all result", existing)
    except Exception as e:
        _dbg("Error during frappe.get_all", {"error": str(e)})
        raise

    if existing:
        name = existing[0]
        msg = frappe._("Vous avez déjà postulé à ce poste. Référence : {0}").format(name)
        _dbg("Duplicate detected", {"existing_doc": name, "filters": filters})

        # Option A (recommandé) : message rouge visible sur Web Form
        frappe.throw(msg, title=frappe._("Candidature déjà enregistrée"), exc=frappe.ValidationError)

        # Option B (UX sympa) : rediriger vers une page d’info (décommente si tu préfères)
        # frappe.local.response["type"] = "redirect"
        # frappe.local.response["location"] = f"/applications?already_applied=1&ref={name}"
        # raise frappe.Redirect

    _dbg("No duplicate found, validation passed")