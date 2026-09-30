// Apply the category filter as soon as a different category is picked.
const categoryFilter = document.getElementById("category-filter");
if (categoryFilter) {
  categoryFilter.addEventListener("change", () => categoryFilter.form.submit());
}

// Ask for confirmation before deleting a transaction.
document.querySelectorAll(".delete-form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!confirm("Delete this transaction?")) event.preventDefault();
  });
});
