
// Theme switching logic
document.addEventListener("DOMContentLoaded", () => {
  const savedTheme = localStorage.getItem("selectedTheme") || "dark-blue";
  document.body.className = savedTheme; // Apply saved theme on load

  // Set correct radio checked
  const themeRadio = document.querySelector(`input[name="theme"][value="${savedTheme}"]`);
  if (themeRadio) themeRadio.checked = true;

  // Handle theme change
  document.querySelectorAll('input[name="theme"]').forEach(radio => {
    radio.addEventListener("change", (e) => {
      const newTheme = e.target.value;
      document.body.className = newTheme;
      localStorage.setItem("selectedTheme", newTheme);
    });
  });

  // Optional: Toggle theme list with the palette icon
  const themeToggleBtn = document.getElementById("theme-toggle");
  const themeOptions = document.querySelector(".theme-options");

  if (themeToggleBtn && themeOptions) {
    themeToggleBtn.addEventListener("click", () => {
      themeOptions.classList.toggle("show");
    });
  }
});


