frappe.ui.form.on('Job Applicant', {
	refresh(frm) {
        hide_specific_action_button(frm);
	}
})

function hide_specific_action_button(frm) {
        setTimeout(() => {
            // Correction du sélecteur pour cibler le bon élément
            const bouton = $('div.actions-btn-group');
            
            if (bouton.length) {
                bouton.hide();

            } else {
                console.warn("Bouton spécifique non trouvé");
            }
        }, 300);
}