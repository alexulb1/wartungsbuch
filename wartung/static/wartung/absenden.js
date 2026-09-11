/* Gegen doppeltes Absenden: Ein abgeschicktes Formular nimmt keinen zweiten
   Klick mehr an. Der Server fängt Wiederholungen ohnehin ab (einmalig.py) --
   das hier erspart nur, dass eine zweite Anfrage samt Fotos überhaupt losgeht.

   Bewusst ohne disabled am Knopf: Ein gesperrter Knopf würde je nach Browser
   aus den mitgeschickten Daten fallen. */
(function () {
  "use strict";

  document.addEventListener("submit", function (ereignis) {
    var formular = ereignis.target;
    if (formular.method !== "post") {
      return;
    }
    if (formular.classList.contains("wird-gesendet")) {
      ereignis.preventDefault();
      return;
    }
    formular.classList.add("wird-gesendet");
    formular.setAttribute("aria-busy", "true");
  });

  // Mit "Zurück" holt der Browser die Seite samt Sperre aus dem Speicher.
  window.addEventListener("pageshow", function (ereignis) {
    if (!ereignis.persisted) {
      return;
    }
    document.querySelectorAll("form.wird-gesendet").forEach(function (formular) {
      formular.classList.remove("wird-gesendet");
      formular.removeAttribute("aria-busy");
    });
  });
})();
