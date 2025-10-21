frappe.ui.form.on('Job Applicant', {
	refresh(frm) {
        hide_specific_action_button(frm);
        update_custom_job_title(frm);

        if (frm.is_new()) return;

    const in_prog  = !!frm.doc.custom_is_matching_in_progress;
    const failed   = !!frm.doc.custom_is_matching_failed;
    const emailSent= !!frm.doc.custom_not_match_email_sent;
    const invites  = !!frm.doc.custom_invites_sent;

    // Groupe d’actions IA
    frm.add_custom_button('Relancer matching', () => {
      frappe.call({
        method: 'job_auto_match.api.retry_matching',
        args: { applicant_name: frm.doc.name },
        freeze: true, freeze_message: 'Relance en cours…',
        callback: () => frm.reload_doc()
      });
    }, 'Actions IA');

    frm.add_custom_button('Renvoyer email "Non retenu"', () => {
      frappe.call({
        method: 'job_auto_match.api.resend_not_match_email',
        args: { applicant_name: frm.doc.name },
        freeze: true, freeze_message: 'Envoi e-mail…',
        callback: () => frm.reload_doc()
      });
    }, 'Actions IA');

    frm.add_custom_button('Renvoyer invitations', () => {
      frappe.call({
        method: 'job_auto_match.api.resend_invites',
        args: { applicant_name: frm.doc.name },
        freeze: true, freeze_message: 'Envoi invitations…',
        callback: () => frm.reload_doc()
      });
    }, 'Actions IA');

    // Rubans d’info (facultatif)
    frm.dashboard.clear_headline();
    if (in_prog) {
      frm.dashboard.set_headline_alert('Matching en cours…', 'blue');
    } else if (failed) {
      frm.dashboard.set_headline_alert(
        `Dernière erreur IA: ${frappe.utils.escape_html(frm.doc.custom_ai_last_error || '')}`,
        'red'
      );
    } else if (emailSent) {
      frm.dashboard.set_headline_alert('E-mail “Non retenu” envoyé', 'green');
    } else if (invites) {
      frm.dashboard.set_headline_alert('Invitations envoyées', 'green');
    }
  

        

	},
    job_title: function(frm) {
        update_custom_job_title(frm);
    }
})


// Fonction pour récupérer le job_title réel depuis Job Opening
function update_custom_job_title(frm) {
    if(frm.doc.job_title) {
        frappe.db.get_value('Job Opening', frm.doc.job_title, 'job_title')
        .then(r => {
            if(r && r.message) {
                frm.set_value('custom_nom_de_loffre', r.message.job_title);
            }
        });
    } else {
        frm.set_value('custom_nom_de_loffre', '');
    }
}

function hide_specific_action_button(frm) {
        setTimeout(() => {
            // Correction du sélecteur pour cibler le bon élément
            const bouton = $('div.actions-btn-group');
            
            if (bouton.length) {
                bouton.hide();

            } else {
                console.log("Bouton spécifique non trouvé");
            }
        }, 300);
}