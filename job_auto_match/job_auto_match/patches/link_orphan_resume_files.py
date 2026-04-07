"""
Patch: link_orphan_resume_files
--------------------------------
Lie les fichiers CV privés (File.attached_to_doctype IS NULL) à leur Job Applicant
correspondant en se basant sur le champ resume_attachment.

Contexte : les CVs uploadés manuellement par l'Administrator et certains uploadés
via le web form ne sont pas correctement rattachés au document Job Applicant,
ce qui bloque leur accès aux rôles Talent Acquisition.
"""

import frappe


def execute():
    # Récupère tous les candidats ayant un CV renseigné
    applicants = frappe.db.get_all(
        "Job Applicant",
        filters=[["resume_attachment", "!=", ""]],
        fields=["name", "resume_attachment"],
        limit_page_length=0,
    )

    fixed = 0
    for applicant in applicants:
        if not applicant.resume_attachment:
            continue

        # Cherche les fichiers File correspondant à cette URL et non encore liés
        orphan_files = frappe.db.get_all(
            "File",
            filters={
                "file_url": applicant.resume_attachment,
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
                    "attached_to_name": applicant.name,
                    "attached_to_field": "resume_attachment",
                },
                update_modified=False,
            )
            fixed += 1

    if fixed:
        frappe.db.commit()

    frappe.logger().info(f"[link_orphan_resume_files] {fixed} fichier(s) lié(s) à leur Job Applicant.")
    print(f"Patch terminé : {fixed} fichier(s) lié(s).")
