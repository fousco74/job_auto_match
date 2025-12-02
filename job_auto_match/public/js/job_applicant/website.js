// Sélectionne tous les liens dont l'attribut href contient "/job-applicant/new"
const buttons = document.querySelectorAll("a[href*='/job-applicant/new']");

buttons.forEach(button => {
  // Vérifie si le texte du bouton est "Choisir"
  if (button.textContent.trim() === "Choisir") {
    // Change le texte en "Postuler"
    button.textContent = "Postuler";
  }
});
